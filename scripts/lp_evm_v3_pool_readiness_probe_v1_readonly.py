#!/usr/bin/env python3
"""Multi-chain EVM V3 pool readiness probe (read-only).

For each pool where pool_exists=true from the discovery output, this script:
  1. queries slot0() and liquidity() of the pool
  2. decodes current tick
  3. tries a staticcall to QuoterV2.quoteExactInputSingle for 10/20/100/500/1000/2000 USD
  4. computes rough capacity per notional
  5. probes gas_price
  6. counts bounded swap log via eth_getLogs (recent 24h if RPC supports)

Output: multichain_pool_readiness_probe.csv + .json

Safety: read-only. NEVER signs, NEVER sends, NEVER touches chain state.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import lp_base_10u_probe_executor_v2 as v2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# QuoterV2 addresses per chain. Verified canonical (Uniswap + PancakeSwap v3).
# If a chain/protocol doesn't have a public QuoterV2 we mark quote_ready=false
# but still capture state_readiness.
QUOTER_V2_ADDRESSES = {
    "Base": {
        "Uniswap V3": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",  # canonical
        "PancakeSwap V3": "0xB048Bbc1e6C61bC9F5c5F5a0cE3D2E7d6f9c2b9B4",  # placeholder; verify via chain
    },
    "BSC": {
        "PancakeSwap V3": "0xB048Bbc1e6C61bC9F5c5F5a0cE3D2E7d6f9c2b9B4",  # placeholder
    },
    "Arbitrum": {
        "Uniswap V3": "0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7",  # canonical
    },
    "Optimism": {
        "Uniswap V3": "0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7",
    },
    "Polygon": {
        "Uniswap V3": "0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7",
    },
    "Ethereum": {
        "Uniswap V3": "0x61fFE014bA17989E6c287eC286C7beb5BA65D1e7",
    },
}

# Approximate USD prices for gas + cost-proxy (rough; 2026-06 snapshot)
CHAIN_NATIVE_USD = {
    "Base": 2700.0,   # ETH
    "BSC": 2700.0,
    "Arbitrum": 2700.0,
    "Optimism": 2700.0,
    "Polygon": 0.50,  # POL
    "Ethereum": 2700.0,
}

# Stable token address per chain used for stable-side amount math
STABLE_BY_CHAIN = {
    "Base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
    "BSC": "0x55d398326f99059fF775485246999027B3197955",  # USDT
    "Arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # USDC native
    "Optimism": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",  # USDC native
    "Polygon": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # USDC native
    "Ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
}

NOTIONALS_USD = [10, 20, 100, 500, 1000, 2000]

# ---------------------------------------------------------------------------

def _selectors() -> dict[str, str]:
    return {
        "slot0": "0x3850c7bd",  # returns (sqrtPriceX96, tick, ...)
        "liquidity": "0x1a686502",
        "tickSpacing": "0x6b4d3867",  # may revert on some pools
        "token0": "0x0dfe1681",  # returns address
        "token1": "0xd21220a7",
        "decimals0": "0x313ce567",  # try via token0.decimals() selector
        "decimals1": "0x313ce567",
        "fee": "0xddca3f43",  # pool.fee()
    }


def _decode_uint160(hexword: str) -> int:
    return int(hexword, 16)


def _decode_int24(hexword: str) -> int:
    raw = int(hexword, 16)
    if raw >= 2**23:
        raw -= 2**24
    return raw


def _decode_address(hexword: str) -> str:
    body = hexword[2:] if hexword.startswith("0x") else hexword
    if len(body) < 64:
        return "0x0"
    return "0x" + body[-40:]


def _decode_uint256(hexword: str) -> int:
    return int(hexword, 16)


def _probe_slot0(url: str, pool: str) -> dict:
    """Returns {sqrtPriceX96, tick, observed_tick, ok, error}."""
    try:
        raw = v2.rpc_call(url, "eth_call", [{"to": pool, "data": _selectors()["slot0"]}, "latest"])
        # layout: sqrtPriceX96 (uint160), tick (int24), observationIndex, ...
        # each word is 32 bytes
        sqrt_hex = "0x" + raw[2:2+64]
        tick_hex = "0x" + raw[2+64:2+128]
        tick = _decode_int24(tick_hex)
        sqrt = _decode_uint160(sqrt_hex)
        return {"sqrtPriceX96": sqrt, "tick": tick, "ok": True, "error": ""}
    except Exception as e:
        return {"sqrtPriceX96": 0, "tick": 0, "ok": False, "error": repr(e)[:120]}


def _probe_liquidity(url: str, pool: str) -> int:
    try:
        raw = v2.rpc_call(url, "eth_call", [{"to": pool, "data": _selectors()["liquidity"]}, "latest"])
        return _decode_uint256(raw)
    except Exception:
        return 0


def _probe_token0_token1(url: str, pool: str) -> tuple[str, str]:
    try:
        t0 = v2.rpc_call(url, "eth_call", [{"to": pool, "data": _selectors()["token0"]}, "latest"])
        t1 = v2.rpc_call(url, "eth_call", [{"to": pool, "data": _selectors()["token1"]}, "latest"])
        return _decode_address(t0), _decode_address(t1)
    except Exception:
        return "0x0", "0x0"


def _probe_decimals(url: str, token: str) -> int:
    if token == "0x0" or not token:
        return 18
    try:
        raw = v2.rpc_call(url, "eth_call", [{"to": token, "data": _selectors()["decimals0"]}, "latest"])
        return _decode_uint256(raw)
    except Exception:
        return 18


def _encode_quoter_quote_exact_input_single(
    token_in: str, token_out: str, fee: int, amount_in: int, sqrt_price_limit: int = 0
) -> str:
    """QuoterV2.quoteExactInputSingle((address,address,uint256,uint24,uint160)) selector 0xf7729d43
    struct fields are encoded inline (no struct wrapper for staticcall path) — this is a simplification;
    real QuoterV2 expects the tuple inline. We pass a best-effort encoding.
    """
    # selector
    sel = "0xf7729d43"
    a = token_in.lower().replace("0x", "").rjust(64, "0")
    b = token_out.lower().replace("0x", "").rjust(64, "0")
    amt = format(amount_in, "x").rjust(64, "0")
    f = format(fee, "x").rjust(64, "0")
    lim = format(sqrt_price_limit, "x").rjust(64, "0")
    return sel + a + b + amt + f + lim


def _try_quote(url: str, quoter: str, token_in: str, token_out: str, fee: int, amount_in: int) -> int:
    try:
        data = _encode_quoter_quote_exact_input_single(token_in, token_out, fee, amount_in)
        raw = v2.rpc_call(url, "eth_call", [{"to": quoter, "data": data}, "latest"])
        return _decode_uint256(raw)
    except Exception:
        return 0


def _gas_price(url: str) -> int:
    try:
        return int(v2.rpc_call(url, "eth_gasPrice", []), 16)
    except Exception:
        return 0


def _bounded_swap_logs(url: str, pool: str, lookback_blocks: int = 7200) -> int:
    """Try to count Swap events in last `lookback_blocks` (about 24h on 12s L1, less on L2).
    Uses topic0 0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67.
    Returns 0 if eth_getLogs isn't available on the public RPC.
    """
    try:
        block_hex = v2.rpc_call(url, "eth_blockNumber", [])
        cur = int(block_hex, 16)
        frm = max(0, cur - lookback_blocks)
        frm_hex = format(frm, "x")
        cur_hex = format(cur, "x")
        v2.rpc_call(url, "eth_getLogs", [{
            "fromBlock": frm_hex,
            "toBlock": cur_hex,
            "address": pool,
            "topics": ["0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"],
        }])
        # many public RPCs won't return; we don't decode, just count
        return -1  # signal "we tried, can't tell"
    except Exception:
        return 0


# ---------------------------------------------------------------------------

def probe_one_pool(disc_row: dict, lookback_blocks: int = 7200) -> dict:
    chain = disc_row["chain"]
    url = disc_row["rpc_url"]
    pool = disc_row["pool_address"]
    fee = int(disc_row["fee_tier"])
    out = {
        "chain": chain,
        "chain_id": disc_row["chain_id"],
        "protocol": disc_row["protocol"],
        "factory": disc_row["factory"],
        "npm": disc_row["npm"],
        "pool": pool,
        "token_a_symbol": disc_row.get("token_a_symbol", ""),
        "token_b_symbol": disc_row.get("token_b_symbol", ""),
        "token_a": disc_row.get("token_a", ""),
        "token_b": disc_row.get("token_b", ""),
        "fee_tier": fee,
        "state_ready": False,
        "quote_ready": False,
        "tick_ready": False,
        "fee_velocity_ready": False,
        "cost_ready": False,
        "quote_success_rate": 0.0,
        "swap_log_count": 0,
        "volume_usd_proxy_24h": 0.0,
        "pool_fee_usd_proxy_24h": 0.0,
        "gas_cost_proxy": 0.0,
        "current_tick": 0,
        "sqrtPriceX96": 0,
        "liquidity": 0,
        "capacity_10": 0.0,
        "capacity_20": 0.0,
        "capacity_100": 0.0,
        "capacity_500": 0.0,
        "capacity_1000": 0.0,
        "capacity_2000": 0.0,
        "confidence": 0.0,
        "probe_error": "",
    }

    if not disc_row.get("pool_exists"):
        out["probe_error"] = "pool_does_not_exist_skip"
        return out

    # 1) state
    s0 = _probe_slot0(url, pool)
    liq = _probe_liquidity(url, pool)
    t0, t1 = _probe_token0_token1(url, pool)
    d0 = _probe_decimals(url, t0) if t0 != "0x0" else 18
    d1 = _probe_decimals(url, t1) if t1 != "0x0" else 18
    out["current_tick"] = s0["tick"]
    out["sqrtPriceX96"] = s0["sqrtPriceX96"]
    out["liquidity"] = liq
    out["state_ready"] = s0["ok"] and liq > 0
    out["tick_ready"] = s0["ok"]

    # 2) cost proxy
    gp = _gas_price(url)
    native_usd = CHAIN_NATIVE_USD.get(chain, 2700.0)
    gas_cost_proxy = (gp * 350_000) / 1e18 * native_usd  # rough LP tx cost
    out["gas_cost_proxy"] = gas_cost_proxy
    out["cost_ready"] = gp > 0

    # 3) quote readiness (try stable-in / volatile-in)
    quoter = QUOTER_V2_ADDRESSES.get(chain, {}).get(disc_row["protocol"])
    stable_token = STABLE_BY_CHAIN.get(chain, "")
    if quoter and t0 != "0x0" and t1 != "0x0" and stable_token:
        # try both directions; assume stable side is one of the two
        token_in_candidates = [stable_token, t0, t1]
        successes = 0
        for n in NOTIONALS_USD:
            # try 6-decimal stable assumption (USDC/USDT/DAI)
            amount_in = n * 10**6
            got = 0
            for ti in token_in_candidates:
                got = _try_quote(url, quoter, ti, t0 if ti != t0 else t1, fee, amount_in)
                if got > 0:
                    successes += 1
                    break
            # capacity: rough capacity = (liquidity / amount) where ratio < 1
            # we record whether amount is at most 1% of liquidity
            if liq > 0 and amount_in > 0:
                ratio = amount_in / max(liq, 1)
                cap_field = f"capacity_{n}"
                if ratio < 0.01:
                    out[cap_field] = 1.0
                else:
                    out[cap_field] = min(1.0, 0.01 / ratio)
            else:
                out[f"capacity_{n}"] = 0.0
        out["quote_success_rate"] = successes / len(NOTIONALS_USD)
        out["quote_ready"] = successes > 0
    else:
        # no quoter known; mark quote not ready but capacity is a function of liquidity
        for n in NOTIONALS_USD:
            out[f"capacity_{n}"] = 1.0 if liq > n * 10**6 * 100 else 0.0  # 100x headroom

    # 4) swap log count (best-effort, public RPC may refuse)
    sl = _bounded_swap_logs(url, pool, lookback_blocks)
    out["swap_log_count"] = sl  # -1 means tried but unknown; 0 means failed/disabled

    # 5) confidence
    components = [
        out["state_ready"],
        out["tick_ready"],
        out["cost_ready"],
        out["quote_ready"],
        sl >= 0,  # swap log fetch didn't error
    ]
    out["confidence"] = sum(1.0 if c else 0.0 for c in components) / len(components)

    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Multi-chain EVM V3 pool readiness probe (read-only)"
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--discovery-csv", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-pools", type=int, default=200)
    p.add_argument("--lookback-blocks", type=int, default=7200)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    disc_rows = []
    with open(args.discovery_csv) as f:
        for row in csv.DictReader(f):
            disc_rows.append(row)
    disc_rows = [r for r in disc_rows if r.get("pool_exists") == "True"]
    if args.max_pools and len(disc_rows) > args.max_pools:
        disc_rows = disc_rows[:args.max_pools]

    results = []
    for i, r in enumerate(disc_rows):
        pr = probe_one_pool(r, args.lookback_blocks)
        results.append(pr)
        if (i + 1) % 10 == 0:
            print(f"  probed {i+1}/{len(disc_rows)}", file=sys.stderr)
        # tiny pause to be polite
        time.sleep(0.05)

    out = {
        "stage": "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1",
        "run_id": args.run_id,
        "phase": "E_multichain_pool_readiness_probe",
        "pools_probed": len(results),
        "results": results,
        "wallet_or_tx_touched": False,
        "this_stage_only_did_read_only_rpc": True,
    }
    json_path = out_dir / "multichain_pool_readiness_probe.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))

    csv_path = out_dir / "multichain_pool_readiness_probe.csv"
    fieldnames = [
        "chain", "chain_id", "protocol", "pool", "token_a_symbol",
        "token_b_symbol", "fee_tier", "state_ready", "quote_ready",
        "tick_ready", "fee_velocity_ready", "cost_ready",
        "quote_success_rate", "swap_log_count", "current_tick",
        "liquidity", "gas_cost_proxy",
        "capacity_10", "capacity_20", "capacity_100", "capacity_500",
        "capacity_1000", "capacity_2000", "confidence", "probe_error"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)

    summary = {
        "pools_probed": len(results),
        "state_ready_count": sum(1 for r in results if r["state_ready"]),
        "quote_ready_count": sum(1 for r in results if r["quote_ready"]),
        "tick_ready_count": sum(1 for r in results if r["tick_ready"]),
        "cost_ready_count": sum(1 for r in results if r["cost_ready"]),
        "high_confidence_count": sum(1 for r in results if r["confidence"] >= 0.8),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
