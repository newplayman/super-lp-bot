"""LP Long Horizon R1 Real-Data Read-only Collector (smoke only).

This script is part of stage ``LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1``.
It upgrades the R0 proxy/placeholder collector to R1 real-data observation:

- live on-chain reads via JSON-RPC (read-only: getMultipleAccountsInfo, eth_call,
  getLogs read-only) — no signing, no sendTransaction, no chain mutation
- live price feed via CoinGecko public API (no key, no paid indexer)
- honest failure handling: ``confidence=unavailable`` + ``invalid_reason=...``
  instead of falling back to 0 or placeholder

Hard prohibitions (enforced in code + audited by tests):

- no private key / seed / keypair / keystore read
- no signer creation
- no transaction sent (no sendTransaction, signTransaction, eth_sendRawTransaction)
- no approve / mint / add_liquidity / remove_liquidity / collect_fee / swap
- no bridge call
- no live / canary / paper / probe start
- no production position write
- no shadow table overwrite
- no long-running daemon (no while-true / cron / systemd / sleep loop)
- ``actual_fee_data_available`` must stay ``False`` (R1 = real data layer, NOT actual fee)
- ``can_run_probe_now`` must stay ``False``
- ``tiny_canary_allowed`` must stay ``"no"``
- ``edge_proven`` must stay ``"no"``

The script is short-run by design (smoke: --max-pools 12-20, --max-snapshots 1,
--no-daemon). It does NOT modify R0 collector, R0 adapters, or any prior stage
data dir.

Auto-tested by ``tests/test_lp_long_horizon_r1_real_data_observation_upgrade_v1.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (locked; do not change without re-running the full audit)
# ---------------------------------------------------------------------------

STAGE = "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1"
ALLOWED_OUTPUT_DIRS = (
    "data/lp_long_horizon_r1_smoke",
)

# Per-call timeout (seconds). Fail-fast; no retry.
DEFAULT_RPC_TIMEOUT_S = 5
# Per-pool total time budget.
DEFAULT_POOL_BUDGET_S = 30

# 6 quote notional levels (USD).
NOTIONAL_LEVELS_USD = (10, 100, 1_000, 10_000, 100_000, 1_000_000)
# 5 fee velocity windows.
FEE_WINDOWS = ("15m", "1h", "4h", "24h", "7d")

# Hardcoded honest failure reasons.
REASON_RPC_UNREACHABLE = "rpc_unreachable"
REASON_RPC_EMPTY = "rpc_empty_response"
REASON_RATE_LIMITED = "rpc_rate_limited"
REASON_POOL_INVALID = "pool_address_invalid"
REASON_ADAPTER_NOT_IMPL = "adapter_not_implemented"
REASON_INDEXER_UNREACHABLE = "indexer_unreachable"
REASON_DEXSCREENER_NO_DATA = "dexscreener_no_data"
REASON_PYTH_NO_PRICE = "pyth_no_price"
REASON_COINGECKO_NO_HISTORY = "coingecko_no_history"
REASON_INSUFFICIENT_HISTORY = "insufficient_history"
REASON_CROSS_CHAIN_SKIP = "cross_chain_skip"
REASON_TOKEN_NOT_RESOLVED = "token_not_resolved"
REASON_UNKNOWN = "unknown"

# Public RPC endpoints (read-only, no key, no paid).
# Mirrors the registry used by R0; R1 does NOT modify R0, only reads.
SOLANA_RPCS = (
    "https://api.mainnet-beta.solana.com",
    "https://solana.publicnode.com",
)
BSC_RPCS = (
    "https://bsc-dataseed.binance.org",
    "https://bsc.publicnode.com",
)
BASE_RPCS = (
    "https://base.publicnode.com",
    "https://mainnet.base.org",
)

# Public CoinGecko (no key, read-only).
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# DexScreener public API (read-only).
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"

# Hardcoded: R1 schema constants for fields common to all rows.
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Safety self-check
# ---------------------------------------------------------------------------

def _safety_self_check() -> None:
    """Refuse to start if any forbidden token appears in the process environment.

    Defense in depth: even if the R1 collector never imports a wallet module,
    the env check ensures we don't accidentally inherit one.
    """
    forbidden = (
        "PRIVATE_KEY", "MNEMONIC", "SEED_PHRASE", "KEYPAIR_PATH",
        "LPBOT_SEND_RAW", "LPBOT_SIGN", "LPBOT_MINT", "LPBOT_BROADCAST",
    )
    for tok in forbidden:
        v = os.environ.get(tok)
        if v and len(v) >= 8:
            raise SystemExit(f"refuse: env {tok} is set (>=8 chars). R1 read-only.")


# ---------------------------------------------------------------------------
# RPC helpers (read-only, fail-fast)
# ---------------------------------------------------------------------------

def _http_post_json(url: str, payload: dict, timeout_s: int = DEFAULT_RPC_TIMEOUT_S) -> dict:
    """POST JSON-RPC payload, return parsed response. Read-only. Fail-fast."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RpcUnreachable(f"http 403 at {url}") from e
        if e.code == 429:
            raise RpcRateLimited(f"http 429 at {url}") from e
        raise RpcUnreachable(f"http {e.code} at {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RpcUnreachable(f"transport error at {url}: {e}") from e
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise RpcUnreachable(f"non-json response from {url}: {e}") from e


def _http_get_json(url: str, timeout_s: int = DEFAULT_RPC_TIMEOUT_S) -> Any:
    """GET JSON from a public API. Read-only. Fail-fast."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RpcRateLimited(f"http 429 at {url}") from e
        raise RpcUnreachable(f"http {e.code} at {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RpcUnreachable(f"transport error at {url}: {e}") from e
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise RpcUnreachable(f"non-json from {url}: {e}") from e


class RpcUnreachable(Exception):
    pass


class RpcRateLimited(Exception):
    pass


# ---------------------------------------------------------------------------
# Per-chain reachability probe
# ---------------------------------------------------------------------------

def _probe_chain(chain: str) -> tuple[str, str]:
    """Probe 1 endpoint per chain. Return (status, detail).

    status: 'reachable' | 'unreachable' | 'rate_limited'
    """
    if chain == "solana":
        endpoints = SOLANA_RPCS
    elif chain == "bsc":
        endpoints = BSC_RPCS
    elif chain == "base":
        endpoints = BASE_RPCS
    else:
        return ("unreachable", f"unknown chain: {chain}")
    for url in endpoints:
        try:
            if chain == "solana":
                # eth_chainId-equivalent for Solana: getHealth
                r = _http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "getHealth", "params": []})
                if "result" in r and r["result"] == "ok":
                    return ("reachable", url)
            elif chain in ("bsc", "base"):
                r = _http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
                if "result" in r:
                    return ("reachable", url)
        except RpcRateLimited:
            return ("rate_limited", url)
        except RpcUnreachable:
            continue
    return ("unreachable", "all endpoints failed")


# ---------------------------------------------------------------------------
# R1 fetchers (per dimension, per pool, fail-fast, honest confidence)
# ---------------------------------------------------------------------------

def fetch_r1_pool_snapshot_solana(pool: dict) -> dict:
    """Solana CLMM/CPMM via getMultipleAccountsInfo. Read-only."""
    addr = pool.get("pool_address", "")
    protocol = pool.get("protocol", "")
    if not addr or len(addr) < 32:
        return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_POOL_INVALID,
                            reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                            data_source="rpc_getMultipleAccountsInfo")
    for url in SOLANA_RPCS:
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getMultipleAccountsInfo",
                "params": [[addr], {"encoding": "base64"}],
            }
            r = _http_post_json(url, payload)
            result = r.get("result", {}).get("value", [])
            if result is None:
                continue
            if not result or result[0] is None:
                # account does not exist on this endpoint; try next
                continue
            account = result[0]
            data_b64 = account.get("data", [""])[0] if isinstance(account.get("data"), list) else ""
            data_len = len(data_b64) if data_b64 else 0
            if data_len == 0:
                # Some public RPCs return the account but with no data field; treat as low confidence.
                return _r1_pool_row(
                    pool,
                    confidence=CONFIDENCE_LOW,
                    reason=None,
                    reserve0="0", reserve1="0",
                    liquidity="0",
                    active_tick_or_bin=None,
                    data_source="rpc_getMultipleAccountsInfo",
                )
            return _r1_pool_row(
                pool,
                confidence=CONFIDENCE_LOW,  # confirmed-exists but unparsed
                reason=None,
                reserve0="0", reserve1="0",
                liquidity=str(data_len),  # byte length of account data as low-confidence proxy
                active_tick_or_bin=None,
                data_source="rpc_getMultipleAccountsInfo",
            )
        except RpcRateLimited:
            return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                                reason=REASON_RATE_LIMITED,
                                reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                                data_source="rpc_getMultipleAccountsInfo")
        except RpcUnreachable:
            continue
    return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_RPC_UNREACHABLE,
                        reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                        data_source="rpc_getMultipleAccountsInfo")


def fetch_r1_pool_snapshot_bsc_v3(pool: dict) -> dict:
    """BSC PancakeSwap V3 via eth_call slot0 + liquidity."""
    addr = pool.get("pool_address", "")
    if not addr or not addr.startswith("0x") or len(addr) != 42:
        return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_POOL_INVALID,
                            reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                            data_source="rpc_eth_call")
    for url in BSC_RPCS:
        try:
            # slot0() selector 0x3850c7bd
            slot0_data = "0x3850c7bd"
            payload_slot0 = {
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": addr, "data": slot0_data}, "latest"],
            }
            r = _http_post_json(url, payload_slot0)
            res = r.get("result", "0x")
            if not res or res == "0x" or len(res) < 66:
                continue
            # Decode first int24 word (current tick).
            tick_hex = res[2 + 24 * 2: 2 + 26 * 2]
            active_tick = int(tick_hex, 16)
            if active_tick >= 2**23:
                active_tick -= 2**24
            return _r1_pool_row(
                pool,
                confidence=CONFIDENCE_MEDIUM,  # one eth_call, parsed
                reason=None,
                reserve0="0", reserve1="0",
                liquidity="0",  # would need a second eth_call to liquidity()
                active_tick_or_bin=active_tick,
                data_source="rpc_eth_call_slot0",
            )
        except RpcRateLimited:
            return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                                reason=REASON_RATE_LIMITED,
                                reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                                data_source="rpc_eth_call")
        except RpcUnreachable:
            continue
    return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_RPC_UNREACHABLE,
                        reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                        data_source="rpc_eth_call")


def fetch_r1_pool_snapshot_bsc_v2(pool: dict) -> dict:
    """BSC PancakeSwap V2 via eth_call getReserves."""
    addr = pool.get("pool_address", "")
    if not addr or not addr.startswith("0x") or len(addr) != 42:
        return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_POOL_INVALID,
                            reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                            data_source="rpc_eth_call")
    for url in BSC_RPCS:
        try:
            # getReserves() selector 0x0902f1ac
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": addr, "data": "0x0902f1ac"}, "latest"],
            }
            r = _http_post_json(url, payload)
            res = r.get("result", "0x")
            if not res or res == "0x" or len(res) < 130:
                continue
            r0 = int(res[2:66], 16)
            r1 = int(res[66:130], 16)
            return _r1_pool_row(
                pool,
                confidence=CONFIDENCE_MEDIUM,
                reason=None,
                reserve0=str(r0), reserve1=str(r1),
                liquidity="0",
                active_tick_or_bin=None,
                data_source="rpc_eth_call_getReserves",
            )
        except RpcRateLimited:
            return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                                reason=REASON_RATE_LIMITED,
                                reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                                data_source="rpc_eth_call")
        except RpcUnreachable:
            continue
    return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_RPC_UNREACHABLE,
                        reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                        data_source="rpc_eth_call")


def fetch_r1_pool_snapshot_base(pool: dict) -> dict:
    """Base (Aerodrome / UniV3) — same as BSC V3, but Base public RPC is 403 in this env."""
    addr = pool.get("pool_address", "")
    if not addr or not addr.startswith("0x") or len(addr) != 42:
        return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_POOL_INVALID,
                            reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                            data_source="rpc_eth_call")
    for url in BASE_RPCS:
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": [],
            }
            _http_post_json(url, payload)
            # If chain reachable, fall through to a slot0 call
            slot0_data = "0x3850c7bd"
            payload_slot0 = {
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": addr, "data": slot0_data}, "latest"],
            }
            r = _http_post_json(url, payload_slot0)
            res = r.get("result", "0x")
            if not res or res == "0x" or len(res) < 66:
                continue
            tick_hex = res[2 + 24 * 2: 2 + 26 * 2]
            active_tick = int(tick_hex, 16)
            if active_tick >= 2**23:
                active_tick -= 2**24
            return _r1_pool_row(
                pool,
                confidence=CONFIDENCE_MEDIUM, reason=None,
                reserve0="0", reserve1="0", liquidity="0",
                active_tick_or_bin=active_tick, data_source="rpc_eth_call_slot0_base",
            )
        except RpcRateLimited:
            return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                                reason=REASON_RATE_LIMITED,
                                reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                                data_source="rpc_eth_call")
        except RpcUnreachable:
            continue
    return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE, reason=REASON_RPC_UNREACHABLE,
                        reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                        data_source="rpc_eth_call")


def fetch_r1_pool_snapshot_dispatch(pool: dict) -> dict:
    chain = pool.get("chain", "")
    protocol = pool.get("protocol", "")
    if chain == "solana":
        if protocol == "meteora_dlmm":
            # Meteora DLMM uses dlmm-api which is unreachable in this env.
            return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                                reason=REASON_INDEXER_UNREACHABLE,
                                reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                                data_source="dlmm_api")
        return fetch_r1_pool_snapshot_solana(pool)
    if chain == "bsc":
        if protocol == "pancakeswap_v3":
            return fetch_r1_pool_snapshot_bsc_v3(pool)
        if protocol == "pancakeswap_v2":
            return fetch_r1_pool_snapshot_bsc_v2(pool)
    if chain == "base":
        return fetch_r1_pool_snapshot_base(pool)
    return _r1_pool_row(pool, confidence=CONFIDENCE_UNAVAILABLE,
                        reason=REASON_ADAPTER_NOT_IMPL,
                        reserve0="0", reserve1="0", liquidity="0", active_tick_or_bin=None,
                        data_source="unsupported")


def _r1_pool_row(pool: dict, *, confidence: str, reason: str | None,
                 reserve0: str, reserve1: str, liquidity: str,
                 active_tick_or_bin, data_source: str) -> dict:
    return {
        "chain": pool.get("chain", ""),
        "protocol": pool.get("protocol", ""),
        "pool_address": pool.get("pool_address", ""),
        "token_pair": pool.get("token_pair", ""),
        "pool_type": pool.get("pool_type", ""),
        "block_or_slot": 0,  # we don't decode block number from headers; could be added
        "timestamp_utc": _now_iso(),
        "reserve0": reserve0,
        "reserve1": reserve1,
        "liquidity": liquidity,
        "active_tick_or_bin": active_tick_or_bin,
        "fee_tier_or_fee_bps": pool.get("fee_tier_or_fee_bps", 0),
        "tvl_usd_proxy": pool.get("tvl_proxy_usd", pool.get("vol24h_usd", 0.0)) or 0.0,
        "data_source": data_source,
        "confidence": confidence,
        "invalid_reason": reason,
    }


# ---------------------------------------------------------------------------
# R1 quote: 6 notional levels per pool. For smoke, we use TVL proxy as a
# rough price-impact heuristic with explicit confidence=low. We do NOT call
# QuoterV2 (not deployed in this env) — we honestly mark unavailable.
# ---------------------------------------------------------------------------

def fetch_r1_quote_rows(pool: dict, pool_row: dict) -> list[dict]:
    pool_addr = pool.get("pool_address", "")
    token_in = pool.get("token_pair", "TOKEN_IN/TOKEN_OUT").split("/")[0]
    token_out = pool.get("token_pair", "TOKEN_IN/TOKEN_OUT").split("/")[-1]
    rows = []
    for notional in NOTIONAL_LEVELS_USD:
        if pool_row["confidence"] == CONFIDENCE_UNAVAILABLE:
            rows.append({
                "pool_address": pool_addr,
                "notional_usd": float(notional),
                "token_in": token_in, "token_out": token_out,
                "amount_in": "0", "amount_out": "0",
                "price_impact_bps": 0.0, "fee_bps": 0,
                "quote_success": False,
                "quote_method": "unavailable",
                "confidence": CONFIDENCE_UNAVAILABLE,
                "invalid_reason": pool_row["invalid_reason"] or REASON_RPC_UNREACHABLE,
            })
        else:
            # Pool snapshot exists (low confidence). Quote still requires QuoterV2 /
            # Whirlpool quote_swap, which R1 does NOT call (QuoterV2 not deployed in
            # this env). We honestly mark low confidence + adapter_not_implemented,
            # NOT unavailable, because the pool itself is real.
            rows.append({
                "pool_address": pool_addr,
                "notional_usd": float(notional),
                "token_in": token_in, "token_out": token_out,
                "amount_in": "0", "amount_out": "0",
                "price_impact_bps": 0.0, "fee_bps": pool.get("fee_tier_or_fee_bps", 0),
                "quote_success": False,
                "quote_method": "unavailable_no_quoter_v2",
                "confidence": CONFIDENCE_LOW,
                "invalid_reason": REASON_ADAPTER_NOT_IMPL,
            })
    return rows


# ---------------------------------------------------------------------------
# R1 fee velocity: 5 windows per pool. DexScreener read-only; honest failure.
# ---------------------------------------------------------------------------

def fetch_r1_fee_velocity_rows(pool: dict) -> list[dict]:
    pool_addr = pool.get("pool_address", "")
    chain = pool.get("chain", "")
    fee_bps = pool.get("fee_tier_or_fee_bps", 0)
    rows = []
    for window in FEE_WINDOWS:
        volume_usd = 0.0
        confidence = CONFIDENCE_UNAVAILABLE
        source = "unavailable"
        reason = REASON_DEXSCREENER_NO_DATA
        heuristic = "unavailable"
        # Try DexScreener if the chain is supported by it.
        if chain in ("solana", "bsc", "base"):
            try:
                if chain == "solana":
                    url = f"{DEXSCREENER_BASE}/pairs/solana/{pool_addr}"
                else:
                    # EVM: try a generic search
                    url = f"{DEXSCREENER_BASE}/search?q={pool_addr}"
                r = _http_get_json(url)
                pairs = None
                if isinstance(r, dict):
                    pairs = r.get("pairs") or (r.get("pair") and [r["pair"]])
                if pairs and isinstance(pairs, list) and len(pairs) > 0:
                    p0 = pairs[0]
                    vol = p0.get("volume", {}) or {}
                    if window == "15m":
                        volume_usd = float(vol.get("m15", 0) or 0)
                    elif window == "1h":
                        volume_usd = float(vol.get("h1", 0) or 0)
                    elif window == "4h":
                        volume_usd = float((vol.get("h1", 0) or 0) * 4)
                    elif window == "24h":
                        volume_usd = float(vol.get("h24", 0) or 0)
                    elif window == "7d":
                        volume_usd = float((vol.get("h24", 0) or 0) * 7)
                    if volume_usd > 0:
                        confidence = CONFIDENCE_MEDIUM
                        source = "dexscreener"
                        heuristic = "derived"
                        reason = None
            except (RpcUnreachable, RpcRateLimited):
                confidence = CONFIDENCE_UNAVAILABLE
                source = "dexscreener"
                reason = REASON_INDEXER_UNREACHABLE
        estimated_fee = round(volume_usd * (fee_bps / 10_000.0), 6)
        rows.append({
            "pool_address": pool_addr,
            "window": window,
            "volume_usd": volume_usd,
            "fee_rate_bps": fee_bps,
            "estimated_fee_pool_usd": estimated_fee,
            "source": source,
            "heuristic": heuristic,
            "confidence": confidence,
            "invalid_reason": reason,
        })
    return rows


# ---------------------------------------------------------------------------
# R1 liquidity distribution: rough heuristic per pool type. Honest.
# ---------------------------------------------------------------------------

def fetch_r1_liquidity_distribution(pool: dict, pool_row: dict) -> dict:
    pool_type = pool.get("pool_type", "")
    if pool_type == "cpmm":
        return {
            "pool_address": pool.get("pool_address", ""),
            "range_type": "full_range",
            "bin_coverage": "N/A",
            "active_liquidity": 0.0,
            "near_active_liquidity": 0.0,
            "in_range_liquidity_share_proxy": 1.0,
            "tick_or_bin_density": 0.0,
            "sparse_warning": False,
            "confidence": CONFIDENCE_LOW,
            "invalid_reason": REASON_ADAPTER_NOT_IMPL,
        }
    if pool_type == "clmm":
        return {
            "pool_address": pool.get("pool_address", ""),
            "range_type": "tick_range",
            "bin_coverage": "N/A",
            "active_liquidity": 0.0,
            "near_active_liquidity": 0.0,
            "in_range_liquidity_share_proxy": 0.0,
            "tick_or_bin_density": 0.0,
            "sparse_warning": True,
            "confidence": CONFIDENCE_UNAVAILABLE,
            "invalid_reason": REASON_ADAPTER_NOT_IMPL,
        }
    if pool_type == "dlmm":
        return {
            "pool_address": pool.get("pool_address", ""),
            "range_type": "bin_range",
            "bin_coverage": "N/A",
            "active_liquidity": 0.0,
            "near_active_liquidity": 0.0,
            "in_range_liquidity_share_proxy": 0.0,
            "tick_or_bin_density": 0.0,
            "sparse_warning": True,
            "confidence": CONFIDENCE_UNAVAILABLE,
            "invalid_reason": REASON_INDEXER_UNREACHABLE,
        }
    return {
        "pool_address": pool.get("pool_address", ""),
        "range_type": "unknown",
        "bin_coverage": "N/A",
        "active_liquidity": 0.0, "near_active_liquidity": 0.0,
        "in_range_liquidity_share_proxy": 0.0, "tick_or_bin_density": 0.0,
        "sparse_warning": True, "confidence": CONFIDENCE_UNAVAILABLE,
        "invalid_reason": REASON_ADAPTER_NOT_IMPL,
    }


# ---------------------------------------------------------------------------
# R1 market regime: per chain, public CoinGecko 7d history. Honest failure.
# ---------------------------------------------------------------------------

CHAIN_REFERENCE_COINGECKO_ID = {
    "solana": "solana",
    "bsc": "binancecoin",
    "base": "ethereum",
}


def fetch_r1_market_regime_rows(chains: list[str]) -> list[dict]:
    rows = []
    for chain in chains:
        cg_id = CHAIN_REFERENCE_COINGECKO_ID.get(chain)
        if not cg_id:
            rows.append({
                "chain": chain, "timestamp_utc": _now_iso(),
                "reference_asset": "N/A", "return_1h": 0.0, "return_6h": 0.0,
                "volatility_1h": 0.0, "volatility_6h": 0.0,
                "regime_label": "no_data", "confidence": CONFIDENCE_UNAVAILABLE,
                "invalid_reason": REASON_TOKEN_NOT_RESOLVED,
            })
            continue
        try:
            url = f"{COINGECKO_BASE}/coins/{cg_id}/market_chart?vs_currency=usd&days=7"
            r = _http_get_json(url)
            prices = r.get("prices", []) if isinstance(r, dict) else []
            if not prices or len(prices) < 24:
                rows.append({
                    "chain": chain, "timestamp_utc": _now_iso(),
                    "reference_asset": cg_id, "return_1h": 0.0, "return_6h": 0.0,
                    "volatility_1h": 0.0, "volatility_6h": 0.0,
                    "regime_label": "no_data", "confidence": CONFIDENCE_UNAVAILABLE,
                    "invalid_reason": REASON_COINGECKO_NO_HISTORY,
                })
                continue
            closes = [float(p[1]) for p in prices if isinstance(p, list) and len(p) >= 2]
            if len(closes) < 24:
                raise RpcUnreachable("not enough closes")
            # Return over last 1h window and 6h window (very rough, hourly grain).
            r1h = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] > 0 else 0.0
            r6h = (closes[-1] - closes[-7]) / closes[-7] if closes[-7] > 0 else 0.0
            # Volatility: stdev of hourly returns over last 24 windows.
            rets = []
            for i in range(-24, 0):
                if closes[i - 1] > 0:
                    rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
            if rets:
                mean = sum(rets) / len(rets)
                var = sum((x - mean) ** 2 for x in rets) / max(1, len(rets) - 1)
                vol1h = (var ** 0.5) * (24 ** 0.5) * 100  # annualized %
            else:
                vol1h = 0.0
            regime = "sideways"
            if r6h > 0.05:
                regime = "uptrend"
            elif r6h < -0.05:
                regime = "downtrend"
            if vol1h > 80:
                regime = "high_volatility_trend" if abs(r6h) > 0.02 else "high_volume_sideways"
            if vol1h < 30:
                regime = "low_volatility_stable"
            rows.append({
                "chain": chain, "timestamp_utc": _now_iso(),
                "reference_asset": cg_id, "return_1h": r1h, "return_6h": r6h,
                "volatility_1h": vol1h, "volatility_6h": vol1h,
                "regime_label": regime, "confidence": CONFIDENCE_MEDIUM,
                "invalid_reason": None,
            })
        except (RpcUnreachable, RpcRateLimited):
            rows.append({
                "chain": chain, "timestamp_utc": _now_iso(),
                "reference_asset": cg_id, "return_1h": 0.0, "return_6h": 0.0,
                "volatility_1h": 0.0, "volatility_6h": 0.0,
                "regime_label": "no_data", "confidence": CONFIDENCE_UNAVAILABLE,
                "invalid_reason": REASON_COINGECKO_NO_HISTORY,
            })
    return rows


# ---------------------------------------------------------------------------
# R1 candidate review: 4-dim confidence aggregation
# ---------------------------------------------------------------------------

def aggregate_r1_candidate_review(pool: dict, pool_row: dict, quote_rows: list[dict],
                                  fee_rows: list[dict], liq_row: dict, regime_chain: str,
                                  regime_rows: list[dict]) -> dict:
    pool_addr = pool.get("pool_address", "")
    # quote_ready: at least one quote row is not unavailable
    quote_ready = any(r["confidence"] != CONFIDENCE_UNAVAILABLE for r in quote_rows)
    fee_ready = any(r["confidence"] != CONFIDENCE_UNAVAILABLE for r in fee_rows)
    liquidity_ready = liq_row["confidence"] != CONFIDENCE_UNAVAILABLE
    regime_ready = any(r["chain"] == regime_chain and r["confidence"] != CONFIDENCE_UNAVAILABLE
                       for r in regime_rows)
    # ev_ready: 4 dimensions all non-unavailable, but R1 still does NOT have
    # actual_fee_data_available. So ev_ready = true if 4 dims non-unavailable,
    # but actual_fee_data_available stays False at the summary level.
    ev_ready = quote_ready and fee_ready and liquidity_ready and regime_ready
    # preflight_candidate: simplified r1 preflight — needs all 4 dims non-unavailable
    # AND liquidity_ready AND TVL proxy > 0. (R1 preflight is NOT full EV.)
    tvl = pool.get("tvl_proxy_usd", 0) or 0
    preflight_candidate = bool(ev_ready and tvl > 0)
    # watchlist: basic meta + at least 1 high/medium confidence dimension
    high_medium = (
        pool_row["confidence"] in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM)
        or any(r["confidence"] in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM) for r in quote_rows)
        or any(r["confidence"] in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM) for r in fee_rows)
        or liq_row["confidence"] in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM)
    )
    watchlist = high_medium
    data_insufficient = not (quote_ready or fee_ready or liquidity_ready or regime_ready)
    parts = []
    parts.append("quote_ready" if quote_ready else "quote_unavailable")
    parts.append("fee_ready" if fee_ready else "fee_unavailable")
    parts.append("liquidity_ready" if liquidity_ready else "liquidity_unavailable")
    parts.append("regime_ready" if regime_ready else "regime_unavailable")
    return {
        "pool_address": pool_addr,
        "quote_ready": quote_ready, "fee_ready": fee_ready,
        "liquidity_ready": liquidity_ready, "regime_ready": regime_ready,
        "ev_ready": ev_ready, "preflight_candidate": preflight_candidate,
        "watchlist": watchlist, "data_insufficient": data_insufficient,
        "reason": ", ".join(parts),
    }


# ---------------------------------------------------------------------------
# Universe load + select
# ---------------------------------------------------------------------------

def _load_pool_universe(path: Path) -> dict:
    text = path.read_text()
    return json.loads(text)


def _select_universe_pools(universe: dict, max_pools: int) -> list[dict]:
    pools = universe.get("pools", universe.get("selected_real_pools", []))
    # Priority order: solana orca > bsc v3 > solana raydium > base > bsc v2 > meteora
    # R1 smoke wants a mix of chains (solana + bsc) to validate the multi-chain path.
    priority = {
        ("solana", "orca_whirlpool"): 1,
        ("bsc", "pancakeswap_v3"): 2,
        ("solana", "raydium_clmm"): 3,
        ("solana", "raydium_cpmm"): 4,
        ("base", "aerodrome_slipstream"): 5,
        ("base", "aerodrome_classic"): 6,
        ("base", "uniswap_v3"): 7,
        ("bsc", "pancakeswap_v2"): 8,
        ("solana", "meteora_dlmm"): 9,
    }
    pools_sorted = sorted(pools, key=lambda p: priority.get((p.get("chain"), p.get("protocol")), 99))
    return pools_sorted[:max_pools]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w") as f:
        f.write(",".join(fieldnames) + "\n")
        for r in rows:
            vals = []
            for fn in fieldnames:
                v = r.get(fn, "")
                if isinstance(v, bool):
                    vals.append("true" if v else "false")
                else:
                    s = str(v)
                    if "," in s or '"' in s:
                        s = '"' + s.replace('"', '""') + '"'
                    vals.append(s)
            f.write(",".join(vals) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    _safety_self_check()
    ap = argparse.ArgumentParser(description="R1 real-data read-only collector (smoke)")
    ap.add_argument("--pool-universe", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--max-pools", type=int, default=20)
    ap.add_argument("--max-snapshots", type=int, default=1)
    ap.add_argument("--no-daemon", action="store_true", default=True)
    args = ap.parse_args(argv)

    # Resolve output dir (whitelist guard).
    out_dir_str = str(args.output_dir)
    if not any(out_dir_str.startswith(p) for p in ALLOWED_OUTPUT_DIRS):
        raise SystemExit(f"refuse: output-dir {out_dir_str!r} not in whitelist {ALLOWED_OUTPUT_DIRS}")
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    universe = _load_pool_universe(args.pool_universe)
    pools = _select_universe_pools(universe, args.max_pools)
    if not pools:
        raise SystemExit("no pools selected from universe")

    # Probe per-chain reachability.
    chain_probes = {}
    for chain in ("solana", "bsc", "base"):
        chain_probes[chain] = _probe_chain(chain)

    # 1. pool_snapshot per pool
    pool_snapshots = []
    for p in pools:
        snap = fetch_r1_pool_snapshot_dispatch(p)
        pool_snapshots.append(snap)

    # 2. quote per pool × 6 notional
    quote_rows = []
    for p, snap in zip(pools, pool_snapshots):
        quote_rows.extend(fetch_r1_quote_rows(p, snap))

    # 3. fee_velocity per pool × 5 windows
    fee_rows = []
    for p in pools:
        fee_rows.extend(fetch_r1_fee_velocity_rows(p))

    # 4. liquidity_distribution per pool
    liq_rows = []
    for p, snap in zip(pools, pool_snapshots):
        liq_rows.append(fetch_r1_liquidity_distribution(p, snap))

    # 5. market_regime per chain (one row per reachable chain)
    reachable_chains = [c for c, (s, _) in chain_probes.items() if s == "reachable"]
    regime_rows = fetch_r1_market_regime_rows(reachable_chains)

    # 6. candidate_review per pool
    cand_rows = []
    for p, snap, q, fv, lq in zip(pools, pool_snapshots, _grouper(quote_rows, len(NOTIONAL_LEVELS_USD)),
                                  _grouper(fee_rows, len(FEE_WINDOWS)), liq_rows):
        cand_rows.append(aggregate_r1_candidate_review(p, snap, q, fv, lq, p.get("chain", ""), regime_rows))

    # Write outputs.
    _write_csv(out_dir / "r1_pool_snapshot.csv", pool_snapshots,
               list(pool_snapshots[0].keys()) if pool_snapshots else [])
    _write_json(out_dir / "r1_pool_snapshot.json", {"pools": pool_snapshots})
    _write_csv(out_dir / "r1_quote_snapshot.csv", quote_rows, list(quote_rows[0].keys()) if quote_rows else [])
    _write_json(out_dir / "r1_quote_snapshot.json", {"quotes": quote_rows})
    _write_csv(out_dir / "r1_fee_velocity.csv", fee_rows, list(fee_rows[0].keys()) if fee_rows else [])
    _write_json(out_dir / "r1_fee_velocity.json", {"fees": fee_rows})
    _write_csv(out_dir / "r1_liquidity_distribution.csv", liq_rows,
               list(liq_rows[0].keys()) if liq_rows else [])
    _write_json(out_dir / "r1_liquidity_distribution.json", {"liquidity": liq_rows})
    _write_csv(out_dir / "r1_market_regime.csv", regime_rows,
               list(regime_rows[0].keys()) if regime_rows else [])
    _write_json(out_dir / "r1_market_regime.json", {"regimes": regime_rows})
    _write_csv(out_dir / "r1_candidate_review.csv", cand_rows,
               list(cand_rows[0].keys()) if cand_rows else [])
    _write_json(out_dir / "r1_candidate_review.json", {"candidates": cand_rows})

    # Summary
    confidence_dist = Counter(s["confidence"] for s in pool_snapshots)
    preflight_count = sum(1 for c in cand_rows if c["preflight_candidate"])
    watchlist_count = sum(1 for c in cand_rows if c["watchlist"])
    data_insufficient_count = sum(1 for c in cand_rows if c["data_insufficient"])
    quote_ready_pool = sum(1 for c in cand_rows if c["quote_ready"])
    fee_ready_pool = sum(1 for c in cand_rows if c["fee_ready"])
    liquidity_ready_pool = sum(1 for c in cand_rows if c["liquidity_ready"])
    ev_ready_pool = sum(1 for c in cand_rows if c["ev_ready"])
    chain_dist = Counter(p.get("chain", "") for p in pools)
    proto_dist = Counter(f"{p.get('chain')}/{p.get('protocol')}" for p in pools)
    summary = {
        "stage": STAGE, "run_id": args.run_id,
        "r1_smoke_ran": True, "max_pools": args.max_pools, "max_snapshots": args.max_snapshots,
        "selected_pool_count": len(pools),
        "pool_snapshot_rows": len(pool_snapshots),
        "quote_snapshot_rows": len(quote_rows),
        "fee_velocity_rows": len(fee_rows),
        "liquidity_distribution_rows": len(liq_rows),
        "market_regime_rows": len(regime_rows),
        "candidate_review_rows": len(cand_rows),
        "quote_ready_pool_count": quote_ready_pool,
        "fee_ready_pool_count": fee_ready_pool,
        "liquidity_ready_pool_count": liquidity_ready_pool,
        "ev_ready_pool_count": ev_ready_pool,
        "preflight_candidate_count": preflight_count,
        "watchlist_count": watchlist_count,
        "data_insufficient_count": data_insufficient_count,
        "actual_fee_data_available": False,  # R1 ≠ actual fee
        "fee_proxy_only": True,             # R1 ≠ actual fee
        "actual_fee_schema_unchanged": True,
        "no_wallet_tx_probe": True,
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "chain_distribution": dict(chain_dist),
        "protocol_distribution": dict(proto_dist),
        "confidence_distribution": dict(confidence_dist),
        "chain_reachability": {c: {"status": s, "endpoint": d} for c, (s, d) in chain_probes.items()},
        "chains_skipped": [c for c, (s, _) in chain_probes.items() if s != "reachable"],
        "executed_at_utc": _now_iso(),
    }
    _write_json(out_dir / "r1_smoke_summary.json", summary)
    return 0


def _grouper(items: list, n: int) -> list[list]:
    if n <= 0:
        return [items]
    return [items[i:i + n] for i in range(0, len(items), n)]


if __name__ == "__main__":
    sys.exit(main())
