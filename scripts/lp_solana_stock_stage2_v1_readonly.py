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
import base64
import binascii
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
from scripts.lp_netcover_inputs_v1_readonly import assemble_clmm_netcover_inputs
from scripts.lp_solana_token_constants_v1_readonly import STABLE_MINTS
from scripts.lp_vol_range_sizer_v1_readonly import recommend_range_pct


RAYDIUM_MINT_URL = "https://api-v3.raydium.io/pools/info/mint"
RAYDIUM_KEYS_URL = "https://api-v3.raydium.io/pools/key/ids"
ORCA_POOLS_URL = "https://api.orca.so/v2/solana/pools"
ORCA_WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
RAYDIUM_CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
RAYDIUM_CLMM_ACCOUNT_SIZE = 1544
ORCA_WHIRLPOOL_ACCOUNT_SIZE = 653
ORCA_WHIRLPOOL_DISCRIMINATOR = bytes.fromhex("3f95d10ce1806309")
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
DEFAULT_REPLAY_LIMIT = 60
MIN_SIGMA_SWAP_COUNT = 20
MIN_SIGMA_SPAN_SECONDS = 60 * 60
MIN_RECOMMENDED_RANGE_PCT = 0.1


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
    selected["llama_apy_base_pct"] = record.get("apyBase", record.get("apy_base"))
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


def _base64_account(response: Mapping[str, Any], *, owner: str, space: int) -> bytes:
    """Validate a program-owned account and return its canonical bytes."""
    value = response.get("value") if isinstance(response, Mapping) else None
    if not isinstance(value, Mapping):
        raise ValueError("POOL_ACCOUNT_UNAVAILABLE")
    if value.get("owner") != owner:
        raise ValueError("POOL_ACCOUNT_OWNER_MISMATCH")
    if value.get("space") != space:
        raise ValueError("POOL_ACCOUNT_LAYOUT_SIZE_MISMATCH")
    encoded = value.get("data")
    if (not isinstance(encoded, list) or len(encoded) != 2
            or encoded[1] != "base64" or not isinstance(encoded[0], str)):
        raise ValueError("POOL_ACCOUNT_BASE64_REQUIRED")
    try:
        raw = base64.b64decode(encoded[0], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("POOL_ACCOUNT_BASE64_MALFORMED") from exc
    if len(raw) != space:
        raise ValueError("POOL_ACCOUNT_DECODED_SIZE_MISMATCH")
    return raw


def _mint_decimals(rpc: RpcPool, mint: str) -> int:
    response = rpc.call("getAccountInfo", [
        mint, {"encoding": "jsonParsed", "commitment": "confirmed"},
    ])
    try:
        decimals = int(response["value"]["data"]["parsed"]["info"]["decimals"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("MINT_DECIMALS_UNAVAILABLE") from exc
    if decimals < 0 or decimals > 30:
        raise ValueError("MINT_DECIMALS_INVALID")
    return decimals


def _decode_orca_pool_state(response: Mapping[str, Any], *, decimals_a: int,
                            decimals_b: int) -> dict[str, Any]:
    raw = _base64_account(
        response, owner=ORCA_WHIRLPOOL_PROGRAM, space=ORCA_WHIRLPOOL_ACCOUNT_SIZE
    )
    if raw[:8] != ORCA_WHIRLPOOL_DISCRIMINATOR:
        raise ValueError("ORCA_WHIRLPOOL_DISCRIMINATOR_MISMATCH")
    liquidity = int.from_bytes(raw[49:65], "little", signed=False)
    sqrt_price_x64 = int.from_bytes(raw[65:81], "little", signed=False)
    tick_current = int.from_bytes(raw[81:85], "little", signed=True)
    if liquidity <= 0 or sqrt_price_x64 <= 0:
        raise ValueError("ORCA_ACTIVE_LIQUIDITY_OR_PRICE_UNAVAILABLE")
    return {
        "protocol_type": "clmm", "state_protocol": "orca_whirlpool",
        "active_liquidity_raw": liquidity, "sqrt_price_x64": sqrt_price_x64,
        "tick_current": tick_current, "decimals_a": decimals_a,
        "decimals_b": decimals_b,
    }


def _decode_raydium_pool_state(response: Mapping[str, Any], *, decimals_a: int,
                               decimals_b: int) -> dict[str, Any]:
    raw = _base64_account(
        response, owner=RAYDIUM_CLMM_PROGRAM, space=RAYDIUM_CLMM_ACCOUNT_SIZE
    )
    # PoolInfoLayout has an 8-byte discriminator plus a one-byte bump.  The
    # following offsets are pinned to Raydium's published SDK layout.
    # mint decimals 233/234, tick spacing 235..237, liquidity 237..253,
    # sqrtPriceX64 253..269, tickCurrent 269..273.
    liquidity = int.from_bytes(raw[237:253], "little", signed=False)
    sqrt_price_x64 = int.from_bytes(raw[253:269], "little", signed=False)
    tick_current = int.from_bytes(raw[269:273], "little", signed=True)
    if liquidity <= 0 or sqrt_price_x64 <= 0:
        raise ValueError("RAYDIUM_ACTIVE_LIQUIDITY_OR_PRICE_UNAVAILABLE")
    return {
        "protocol_type": "clmm", "state_protocol": "raydium_clmm",
        "active_liquidity_raw": liquidity, "sqrt_price_x64": sqrt_price_x64,
        "tick_current": tick_current, "tick_spacing": int.from_bytes(raw[235:237], "little"),
        "decimals_a": decimals_a, "decimals_b": decimals_b,
    }


def read_clmm_state(pool: Mapping[str, Any], rpc: RpcPool) -> dict[str, Any]:
    """Read the current active CLMM state from the protocol-owned account."""
    protocol = str(pool.get("protocol") or "").lower()
    if protocol == "orca":
        owner, decoder = ORCA_WHIRLPOOL_PROGRAM, _decode_orca_pool_state
    elif protocol == "raydium":
        owner, decoder = RAYDIUM_CLMM_PROGRAM, _decode_raydium_pool_state
    else:
        raise ValueError("CLMM_PROTOCOL_STATE_DECODER_UNAVAILABLE")
    if str(pool.get("program_id") or "") != owner:
        raise ValueError("CLMM_PROGRAM_ID_MISMATCH")
    decimals_a = _mint_decimals(rpc, str(pool["mint_a"]))
    decimals_b = _mint_decimals(rpc, str(pool["mint_b"]))
    response = rpc.call("getAccountInfo", [
        pool["pool_address"], {"encoding": "base64", "commitment": "confirmed"},
    ])
    state = decoder(response, decimals_a=decimals_a, decimals_b=decimals_b)
    context = response.get("context") if isinstance(response, Mapping) else None
    slot = context.get("slot") if isinstance(context, Mapping) else None
    if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
        raise ValueError("CLMM_STATE_SLOT_UNAVAILABLE")
    # These labels are attached only after both the protocol account owner and
    # the confirmed RPC account payload have been verified above.  Swap replay
    # evidence is intentionally labelled separately by the stage-2 assembler.
    return {
        **state,
        "state_slot": slot,
        "state_owner": owner,
        "sqrt_price_x64_source": "measured:pool.sqrt_price_x64",
        "active_liquidity_raw_source": "measured:pool.liquidity",
    }


def replay_recent_swaps(pool: Mapping[str, Any], rpc: RpcPool, *, signature_limit: int = DEFAULT_REPLAY_LIMIT) -> dict[str, Any]:
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


def _finite_positive(value: Any, reason: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(reason)
    return number


def _clmm_active_depth(pool: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, float]:
    """Value current active liquidity only when one leg has an on-chain stable anchor.

    This is deliberately a lower-bound depth: only the immediately active
    liquidity is counted and only the stable quote-leg reserve is used for an
    exit.  TVL and protocol API volume are never substituted for depth.
    """
    liquidity = _finite_positive(state.get("active_liquidity_raw"), "ACTIVE_LIQUIDITY_UNAVAILABLE")
    sqrt_price = _finite_positive(state.get("sqrt_price_x64"), "CLMM_SQRT_PRICE_UNAVAILABLE")
    try:
        dec_a, dec_b = int(state["decimals_a"]), int(state["decimals_b"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("MINT_DECIMALS_UNAVAILABLE") from exc
    if not 0 <= dec_a <= 30 or not 0 <= dec_b <= 30:
        raise ValueError("MINT_DECIMALS_INVALID")
    root = sqrt_price / float(1 << 64)
    amount_a = liquidity / root / (10 ** dec_a)
    amount_b = liquidity * root / (10 ** dec_b)
    price_b_per_a = root * root * (10 ** (dec_a - dec_b))
    mint_a, mint_b = str(pool.get("mint_a")), str(pool.get("mint_b"))
    if mint_b in STABLE_MINTS:
        stable_reserve_usd = amount_b
        active_notional_usd = amount_b + amount_a * price_b_per_a
    elif mint_a in STABLE_MINTS:
        stable_reserve_usd = amount_a
        active_notional_usd = amount_a + amount_b / price_b_per_a
    else:
        raise ValueError("ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE")
    if not math.isfinite(stable_reserve_usd) or stable_reserve_usd <= 0:
        raise ValueError("ACTIVE_STABLE_LIQUIDITY_UNAVAILABLE")
    # A one-sided exit consumes only quote-side depth; retain a 50% reserve
    # haircut before it becomes an advertised executable depth.
    return {
        "active_liquidity_notional_usd": active_notional_usd,
        "exit_depth_usd": stable_reserve_usd * 0.5,
        "price_b_per_a": price_b_per_a,
    }


def _replay_price_path(
    replay: Mapping[str, Any], *, require_sigma_sample: bool = False,
) -> dict[str, float]:
    samples: list[tuple[int | None, float]] = []
    for swap in replay.get("swaps") or []:
        try:
            price = float(swap.get("raw_ui_price_b_per_a"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        try:
            block_time = int(swap.get("block_time"))
        except (TypeError, ValueError):
            block_time = None
        samples.append((block_time if block_time and block_time > 0 else None, price))
    if require_sigma_sample:
        samples = sorted((time, price) for time, price in samples if time is not None)
    prices = [price for _block_time, price in samples]
    count = len(prices)
    span_seconds = (
        int(samples[-1][0]) - int(samples[0][0])
        if require_sigma_sample and count >= 2 else 0
    )
    span_hours = span_seconds / 3600.0
    if require_sigma_sample and (
        count < MIN_SIGMA_SWAP_COUNT or span_seconds < MIN_SIGMA_SPAN_SECONDS
    ):
        raise ValueError(f"SIGMA_SAMPLE_INSUFFICIENT:n={count},span={span_hours:.1f}h")
    if count < 2:
        raise ValueError("RAW_SWAP_PRICE_PATH_INSUFFICIENT")
    log_returns = [math.log(current / prior) for prior, current in zip(prices, prices[1:])]
    variance = sum(value * value for value in log_returns) / len(log_returns)
    return {
        "replay_price_min": min(prices), "replay_price_max": max(prices),
        "sigma_pair": math.sqrt(variance),
        "price_ratio_worst": max(prices) / min(prices),
        "latest_swap_price_b_per_a": prices[-1],
        "sigma_swap_count": count,
        "sigma_sample_span_hours": span_hours,
    }


def recompute_clmm_economics(
    pool: Mapping[str, Any], state: Mapping[str, Any], replay: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce CLMM replay economics without replacing the shared NetCover model."""
    try:
        tvl = _finite_positive(pool.get("tvl_usd"), "MISSING_REAL_FEE_INPUTS")
        fees = float(pool["fees_24h_usd"])
        volume = float(pool["volume_24h_usd"])
        fee_rate = float(pool["fee_rate"])
        if not all(math.isfinite(value) and value >= 0 for value in (fees, volume)):
            raise ValueError("INVALID_REAL_FEE_INPUTS")
        if not math.isfinite(fee_rate) or not 0 <= fee_rate <= 1:
            raise ValueError("INVALID_REAL_FEE_INPUTS")
        fee_apr_pct = fees / tvl * 365.0 * 100.0
        base = {
            "real_tvl_usd": tvl, "real_volume_24h_usd": volume,
            "real_fees_24h_usd": fees, "fee_rate": fee_rate,
            "recomputed_fee_apr_pct": fee_apr_pct,
            "volume_times_fee_recomputed_apr_pct": volume * fee_rate / tvl * 365.0 * 100.0,
            "fee_recompute_relative_difference": (
                abs(fee_apr_pct - volume * fee_rate / tvl * 365.0 * 100.0) / fee_apr_pct
                if fee_apr_pct else 0.0
            ),
            "source_semantics": "official_protocol_24h_swap_aggregates_cross_checked_on_chain",
        }
    except ValueError as exc:
        return {"passed": False, "reason": str(exc)}
    try:
        depth = _clmm_active_depth(pool, state)
        path = _replay_price_path(replay, require_sigma_sample=True)
        range_pct = recommend_range_pct(path["sigma_pair"], 168.0 / 24.0)
        if not math.isfinite(range_pct) or range_pct < MIN_RECOMMENDED_RANGE_PCT:
            raise ValueError(f"RECOMMENDED_RANGE_DEGENERATE:range={range_pct:.4f}%")
        il_fraction = v2_il(path["price_ratio_worst"])
        # This is a conservative path-loss input.  The range-sized fee share
        # itself remains exclusively calculated by assemble_clmm_netcover_inputs.
        il_apr_pct = abs(il_fraction) * 365.0 * 100.0
        position_usd = 5.0
        slippage_bps = position_usd / depth["exit_depth_usd"] * 10_000.0
    except ValueError as exc:
        return {**base, "passed": False, "reason": str(exc)}
    return {
        **base,
        **depth,
        **path,
        "passed": True,
        "reason": "PASS",
        "il_24h_worst": il_fraction,
        "il_apr_pct": il_apr_pct,
        "recommend_range_pct": range_pct,
        "recommend_range_min_pct": MIN_RECOMMENDED_RANGE_PCT,
        "exit_slippage_bps": slippage_bps,
        "exit_depth_model": "active_stable_quote_liquidity_50pct_haircut",
        "fee_attribution": "official_protocol_24h_fees_with_raw_swap_path_validation",
    }


def assemble_clmm_stage2_netcover(
    pool: Mapping[str, Any], state: Mapping[str, Any], economics: Mapping[str, Any],
) -> dict[str, Any]:
    """Use the common CLMM assembler; unavailable inputs stay explicit and closed."""
    if economics.get("passed") is not True:
        return {"passed": False, "reason": str(economics.get("reason") or "CLMM_ECONOMICS_UNAVAILABLE")}
    record = {
        "chain": "Solana", "protocol_type": "clmm", "profile": "PASSIVE_CL",
        "holding_horizon_hours": 168.0, "is_new_pool": None,
        "fee_apr_24h": economics.get("recomputed_fee_apr_pct"),
        # The supplied DefiLlama base-APR window remains a second, independent
        # conservative anchor; the common assembler takes min(24h, base APR).
        "fee_apr_7d": pool.get("llama_apy_base_pct"),
        "sigma_pair": economics.get("sigma_pair"), "il_apr": economics.get("il_apr_pct"),
        "l_active_raw": state.get("active_liquidity_raw"),
        "l_active_raw_source": state.get("active_liquidity_raw_source"),
        "sqrt_price_x64": state.get("sqrt_price_x64"),
        "sqrt_price_x64_source": state.get("sqrt_price_x64_source"),
        "last_swap_liquidity_raw": state.get("active_liquidity_raw"),
        "last_swap_price_token1_per_token0": economics.get("latest_swap_price_b_per_a"),
        "last_swap_cost_state_source": "measured:latest_decoded_solana_swap_event",
        "token0": pool.get("mint_a"),
        "token1": pool.get("mint_b"), "dec0": state.get("decimals_a"),
        "dec1": state.get("decimals_b"), "fee_tier": pool.get("fee_rate"),
        "tvlUsd": pool.get("tvl_usd"),
        "active_liquidity_notional_usd": economics.get("active_liquidity_notional_usd"),
    }
    try:
        assembled = assemble_clmm_netcover_inputs(record, position_usd=5.0)
    except (ArithmeticError, TypeError, ValueError) as exc:
        return {"passed": False, "reason": f"NETCOVER_ASSEMBLY_FAILED:{exc}"}
    missing = [name for name, value in assembled.items()
               if name.endswith("_usd") and value is None]
    return {
        "passed": not missing, "reason": "PASS" if not missing else "NETCOVER_INPUT_MISSING:" + ",".join(missing),
        "inputs": assembled,
    }


def solana_exit_and_sell_evidence(
    replay: Mapping[str, Any], economics: Mapping[str, Any],
    simulation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate raw Solana replay/simulation evidence into Tier-C fields.

    A caller may provide only a serialized, unsigned transaction generated by
    a protocol-owned quote builder.  This function never signs or broadcasts;
    absent a simulation response it intentionally records a concrete failure.
    """
    try:
        path = _replay_price_path(replay)
        verdict = "EXITABLE_CLEAN" if economics.get("exit_slippage_bps") is not None else "GAPPED"
        exit_reason = "PASS" if verdict == "EXITABLE_CLEAN" else str(economics.get("reason"))
    except ValueError as exc:
        verdict, exit_reason = "NO_DATA", str(exc)
    response = simulation if isinstance(simulation, Mapping) else None
    value = response.get("value") if response else None
    simulation_ok = isinstance(value, Mapping) and value.get("err") is None
    return {
        "exit_verdict": verdict, "exit_verdict_reason": exit_reason,
        "exit_slippage_bps": economics.get("exit_slippage_bps"),
        "exit_slippage_reason": (
            "PASS" if economics.get("exit_slippage_bps") is not None
            else str(economics.get("reason") or "EXIT_SLIPPAGE_MODEL_UNAVAILABLE")
        ),
        "sell_simulation_ok": simulation_ok,
        "sell_simulation_reason": (
            "PASS" if simulation_ok else "FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE"
            if response is None else "FAIL_CLOSED_SIMULATE_TRANSACTION_ERROR"
        ),
        "known_honeypot": False if simulation_ok else None,
        "sell_tax_pct": 0 if simulation_ok else None,
        "simulation_broadcast_count": 0,
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
            "passed": False, "reason": "CLMM_ACTIVE_STATE_AND_RAW_SWAP_REPLAY_REQUIRED",
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


def _stage2_failure_reason(
    onchain: Mapping[str, Any], economics: Mapping[str, Any],
    replay: Mapping[str, Any], netcover: Mapping[str, Any] | None,
) -> str:
    """Return the reason belonging to the first failed conjunct only."""
    if onchain.get("passed") is not True:
        return str(onchain.get("reason") or "ONCHAIN_VERIFICATION_FAILED")
    if economics.get("passed") is not True:
        return str(economics.get("reason") or "ECONOMICS_UNAVAILABLE")
    if replay.get("swap_count", 0) <= 0:
        return str(replay.get("reason") or "RAW_SWAP_SAMPLE_EMPTY")
    if replay.get("economic_price_complete") is not True:
        return str(replay.get("reason") or "ECONOMIC_PRICE_INCOMPLETE")
    if netcover is not None and netcover.get("passed") is not True:
        return str(netcover.get("reason") or "NETCOVER_UNAVAILABLE")
    return "STAGE2_CONJUNCTION_FAILED"


def assess(record: Mapping[str, Any], rpc: RpcPool,
           http: Callable[[str], Any] = _http_json, *, replay_limit: int = 0) -> dict[str, Any]:
    base = {
        "llama_pool_id": record.get("pool") or record.get("pool_id") or record.get("llama_pool_id"),
        "symbol": record.get("symbol"), "tier": record.get("tier") or record.get("stock_tier"),
        "stage2_pass": False,
    }
    try:
        resolved = resolve_pool(record, http)
        universe_protocol = str(record.get("protocol_type") or "").strip().lower()
        stage2_protocol = str(resolved.get("protocol_type") or "").strip().lower()
        reconciliation = {
            "universe_protocol_type": universe_protocol or None,
            "stage2_protocol_type": stage2_protocol or None,
            "matched": universe_protocol == stage2_protocol and bool(stage2_protocol),
        }
        base["protocol_type_reconciliation"] = reconciliation
        if not reconciliation["matched"]:
            base.update({
                "protocol_type_mismatch_alert": "PROTOCOL_TYPE_MISMATCH",
                "resolved": resolved,
                "reason": "PROTOCOL_TYPE_MISMATCH",
            })
            return base
        onchain = verify_onchain(resolved, rpc)
        replay = replay_recent_swaps(resolved, rpc, signature_limit=replay_limit)
        state: dict[str, Any] | None = None
        netcover: dict[str, Any] | None = None
        if stage2_protocol == "clmm":
            try:
                state = read_clmm_state(resolved, rpc)
                economics = recompute_clmm_economics(resolved, state, replay)
                netcover = assemble_clmm_stage2_netcover(resolved, state, economics)
            except Exception as exc:  # a per-pool acquisition failure is evidence
                economics = {
                    "passed": False,
                    "reason": f"CLMM_STATE_OR_REPLAY_UNAVAILABLE:{type(exc).__name__}:{exc}",
                }
                netcover = {"passed": False, "reason": str(economics["reason"])}
        else:
            economics = recompute_economics(resolved)
        base.update({
            "resolved": resolved, "onchain": onchain, "swap_replay": replay,
            "clmm_state": state, "economics": economics, "netcover": netcover,
            "exit_slippage_bps": economics.get("exit_slippage_bps"),
        })
        base.update(solana_exit_and_sell_evidence(replay, economics))
        base["stage2_pass"] = (
            onchain.get("passed") is True
            and economics.get("passed") is True
            and replay.get("swap_count", 0) > 0
            and replay.get("economic_price_complete") is True
            and (netcover is None or netcover.get("passed") is True)
        )
        if base["stage2_pass"]:
            base["reason"] = "PASS"
        else:
            base["reason"] = "FAIL_CLOSED:" + _stage2_failure_reason(
                onchain, economics, replay, netcover,
            )
    except Exception as exc:
        base["reason"] = f"FAIL_CLOSED:{type(exc).__name__}:{exc}"
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0,
                        help="skip this many filtered records before --limit; supports paced checkpoint runs")
    parser.add_argument("--pool-id", default="", help="optional exact DefiLlama UUID for bounded replay evidence")
    parser.add_argument("--protocol-type", default="",
                        help="optional universe-declared protocol type filter (for a CLMM-only replay)")
    parser.add_argument("--replay-limit", type=int, default=DEFAULT_REPLAY_LIMIT,
                        help="recent pool transactions checked for real swaps (default: 60); 0 disables")
    args = parser.parse_args()
    records = [row for row in _rows(json.loads(args.universe.read_text()))
               if str(row.get("chain")).lower() == "solana"]
    if args.protocol_type:
        requested_protocol = args.protocol_type.strip().lower()
        records = [row for row in records
                   if str(row.get("protocol_type") or "").strip().lower() == requested_protocol]
    if args.pool_id:
        records = [row for row in records
                   if str(row.get("pool") or row.get("pool_id") or row.get("llama_pool_id")) == args.pool_id]
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    if args.offset:
        records = records[args.offset:]
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
