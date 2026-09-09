#!/usr/bin/env python3
"""LP survival horizon EV model (read-only).

Computes expected net EV per (chain, protocol, pool, notional, hold_window, scenario).

Inputs:
  - multichain_pool_readiness_probe.json (state from Stage E)
  - 5 scenarios (zero_il_lvr, optimistic, realistic, conservative, stress)
  - 6 notionals (10, 20, 100, 500, 1000, 2000)
  - 9 hold_windows (15m, 30m, 1h, 2h, 6h, 12h, 24h, 3d, 7d)

Outputs:
  - survival_horizon_ev_model.csv (long form)
  - survival_horizon_ev_model.json (machine + aggregates)

Safety: this script NEVER touches chain state. It only reads Stage E output
and runs an in-memory model.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOTIONALS_USD = [10, 20, 100, 500, 1000, 2000]
HOLD_WINDOWS = ["15m", "30m", "1h", "2h", "6h", "12h", "24h", "3d", "7d"]
HOLD_WINDOWS_HOURS = {
    "15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0, "6h": 6.0,
    "12h": 12.0, "24h": 24.0, "3d": 72.0, "7d": 168.0,
}

# Annualized fee yield per (chain, pool_type) — proxy baseline.
# In real use these would come from actual on-chain fee data. Here we
# use a heuristic based on observed fee_velocity for similar pools.
# This is NOT actual fee data; spec says "按 proxy 推算".
BASE_FEE_YIELD_APR = {
    ("Base", "Uniswap V3"): 0.20,         # 20% APR proxy
    ("Base", "PancakeSwap V3"): 0.18,
    ("BSC", "PancakeSwap V3"): 0.25,      # BSC hot
    ("Arbitrum", "Uniswap V3"): 0.15,
    ("Optimism", "Uniswap V3"): 0.12,
    ("Polygon", "Uniswap V3"): 0.18,
    ("Ethereum", "Uniswap V3"): 0.05,     # Ethereum gas heavy, low yield for tiny LP
}
DEFAULT_FEE_YIELD_APR = 0.10

# IL/LVR proxy per hold_window per scenario.
# zero_il_lvr = 0
# optimistic = 5% of fee
# realistic  = 30% of fee
# conservative = 80% of fee
# stress     = 200% of fee (IL can exceed fees)
IL_LVR_RATIO = {
    "zero_il_lvr": 0.0,
    "optimistic": 0.05,
    "realistic": 0.30,
    "conservative": 0.80,
    "stress": 2.0,
}

# Failure cost buffer: assume some fraction of entry+exit cost is wasted on
# failed txs (reverts, slippage, etc). Proxy.
FAILURE_BUFFER_RATIO = 0.10  # 10% of gas+slippage budget

# Slippage proxy: depends on notional / liquidity.
# At full capacity (capacity_proxy == 1.0), real trades in V3 pools still incur
# tick crossing, rounding, and spread frictions, so slippage is never 0 bps.
# We set a conservative floor of 5 bps at full capacity.
# At zero or negative capacity, slippage rises to 100 bps (1%).
SLIPPAGE_BPS_FLOOR = 5.0  # 5 bps floor at full capacity
SLIPPAGE_BPS_MAX = 100.0  # 100 bps ceiling when capacity is exhausted
SLIPPAGE_BPS_AT_FULL_CAPACITY = SLIPPAGE_BPS_FLOOR  # preserved for backwards compatibility


def expected_fee_usd(notional: float, fee_apr: float, hold_hours: float) -> float:
    return notional * fee_apr * (hold_hours / (365.0 * 24.0))


def il_lvr_usd(expected_fee: float, scenario: str) -> float:
    return expected_fee * IL_LVR_RATIO.get(scenario, 0.30)


def entry_cost_usd(gas_cost_proxy: float, slippage_bps: int, notional: float) -> float:
    gas = gas_cost_proxy
    slip = notional * slippage_bps / 10000.0
    return gas + slip


def exit_cost_usd(gas_cost_proxy: float, slippage_bps: int, notional: float) -> float:
    return entry_cost_usd(gas_cost_proxy, slippage_bps, notional)


def slippage_cost_usd(notional: float, capacity_proxy: float | None) -> float | None:
    """Compute slippage cost in USD.

    Fails close (returns None) if capacity_proxy is None or missing.
    Full capacity (1.0) retains a 5 bps floor because zero slippage is physically
    impossible in automated market maker pools.
    """
    if capacity_proxy is None:
        return None
    try:
        cap = float(capacity_proxy)
    except (ValueError, TypeError):
        return None
    if notional <= 0:
        return 0.0
    # Bound capacity in [0.0, 1.0]
    cap = max(0.0, min(1.0, cap))
    # Interpolate smoothly from SLIPPAGE_BPS_FLOOR (at cap=1.0) to SLIPPAGE_BPS_MAX (at cap=0.0)
    effective_bps = SLIPPAGE_BPS_FLOOR + (SLIPPAGE_BPS_MAX - SLIPPAGE_BPS_FLOOR) * (1.0 - cap)
    return notional * (effective_bps / 10000.0)


def failure_buffer_usd(gas_cost_proxy: float, slippage_cost: float) -> float:
    return (gas_cost_proxy + slippage_cost) * FAILURE_BUFFER_RATIO


# ---------------------------------------------------------------------------

def evaluate(pool: dict, scenario: str, notional: float, hold_window: str) -> dict | None:
    chain = pool["chain"]
    protocol = pool["protocol"]
    fee_apr = BASE_FEE_YIELD_APR.get((chain, protocol), DEFAULT_FEE_YIELD_APR)
    hold_hours = HOLD_WINDOWS_HOURS[hold_window]

    fee = expected_fee_usd(notional, fee_apr, hold_hours)
    il = il_lvr_usd(fee, scenario)

    # use the smallest capacity from {capacity_N} that's >= notional
    cap_field = f"capacity_{notional}"
    if cap_field not in pool or pool[cap_field] is None:
        # Missing capacity input -> fail-close
        return None
    try:
        cap = float(pool[cap_field])
    except (ValueError, TypeError):
        return None

    gas_proxy = pool.get("gas_cost_proxy", 0.0) or 0.0
    entry = entry_cost_usd(gas_proxy, 30, notional)  # 30 bps entry
    exit_c = exit_cost_usd(gas_proxy, 30, notional)
    slip = slippage_cost_usd(notional, cap)
    if slip is None:
        return None
    fail_buf = failure_buffer_usd(gas_proxy, slip)

    net = fee - il - entry - exit_c - slip - fail_buf
    net_pct = (net / notional) * 100.0 if notional > 0 else 0.0

    return {
        "chain": chain,
        "protocol": protocol,
        "pool": pool.get("pool", ""),
        "pair": f"{pool.get('token_a_symbol', '')}/{pool.get('token_b_symbol', '')}",
        "fee_tier": pool.get("fee_tier", 0),
        "notional": notional,
        "hold_window": hold_window,
        "scenario": scenario,
        "expected_fee_usd": round(fee, 6),
        "il_lvr_proxy_usd": round(il, 6),
        "entry_cost_usd": round(entry, 6),
        "exit_cost_usd": round(exit_c, 6),
        "gas_cost_usd": round(gas_proxy * 2, 6),  # entry + exit
        "slippage_cost_usd": round(slip, 6),
        "failure_buffer_usd": round(fail_buf, 6),
        "net_ev_proxy_usd": round(net, 6),
        "net_ev_proxy_pct": round(net_pct, 4),
        "survival_pass": "yes" if net > 0 else "no",
        "out_of_range_risk": "see_stage_G",
        "confidence": pool.get("confidence", 0.0),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="LP survival horizon EV model (read-only)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--readiness-json", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-pools", type=int, default=80)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(args.readiness_json).read_text())
    pools = data.get("results", [])
    if args.max_pools:
        pools = pools[:args.max_pools]

    rows: list[dict] = []
    for pool in pools:
        if not pool.get("state_ready"):
            continue
        for n in NOTIONALS_USD:
            for hw in HOLD_WINDOWS:
                for scen in IL_LVR_RATIO.keys():
                    row = evaluate(pool, scen, n, hw)
                    if row is not None:
                        rows.append(row)

    out = {
        "stage": "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1",
        "run_id": args.run_id,
        "phase": "F_survival_horizon_ev_model",
        "pools_evaluated": len({(r["chain"], r["protocol"], r["pool"]) for r in rows}),
        "row_count": len(rows),
        "wallet_or_tx_touched": False,
        "this_stage_only_runs_model": True,
    }

    # Aggregates
    real_rows = [r for r in rows if r["scenario"] == "realistic"]
    cons_rows = [r for r in rows if r["scenario"] == "conservative"]
    pos_real = sum(1 for r in real_rows if r["net_ev_proxy_usd"] > 0)
    pos_cons = sum(1 for r in cons_rows if r["net_ev_proxy_usd"] > 0)
    near_breakeven = sum(1 for r in real_rows if -0.01 <= r["net_ev_proxy_usd"] <= 0)
    out["positive_realistic_count"] = pos_real
    out["positive_conservative_count"] = pos_cons
    out["near_break_even_count"] = near_breakeven

    # top 20 by net_ev in realistic
    real_sorted = sorted(real_rows, key=lambda r: r["net_ev_proxy_usd"], reverse=True)
    out["top_20_realistic"] = real_sorted[:20]
    # best pool per notional
    best_per_n = {}
    for n in NOTIONALS_USD:
        rs = [r for r in real_sorted if r["notional"] == n]
        if rs:
            best_per_n[n] = rs[0]
    out["best_pool_by_notional"] = best_per_n
    # best pool per hold_window
    best_per_h = {}
    for hw in HOLD_WINDOWS:
        rs = [r for r in real_sorted if r["hold_window"] == hw]
        if rs:
            best_per_h[hw] = rs[0]
    out["best_pool_by_hold_window"] = best_per_h

    json_path = out_dir / "survival_horizon_ev_model.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))

    csv_path = out_dir / "survival_horizon_ev_model.csv"
    fieldnames = [
        "chain", "protocol", "pool", "pair", "fee_tier", "notional",
        "hold_window", "scenario", "expected_fee_usd", "il_lvr_proxy_usd",
        "entry_cost_usd", "exit_cost_usd", "gas_cost_usd",
        "slippage_cost_usd", "failure_buffer_usd", "net_ev_proxy_usd",
        "net_ev_proxy_pct", "survival_pass", "out_of_range_risk", "confidence"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    summary = {
        "pools_evaluated": out["pools_evaluated"],
        "row_count": out["row_count"],
        "positive_realistic_count": pos_real,
        "positive_conservative_count": pos_cons,
        "near_break_even_count": near_breakeven,
        "best_pool_by_notional_keys": list(best_per_n.keys()),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
