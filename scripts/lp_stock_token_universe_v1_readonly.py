#!/usr/bin/env python3
"""Build a conservative stock-token LP universe from DefiLlama (read only).

The recognizer deliberately uses an explicit instrument catalogue and a few
chain/project-scoped rules.  It does *not* infer that every token ending in
``X`` or ``ON`` is a stock: false positives are more dangerous than misses for
the downstream RWA basis gate.  DefiLlama data remains Stage-1 lead evidence;
no value produced here is on-chain validation or permission to trade.

Network behaviour is limited to one public, keyless HTTPS GET.  The module has
no wallet, signer, RPC, transaction, or broadcast path.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
DEFAULT_MIN_TVL_USD = 20_000.0
WASH_SUSPECT_VOL_TVL = 1.5
MAX_RESPONSE_BYTES = 64_000_000

# A frozen, reviewed subset of the Backed/xStocks catalogue that appears in or
# immediately around the 2026-08-10 LP snapshot.  Extending this table is an
# explicit evidence change; a generic ``*X`` suffix is intentionally unsafe.
BACKED_TOKENS = {
    "AAPLX": "AAPL", "AMZNX": "AMZN", "AVGOX": "AVGO",
    "BRK.BX": "BRK.B", "COINX": "COIN", "CRCLX": "CRCL",
    "GLDX": "GLD", "GMEX": "GME", "GOOGLX": "GOOGL",
    "HOODX": "HOOD", "INTCX": "INTC", "KOX": "KO",
    "MCDX": "MCD", "METAX": "META", "MSFTX": "MSFT",
    "MSTRX": "MSTR", "NVDAX": "NVDA", "PLTRX": "PLTR",
    "QQQX": "QQQ", "SPCXX": "SPCX", "SPYX": "SPY",
    "STRCX": "STRC", "TQQQX": "TQQQ", "TSLAX": "TSLA",
}

ONDO_TOKENS = {
    "AAPLON": "AAPL", "AMZNON": "AMZN", "GOOGLON": "GOOGL",
    "METAON": "META", "MSFTON": "MSFT", "NVDAON": "NVDA",
    "QQQON": "QQQ", "SPYON": "SPY", "TSLAON": "TSLA",
}

# Bare tickers are accepted only on an issuer-specific chain or a reviewed
# synthetic-stock project, except for a very small generic stock/index set.
BARE_TICKERS = {
    "AAPL", "AI", "AMZN", "ARKK", "BABA", "BITI", "COIN", "EEM",
    "FB", "GLD", "GME", "GOOGL", "IBIT", "MSFT", "MSTR", "NFLX",
    "NVDA", "PFE", "PLTR", "QQQ", "SLV", "SPCX", "SPY", "TLT",
    "TSLA", "URTH",
}
GENERIC_UNAMBIGUOUS_TICKERS = {
    "AAPL", "AMZN", "GOOGL", "MSFT", "NVDA", "PLTR", "TSLA",
    "SSI",
}
BARE_STOCK_PROJECTS = {"defichain-dex", "gmtrade"}

STABLES = {
    "USDC", "USDC.E", "USDBC", "USDT", "USDT.E", "DAI", "DUSD",
    "USDG", "USDS", "FDUSD", "TUSD", "BUSD", "PYUSD", "EURC",
    "FRAX", "CRVUSD", "GHO", "USDE", "USD0", "USYC",
}
MAJOR_CRYPTO = {
    "BTC", "WBTC", "CBBTC", "TBTC", "ETH", "WETH", "SOL", "WSOL",
    "BNB", "WBNB", "AVAX", "WAVAX", "XRP", "ADA", "SUI",
}

CONSTANT_PRODUCT_PROJECTS = {
    "uniswap-v2", "pancakeswap-amm", "sushiswap",
    "defichain-dex", "hyperswap-v2",
}
CLMM_PROJECTS = {
    "orca-dex", "raydium-clmm", "uniswap-v3", "uniswap-v4",
    "sushiswap-v3", "camelot-v3", "pancakeswap-amm-v3",
    "aerodrome-slipstream", "ekubo", "fluxion-network",
}


class UniverseError(ValueError):
    """The input snapshot cannot be interpreted safely."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _finite_nonnegative(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0.0 else None


def split_symbol(symbol: object) -> list[str]:
    """Return exactly the display legs DefiLlama exposes, upper-cased."""

    if not isinstance(symbol, str):
        return []
    return [leg.strip().upper() for leg in symbol.split("-") if leg.strip()]


def preserve_underlying_tokens(value: object) -> list[str] | None:
    """Preserve DefiLlama token identifiers byte-for-byte, or fail closed.

    A UUID is not a Solana pool account.  E7 may use these aggregator-provided
    token identifiers as resolution inputs, but this Stage-1 module must never
    synthesize an address from a display symbol.  A malformed/partial list is
    therefore represented as unavailable rather than filtered or repaired.
    """

    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or not item for item in value):
        return None
    return list(value)


def _backed_identity(token: str) -> tuple[str, str, bool] | None:
    if token in BACKED_TOKENS:
        return token, BACKED_TOKENS[token], False
    # Wrapped EVM xStocks are commonly rendered WSPYX/WTSLAX.  Only unwrap if
    # the remainder is itself in the reviewed catalogue.
    if token.startswith("W") and token[1:] in BACKED_TOKENS:
        inner = token[1:]
        return inner, BACKED_TOKENS[inner], True
    return None


def identify_stock_token(token: object, *, chain: object, project: object) -> dict[str, object] | None:
    """Return a normalized RWA identity, or ``None`` when not certain enough."""

    raw = _text(token).upper()
    chain_name = _text(chain)
    project_name = _text(project).lower()
    if not raw:
        return None

    backed = _backed_identity(raw)
    if backed is not None:
        canonical, ticker, wrapped = backed
        return {
            "instrument_id": f"backed:{canonical}",
            "issuer": "Backed",
            "underlying_ticker": ticker,
            "price_semantics": "token",
            "pool_token_symbol": raw,
            "canonical_token_symbol": canonical,
            "wrapped": wrapped,
            "recognition_basis": "reviewed_backed_xstocks_catalogue",
        }

    if raw in ONDO_TOKENS:
        return {
            "instrument_id": f"ondo:{raw}",
            "issuer": "Ondo",
            "underlying_ticker": ONDO_TOKENS[raw],
            "price_semantics": "token",
            "pool_token_symbol": raw,
            "canonical_token_symbol": raw,
            "wrapped": False,
            "recognition_basis": "reviewed_ondo_catalogue",
        }

    is_robinhood = chain_name.casefold() == "robinhood chain" and raw in BARE_TICKERS
    if is_robinhood:
        return {
            "instrument_id": f"robinhood:{raw}",
            "issuer": "Robinhood",
            "underlying_ticker": raw,
            "price_semantics": "token",
            "pool_token_symbol": raw,
            "canonical_token_symbol": raw,
            "wrapped": False,
            "recognition_basis": "robinhood_chain_bare_ticker_catalogue",
        }

    scoped_bare = project_name in BARE_STOCK_PROJECTS and raw in BARE_TICKERS
    # Generic text is not an issuer proof.  It gets the same reviewed project
    # scope as every other bare ticker, so Base uniswap-v2 TSLA-WETH cannot
    # enter the stock universe simply because its display symbol looks known.
    generic_bare = project_name in BARE_STOCK_PROJECTS and raw in GENERIC_UNAMBIGUOUS_TICKERS
    if scoped_bare or generic_bare:
        return {
            "instrument_id": f"unknown:{chain_name.casefold()}:{raw}",
            "issuer": "unknown",
            "underlying_ticker": raw,
            "price_semantics": "token",
            "pool_token_symbol": raw,
            "canonical_token_symbol": raw,
            "wrapped": False,
            "recognition_basis": (
                "project_scoped_bare_ticker" if scoped_bare else "reviewed_generic_stock_or_index_ticker"
            ),
        }
    return None


def protocol_type(project: object, pool_meta: object = None) -> str:
    name = _text(project).lower()
    meta = _text(pool_meta).lower()
    # DefiLlama's historical project slug is not an architecture guarantee:
    # current Raydium CLMM/CAMMC rows are still published as ``raydium-amm``.
    # Pool metadata therefore has priority over project-level defaults.
    if "concentrated" in meta or "clmm" in meta or "cammc" in meta:
        return "clmm"
    explicit_cp = bool(re.search(r"(?:^|[\s/_-])(standard|amm|cpmm|constant product)(?:$|[\s/_-])", meta))
    if explicit_cp:
        return "amm_constant_product"
    if name == "raydium-amm":
        return "unknown"
    if name in CONSTANT_PRODUCT_PROJECTS:
        return "amm_constant_product"
    if name in CLMM_PROJECTS:
        return "clmm"
    return "unknown"


def classify_pair(legs: Iterable[str], stock_indexes: set[int]) -> str:
    normalized = [str(leg).upper() for leg in legs]
    non_stock = [leg for index, leg in enumerate(normalized) if index not in stock_indexes]
    if len(stock_indexes) >= 2 and not non_stock:
        return "stock_stock"
    if any(leg in STABLES for leg in non_stock):
        return "A"
    if any(leg in MAJOR_CRYPTO for leg in non_stock):
        return "B"
    return "C"


def normalize_pool(pool: Mapping[str, object], *, min_tvl_usd: float = DEFAULT_MIN_TVL_USD) -> dict[str, object] | None:
    if not isinstance(pool, Mapping):
        return None
    tvl = _finite_nonnegative(pool.get("tvlUsd"))
    if tvl is None or tvl < min_tvl_usd:
        return None
    # Lending/vault single-asset records are not DEX LP pools.  DefiLlama's
    # multi-exposure/IL marker is the conservative format-independent filter.
    if _text(pool.get("ilRisk")).lower() != "yes" and _text(pool.get("exposure")).lower() != "multi":
        return None
    legs = split_symbol(pool.get("symbol"))
    if len(legs) != 2:
        return None
    chain = _text(pool.get("chain"))
    project = _text(pool.get("project")).lower()
    stock_instruments: list[dict[str, object]] = []
    stock_indexes: set[int] = set()
    for index, leg in enumerate(legs):
        identity = identify_stock_token(leg, chain=chain, project=project)
        if identity is not None:
            stock_indexes.add(index)
            stock_instruments.append(identity)
    if not stock_instruments:
        return None

    volume = _finite_nonnegative(pool.get("volumeUsd1d"))
    volume = 0.0 if volume is None else volume
    ratio = volume / tvl if tvl > 0.0 else None
    issuers = sorted({str(item["issuer"]) for item in stock_instruments})
    tickers = [str(item["underlying_ticker"]) for item in stock_instruments]
    return {
        "pool_id": _text(pool.get("pool")),
        "chain": chain,
        "project": project,
        "symbol": _text(pool.get("symbol")).upper(),
        "pair_legs": legs,
        "underlying_tokens": preserve_underlying_tokens(pool.get("underlyingTokens")),
        "tier": classify_pair(legs, stock_indexes),
        "protocol_type": protocol_type(project, pool.get("poolMeta")),
        "pool_meta": pool.get("poolMeta") if isinstance(pool.get("poolMeta"), str) else None,
        "issuer": issuers[0] if len(issuers) == 1 else "unknown",
        "underlying_ticker": tickers[0] if len(tickers) == 1 else "+".join(tickers),
        "price_semantics": "token",
        "stock_instruments": stock_instruments,
        "tvl_usd": tvl,
        "volume_usd_1d": volume,
        "vol1d_tvl": ratio,
        "wash_suspect": bool(ratio is not None and ratio > WASH_SUSPECT_VOL_TVL),
        "apy_base": _finite_nonnegative(pool.get("apyBase")),
        "apy_reward": _finite_nonnegative(pool.get("apyReward")),
        "apy_total": _finite_nonnegative(pool.get("apy")),
        "source": "DefiLlama:/pools Stage-1 lead; not on-chain validated",
    }


def build_universe(snapshot: object, *, min_tvl_usd: float = DEFAULT_MIN_TVL_USD) -> list[dict[str, object]]:
    if isinstance(snapshot, Mapping):
        snapshot = snapshot.get("data")
    if not isinstance(snapshot, list):
        raise UniverseError("snapshot must be a list or an object containing data:list")
    rows = [normalize_pool(pool, min_tvl_usd=min_tvl_usd) for pool in snapshot]
    return sorted(
        (row for row in rows if row is not None),
        key=lambda row: (str(row["chain"]), str(row["tier"]), str(row["symbol"]), str(row["pool_id"])),
    )


def summarize(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    materialized = list(rows)
    by_chain_tier: dict[str, Counter[str]] = defaultdict(Counter)
    for row in materialized:
        by_chain_tier[str(row["chain"])][str(row["tier"])] += 1
    tier_counts = Counter(str(row["tier"]) for row in materialized)
    issuer_pool_counts = Counter(str(row["issuer"]) for row in materialized)
    protocol_counts = Counter(str(row["protocol_type"]) for row in materialized)
    raydium_protocol_counts = Counter(
        str(row["protocol_type"]) for row in materialized if row.get("project") == "raydium-amm"
    )
    unknown_instrument_count = sum(
        1 for row in materialized for item in row.get("stock_instruments", [])
        if isinstance(item, Mapping) and item.get("issuer") == "unknown"
    )
    return {
        "pool_count": len(materialized),
        "tier_counts": {key: tier_counts.get(key, 0) for key in ("A", "B", "C", "stock_stock")},
        "chain_tier_counts": {
            chain: {key: counts.get(key, 0) for key in ("A", "B", "C", "stock_stock")}
            for chain, counts in sorted(by_chain_tier.items())
        },
        "issuer_pool_counts": dict(sorted(issuer_pool_counts.items())),
        "issuer_unknown_pool_count": issuer_pool_counts.get("unknown", 0),
        "issuer_unknown_instrument_count": unknown_instrument_count,
        "protocol_counts": dict(sorted(protocol_counts.items())),
        "raydium_protocol_counts": dict(sorted(raydium_protocol_counts.items())),
        "wash_suspect_pool_count": sum(bool(row.get("wash_suspect")) for row in materialized),
        "protocol_unknown_pool_count": sum(row.get("protocol_type") == "unknown" for row in materialized),
        "semantics": {
            "universe": "conservative reviewed identifiers; false-positive avoidance may miss new instruments",
            "issuer": "issuer is never inferred from a bare ticker; unresolved issuers remain unknown",
            "basis": "instrument_id includes issuer, so same underlying across issuers cannot be joined",
            "yield": "DefiLlama Stage-1 lead only; on-chain validation required",
            "raydium": (
                "poolMeta overrides the legacy raydium-amm slug; current Concentrated rows are CLMM. "
                "Missing/ambiguous metadata fails closed as unknown"
            ),
        },
    }


def fetch_snapshot(*, timeout_seconds: float = 30.0) -> object:
    request = Request(
        DEFILLAMA_POOLS_URL,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "lpbot-stock-universe-readonly/1"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed public HTTPS URL
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise UniverseError(f"DefiLlama public GET failed: {type(exc).__name__}") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise UniverseError("DefiLlama response exceeded size limit")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise UniverseError("DefiLlama response was not JSON") from exc


def _markdown(summary: Mapping[str, object], *, as_of: str, input_source: str) -> str:
    lines = [
        "# Stock-token LP universe (read only)", "",
        f"- observed_at_utc: `{as_of}`",
        f"- input: `{input_source}`",
        f"- pool_count: **{summary['pool_count']}**",
        f"- issuer_unknown_pool_count: **{summary['issuer_unknown_pool_count']}**",
        f"- wash_suspect_pool_count (`vol1d/TVL > 1.5`): **{summary['wash_suspect_pool_count']}**",
        f"- Raydium protocol counts (metadata-first): `{summary['raydium_protocol_counts']}`",
        "- status: Stage-1 leads only; not on-chain validated and not entry-eligible evidence.", "",
        "| chain | A | B | C | stock×stock |", "|---|---:|---:|---:|---:|",
    ]
    for chain, counts in summary["chain_tier_counts"].items():
        lines.append(f"| {chain} | {counts['A']} | {counts['B']} | {counts['C']} | {counts['stock_stock']} |")
    lines += [
        "",
        "## Protocol correction versus the task research assumption", "",
        "The research memo treated `raydium-amm` as constant-product.  In this current snapshot the stock-token rows carry `poolMeta=Concentrated - …`; metadata therefore classifies them as `clmm`. The project slug alone is not accepted as architecture evidence, and ambiguous Raydium rows fail closed as `unknown`.", "",
        "Different issuers always retain different `instrument_id` values; bare-ticker issuers remain `unknown`.", "",
    ]
    return "\n".join(lines)


def write_outputs(
    rows: list[dict[str, object]], *, out_dir: Path, as_of: str, input_source: str,
    min_tvl_usd: float = DEFAULT_MIN_TVL_USD,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    envelope = {
        "schema_version": "lp_stock_token_universe_v1",
        "observed_at_utc": as_of,
        "input_source": input_source,
        "min_tvl_usd": min_tvl_usd,
        "rows": rows,
    }
    (out_dir / "stock_token_universe.json").write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "chain_tier_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    unknown_rows = [row for row in rows if row.get("issuer") == "unknown"]
    (out_dir / "unknown_issuer_pools.json").write_text(
        json.dumps(unknown_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "SUMMARY.md").write_text(
        _markdown(summary, as_of=as_of, input_source=input_source), encoding="utf-8"
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="saved DefiLlama JSON; otherwise public GET")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-tvl-usd", type=float, default=DEFAULT_MIN_TVL_USD)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not math.isfinite(args.min_tvl_usd) or args.min_tvl_usd < 0:
        raise SystemExit("--min-tvl-usd must be finite and non-negative")
    now = datetime.now(timezone.utc).isoformat()
    if args.input:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        source = str(args.input)
    else:
        snapshot = fetch_snapshot()
        source = DEFILLAMA_POOLS_URL
    rows = build_universe(snapshot, min_tvl_usd=args.min_tvl_usd)
    summary = write_outputs(
        rows, out_dir=args.out_dir, as_of=now, input_source=source, min_tvl_usd=args.min_tvl_usd,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
