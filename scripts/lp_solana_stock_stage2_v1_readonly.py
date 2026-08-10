#!/usr/bin/env python3
"""Read-only Solana Stage-2 resolver for stock-token Raydium/Orca pools.

DefiLlama UUIDs are never used as Solana addresses.  A pair is resolved through
the protocol's public API, matched against the snapshot TVL, then independently
checked on chain: pool owner, executable program, vault owners and mint owners.
Only constant-product pools receive v2 IL economics here.  CLMM records remain
fail-closed until a position range and raw swap replay are both available.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_rpc_pool_v1_readonly import RpcPool


RAYDIUM_MINT_URL = "https://api-v3.raydium.io/pools/info/mint"
RAYDIUM_KEYS_URL = "https://api-v3.raydium.io/pools/key/ids"
ORCA_POOLS_URL = "https://api.orca.so/v2/solana/pools"
ORCA_WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}
LOADER_OWNERS = {
    "BPFLoader2111111111111111111111111111111111",
    "BPFLoaderUpgradeab1e11111111111111111111111",
}
USER_AGENT = "lpbot-solana-stock-stage2/1"
MAX_TVL_RELATIVE_ERROR = 0.15


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "pools", "data"):
            if isinstance(payload.get(key), list):
                return _rows(payload[key])
    raise ValueError("universe must contain records")


def _http_json(url: str, *, attempts: int = 4) -> Any:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except Exception as exc:  # network failures are evidence, not passes
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"HTTP read failed for {url}: {last}")


def v2_il(price_ratio: float) -> float:
    """Signed LP-vs-HODL return; zero at k=1 and negative otherwise."""
    ratio = float(price_ratio)
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("price_ratio must be finite and positive")
    return 2.0 * math.sqrt(ratio) / (1.0 + ratio) - 1.0


def _relative_error(value: Any, target: Any) -> float:
    try:
        observed, wanted = float(value), float(target)
    except (TypeError, ValueError):
        return math.inf
    if not math.isfinite(observed) or not math.isfinite(wanted) or wanted <= 0:
        return math.inf
    return abs(observed - wanted) / wanted


def _select_unique(candidates: list[dict[str, Any]], target_tvl: Any) -> dict[str, Any]:
    ranked = sorted(candidates, key=lambda row: _relative_error(row.get("tvl_usd"), target_tvl))
    if not ranked:
        raise ValueError("NO_PROTOCOL_POOL_FOR_TOKEN_PAIR")
    best_error = _relative_error(ranked[0].get("tvl_usd"), target_tvl)
    if best_error > MAX_TVL_RELATIVE_ERROR:
        raise ValueError(f"NO_TVL_MATCH_WITHIN_{MAX_TVL_RELATIVE_ERROR:.0%}")
    if len(ranked) > 1:
        second_error = _relative_error(ranked[1].get("tvl_usd"), target_tvl)
        if second_error <= MAX_TVL_RELATIVE_ERROR and second_error - best_error < 0.02:
            raise ValueError("AMBIGUOUS_PROTOCOL_POOL_TVL_MATCH")
    result = dict(ranked[0])
    result["snapshot_tvl_relative_error"] = best_error
    return result


def _raydium_candidates(mint_a: str, mint_b: str, http: Callable[[str], Any]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "mint1": mint_a, "mint2": mint_b, "poolType": "all",
        "poolSortField": "default", "sortType": "desc", "pageSize": 100, "page": 1,
    })
    payload = http(f"{RAYDIUM_MINT_URL}?{query}")
    raw = ((payload or {}).get("data") or {}).get("data") or []
    output = []
    for row in raw:
        day = row.get("day") or {}
        pool_type = "amm_constant_product" if str(row.get("type")).lower() in {
            "standard", "constantproduct", "cpmm",
        } else "clmm" if str(row.get("type")).lower() == "concentrated" else "unknown"
        output.append({
            "protocol": "raydium", "pool_address": row.get("id"),
            "program_id": row.get("programId"), "protocol_type": pool_type,
            "mint_a": (row.get("mintA") or {}).get("address"),
            "mint_b": (row.get("mintB") or {}).get("address"),
            "mint_a_owner": (row.get("mintA") or {}).get("programId"),
            "mint_b_owner": (row.get("mintB") or {}).get("programId"),
            "mint_a_tags": (row.get("mintA") or {}).get("tags") or [],
            "mint_b_tags": (row.get("mintB") or {}).get("tags") or [],
            "tvl_usd": row.get("tvl"), "price": row.get("price"),
            "fee_rate": row.get("feeRate"), "volume_24h_usd": day.get("volume"),
            "fees_24h_usd": day.get("volumeFee"),
            "official_fee_apr_pct": day.get("feeApr"),
            "price_min_24h": day.get("priceMin"), "price_max_24h": day.get("priceMax"),
            "reserve_a_ui": row.get("mintAmountA"), "reserve_b_ui": row.get("mintAmountB"),
        })
    return output


def _orca_candidates(mint_a: str, mint_b: str, http: Callable[[str], Any]) -> list[dict[str, Any]]:
    pair = f"{mint_a},{mint_b}"
    payload = http(f"{ORCA_POOLS_URL}?{urllib.parse.urlencode({'tokensBothOf': pair})}")
    output = []
    for row in (payload or {}).get("data") or []:
        stats = (row.get("stats") or {}).get("24h") or {}
        output.append({
            "protocol": "orca", "pool_address": row.get("address"),
            "program_id": ORCA_WHIRLPOOL_PROGRAM, "protocol_type": "clmm",
            "mint_a": row.get("tokenMintA"), "mint_b": row.get("tokenMintB"),
            "mint_a_owner": (row.get("tokenA") or {}).get("programId"),
            "mint_b_owner": (row.get("tokenB") or {}).get("programId"),
            "mint_a_tags": (row.get("tokenA") or {}).get("tags") or [],
            "mint_b_tags": (row.get("tokenB") or {}).get("tags") or [],
            "vault_a": row.get("tokenVaultA"), "vault_b": row.get("tokenVaultB"),
            "tvl_usd": row.get("tvlUsdc"), "price": row.get("price"),
            "fee_rate": (float(row["feeRate"]) / 1_000_000 if row.get("feeRate") is not None else None),
            "volume_24h_usd": stats.get("volume"), "fees_24h_usd": stats.get("fees"),
            "price_change_24h": stats.get("priceDelta"),
            "price_history_7d": row.get("priceHistory7d") or [],
        })
    return output


def resolve_pool(record: Mapping[str, Any], http: Callable[[str], Any] = _http_json) -> dict[str, Any]:
    tokens = list(record.get("underlyingTokens") or record.get("underlying_tokens") or [])
    if len(tokens) != 2 or any(not token for token in tokens):
        raise ValueError("EXACTLY_TWO_UNDERLYING_MINTS_REQUIRED")
    project = str(record.get("project") or "").lower()
    if project == "raydium-amm" or "raydium" in project:
        selected = _select_unique(_raydium_candidates(tokens[0], tokens[1], http), record.get("tvlUsd", record.get("tvl_usd")))
        keys = http(f"{RAYDIUM_KEYS_URL}?{urllib.parse.urlencode({'ids': selected['pool_address']})}")
        key_rows = (keys or {}).get("data") or []
        if len(key_rows) != 1:
            raise ValueError("RAYDIUM_POOL_KEYS_NOT_UNIQUE")
        vault = key_rows[0].get("vault") or {}
        selected["vault_a"], selected["vault_b"] = vault.get("A"), vault.get("B")
    elif project == "orca-dex" or "orca" in project:
        selected = _select_unique(_orca_candidates(tokens[0], tokens[1], http), record.get("tvlUsd", record.get("tvl_usd")))
    else:
        raise ValueError("UNSUPPORTED_SOLANA_PROTOCOL")
    selected["llama_pool_id"] = record.get("pool") or record.get("pool_id") or record.get("llama_pool_id")
    selected["symbol"] = record.get("symbol")
    selected["tier"] = record.get("tier") or record.get("stock_tier")
    selected["llama_tvl_usd"] = record.get("tvlUsd", record.get("tvl_usd"))
    selected["llama_apy_pct"] = record.get("apy", record.get("apy_total"))
    return selected


def verify_onchain(pool: Mapping[str, Any], rpc: RpcPool) -> dict[str, Any]:
    addresses = [
        pool.get("pool_address"), pool.get("program_id"), pool.get("vault_a"),
        pool.get("vault_b"), pool.get("mint_a"), pool.get("mint_b"),
    ]
    if any(not address for address in addresses):
        return {"passed": False, "reason": "MISSING_ACCOUNT_ADDRESS", "accounts": {}}
    values = rpc.call("getMultipleAccounts", [addresses, {"encoding": "base64", "commitment": "confirmed"}])
    if not isinstance(values, dict) or len(values.get("value") or []) != len(addresses):
        return {"passed": False, "reason": "MALFORMED_GET_MULTIPLE_ACCOUNTS", "accounts": {}}
    accounts = dict(zip(addresses, values["value"]))
    if any(value is None for value in accounts.values()):
        return {"passed": False, "reason": "ACCOUNT_NOT_FOUND", "accounts": accounts}
    program = accounts[str(pool["program_id"])]
    checks = {
        "pool_owner_is_program": accounts[str(pool["pool_address"])].get("owner") == pool.get("program_id"),
        "program_executable": program.get("executable") is True,
        "program_loader_owner": program.get("owner") in LOADER_OWNERS,
        "vault_a_token_owned": accounts[str(pool["vault_a"])].get("owner") in TOKEN_PROGRAMS,
        "vault_b_token_owned": accounts[str(pool["vault_b"])].get("owner") in TOKEN_PROGRAMS,
        "mint_a_owner_matches_api": accounts[str(pool["mint_a"])].get("owner") == pool.get("mint_a_owner"),
        "mint_b_owner_matches_api": accounts[str(pool["mint_b"])].get("owner") == pool.get("mint_b_owner"),
    }
    return {
        "passed": all(checks.values()), "reason": "PASS" if all(checks.values()) else "FAIL_CLOSED",
        "checks": checks,
        "slot_context": values.get("context"),
        "account_owners": {address: value.get("owner") for address, value in accounts.items()},
    }


def _account_keys(transaction: Mapping[str, Any]) -> list[str]:
    message = (((transaction.get("transaction") or {}).get("message")) or {})
    output = []
    for item in message.get("accountKeys") or []:
        output.append(str(item.get("pubkey")) if isinstance(item, Mapping) else str(item))
    return output


def _token_balance_map(rows: Any) -> dict[tuple[int, str], tuple[int, int]]:
    output: dict[tuple[int, str], tuple[int, int]] = {}
    for row in rows or []:
        try:
            ui = row["uiTokenAmount"]
            output[(int(row["accountIndex"]), str(row["mint"]))] = (
                int(ui["amount"]), int(ui["decimals"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return output


def replay_recent_swaps(pool: Mapping[str, Any], rpc: RpcPool, *, signature_limit: int = 3) -> dict[str, Any]:
    """Replay a bounded set of real transactions touching the pool vaults.

    This is deliberately not a transaction-count extrapolator.  It proves that
    actual swap transactions and vault deltas can be decoded.  Token-2022
    Scaled-UI mints remain economically incomplete until their multiplier is
    attached; raw balances are never presented as adjusted economic units.
    """
    if signature_limit <= 0:
        return {"status": "NOT_REQUESTED", "swap_count": 0, "transactions_checked": 0}
    signatures = rpc.call("getSignaturesForAddress", [
        pool["pool_address"], {"limit": signature_limit, "commitment": "confirmed"},
    ])
    if not isinstance(signatures, list):
        return {"status": "FAIL_CLOSED", "reason": "MALFORMED_SIGNATURES", "swap_count": 0}
    swaps = []
    for item in signatures:
        signature = item.get("signature") if isinstance(item, Mapping) else None
        if not signature:
            continue
        tx = rpc.call("getTransaction", [
            signature, {"encoding": "jsonParsed", "commitment": "confirmed",
                        "maxSupportedTransactionVersion": 0},
        ])
        if not isinstance(tx, Mapping):
            continue
        meta = tx.get("meta") or {}
        logs = [str(log).lower() for log in meta.get("logMessages") or []]
        if not any("swap" in log for log in logs):
            continue
        keys = _account_keys(tx)
        vault_indexes = {
            index for index, key in enumerate(keys)
            if key in {pool.get("vault_a"), pool.get("vault_b")}
        }
        pre = _token_balance_map(meta.get("preTokenBalances"))
        post = _token_balance_map(meta.get("postTokenBalances"))
        deltas = {}
        for key in set(pre) | set(post):
            index, mint = key
            if index not in vault_indexes:
                continue
            before, decimals = pre.get(key, (0, post.get(key, (0, 0))[1]))
            after, decimals_after = post.get(key, (0, decimals))
            decimals = max(decimals, decimals_after)
            deltas[mint] = (after - before) / (10 ** decimals)
        delta_a = deltas.get(pool.get("mint_a"))
        delta_b = deltas.get(pool.get("mint_b"))
        price = None
        if delta_a not in (None, 0) and delta_b not in (None, 0):
            price = abs(delta_b / delta_a)
        swaps.append({
            "signature": signature, "slot": tx.get("slot"), "block_time": tx.get("blockTime"),
            "vault_delta_a_raw_ui": delta_a, "vault_delta_b_raw_ui": delta_b,
            "raw_ui_price_b_per_a": price,
        })
    scaled_ui = (
        "scaledUiAmountConfig" in (pool.get("mint_a_tags") or [])
        or "scaledUiAmountConfig" in (pool.get("mint_b_tags") or [])
    )
    return {
        "status": "PASS" if swaps else "NO_SWAP_IN_BOUNDED_SAMPLE",
        "transactions_checked": len(signatures), "swap_count": len(swaps),
        "scaled_ui_multiplier_required": scaled_ui,
        "scaled_ui_multiplier_applied": False if scaled_ui else None,
        "economic_price_complete": bool(swaps) and not scaled_ui,
        "swaps": swaps,
    }


def recompute_economics(pool: Mapping[str, Any]) -> dict[str, Any]:
    try:
        tvl = float(pool["tvl_usd"])
        fees = float(pool["fees_24h_usd"])
        volume = float(pool["volume_24h_usd"])
        fee_rate = float(pool["fee_rate"])
    except (KeyError, TypeError, ValueError):
        return {"passed": False, "reason": "MISSING_REAL_FEE_INPUTS"}
    if tvl <= 0 or fees < 0 or volume < 0 or not 0 <= fee_rate <= 1:
        return {"passed": False, "reason": "INVALID_REAL_FEE_INPUTS"}
    fee_apr_pct = fees / tvl * 365.0 * 100.0
    volume_fee_apr_pct = volume * fee_rate / tvl * 365.0 * 100.0
    result = {
        "real_tvl_usd": tvl, "real_volume_24h_usd": volume,
        "real_fees_24h_usd": fees, "fee_rate": fee_rate,
        "recomputed_fee_apr_pct": fee_apr_pct,
        "volume_times_fee_recomputed_apr_pct": volume_fee_apr_pct,
        "fee_recompute_relative_difference": (
            abs(fee_apr_pct - volume_fee_apr_pct) / fee_apr_pct if fee_apr_pct else 0.0),
        "source_semantics": "official_protocol_24h_swap_aggregates_cross_checked_on_chain",
    }
    if pool.get("protocol_type") != "amm_constant_product":
        result.update({
            "passed": False, "reason": "CLMM_RANGE_AND_RAW_SWAP_REPLAY_REQUIRED",
            "il_24h_worst": None,
        })
        return result
    try:
        low, high = float(pool["price_min_24h"]), float(pool["price_max_24h"])
        if low <= 0 or high <= 0 or high < low:
            raise ValueError
        ratio = high / low
        il = v2_il(ratio)
    except (KeyError, TypeError, ValueError):
        result.update({"passed": False, "reason": "AMM_PRICE_PATH_UNAVAILABLE", "il_24h_worst": None})
        return result
    result.update({
        "passed": True, "reason": "PASS", "price_ratio_24h_worst": ratio,
        "il_24h_worst": il, "il_formula": "2*sqrt(k)/(1+k)-1",
        "exit_depth_usd": tvl / 2.0,
    })
    return result


def assess(record: Mapping[str, Any], rpc: RpcPool,
           http: Callable[[str], Any] = _http_json, *, replay_limit: int = 0) -> dict[str, Any]:
    base = {
        "llama_pool_id": record.get("pool") or record.get("pool_id") or record.get("llama_pool_id"),
        "symbol": record.get("symbol"), "tier": record.get("tier") or record.get("stock_tier"),
        "stage2_pass": False,
    }
    try:
        resolved = resolve_pool(record, http)
        onchain = verify_onchain(resolved, rpc)
        replay = replay_recent_swaps(resolved, rpc, signature_limit=replay_limit)
        economics = recompute_economics(resolved)
        base.update({"resolved": resolved, "onchain": onchain, "swap_replay": replay,
                     "economics": economics})
        base["stage2_pass"] = (
            onchain.get("passed") is True
            and economics.get("passed") is True
            and replay.get("swap_count", 0) > 0
            and replay.get("economic_price_complete") is True
        )
        base["reason"] = "PASS" if base["stage2_pass"] else "FAIL_CLOSED"
    except Exception as exc:
        base["reason"] = f"FAIL_CLOSED:{type(exc).__name__}:{exc}"
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--pool-id", default="", help="optional exact DefiLlama UUID for bounded replay evidence")
    parser.add_argument("--replay-limit", type=int, default=3,
                        help="recent pool transactions checked for real swaps; 0 disables")
    args = parser.parse_args()
    records = [row for row in _rows(json.loads(args.universe.read_text()))
               if str(row.get("chain")).lower() == "solana"]
    if args.pool_id:
        records = [row for row in records
                   if str(row.get("pool") or row.get("pool_id") or row.get("llama_pool_id")) == args.pool_id]
    if args.limit > 0:
        records = records[:args.limit]
    rpc = RpcPool("solana")
    results = [assess(record, rpc, replay_limit=args.replay_limit) for record in records]
    payload = {
        "universe_count": len(records), "stage2_pass_count": sum(row["stage2_pass"] for row in results),
        "tier_counts": {
            tier: {
                "total": sum(str(row.get("tier")).upper() == tier for row in results),
                "stage2_pass": sum(str(row.get("tier")).upper() == tier and row["stage2_pass"] for row in results),
            } for tier in ("A", "B", "C")
        },
        "rpc_health": rpc.health_snapshot(), "results": results,
        "signed": False, "broadcast_count": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({key: payload[key] for key in ("universe_count", "stage2_pass_count", "tier_counts")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
