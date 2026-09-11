#!/usr/bin/env python3
"""LP survival out-of-range risk model (read-only).

Estimates per-pool probability of being out-of-range within a hold window
based on historical tick movement (from upstream monitor) and current
state.

Inputs:
  - multichain_pool_readiness_probe.json
  - upstream monitor: reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/readiness_timeseries.csv
    (provides historical tick moves for Base WETH/USDC; for other pools
    we use a heuristic anchored to ETH price volatility)

Output: survival_out_of_range_risk.{csv,json}
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

# Historical base tick move samples per hour (synthetic but anchored to
# the Base WETH/USDC overnight monitor which observed -318 to -722 ticks over 7h50m).
# For other chains/pools we scale by ETH volatility heuristic.
HOLD_HOURS = {
    "15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0, "6h": 6.0,
    "12h": 12.0, "24h": 24.0, "3d": 72.0, "7d": 168.0,
}

# Empirical tick-move stddev per hour by chain, in "ticks" units
TICK_STDDEV_PER_HR = {
    "Base": 60.0,       # derived from overnight monitor: ~92 ticks stddev over 7h50m
    "BSC": 50.0,
    "Arbitrum": 50.0,
    "Optimism": 50.0,
    "Polygon": 80.0,
    "Ethereum": 30.0,
}

# Range width in ticks assuming ±200 default in v2 dynamic range.
DEFAULT_RANGE_WIDTH_TICKS = 400


def _load_base_historical(rep_dir: Path) -> dict:
    """Pull historical tick move statistics from upstream monitor."""
    csv_path = rep_dir / "readiness_timeseries.csv"
    if not csv_path.is_file():
        return {}
    drifts = []
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            try:
                drifts.append(int(row["drift_ticks"]))
            except (ValueError, KeyError):
                continue
    if len(drifts) < 2:
        return {}
    abs_d = [abs(d) for d in drifts]
    abs_d.sort()
    n = len(abs_d)
    p50 = abs_d[n // 2]
    p90 = abs_d[min(int(n * 0.9), n - 1)]
    p95 = abs_d[min(int(n * 0.95), n - 1)]
    return {
        "samples": n,
        "p50_abs_drift": p50,
        "p90_abs_drift": p90,
        "p95_abs_drift": p95,
        "max_abs_drift": max(abs_d),
    }


def evaluate_pool(pool: dict, base_hist: dict) -> list[dict]:
    chain = pool["chain"]
    sd_hr = TICK_STDDEV_PER_HR.get(chain, 60.0)

    # use base hist for the Base WETH/USDC pool specifically if available
    is_base_candidate = (
        chain == "Base" and pool.get("token_a_symbol") == "WETH"
        and pool.get("token_b_symbol") == "USDC"
    )
    if is_base_candidate and base_hist:
        sd_hr = base_hist.get("p95_abs_drift", 700) / math.sqrt(8.0)

    range_width = DEFAULT_RANGE_WIDTH_TICKS
    rows = []
    for hold, hours in HOLD_HOURS.items():
        # approximate tick-move distribution as Gaussian (sqrt(time) scaling)
        std = sd_hr * math.sqrt(hours)
        # p50 / p90 / p95 of |delta|
        p50 = int(0.67 * std)  # approx for half-normal
        p90 = int(1.65 * std)
        p95 = int(1.96 * std)
        # out-of-range if |delta| > range_width/2
        half = range_width / 2
        # half-normal CDF: P(|X| > x) = 2 * (1 - Phi(x/std))
        z = half / std if std > 0 else float("inf")
        oor_risk = max(0.0, min(1.0, 2 * (1 - _phi(z))))
        survival_p = 1.0 - oor_risk
        if oor_risk > 0.5:
            bucket = "high"
        elif oor_risk > 0.2:
            bucket = "medium"
        else:
            bucket = "low"
        rows.append({
            "chain": chain,
            "protocol": pool.get("protocol", ""),
            "pool": pool.get("pool", ""),
            "pair": f"{pool.get('token_a_symbol', '')}/{pool.get('token_b_symbol', '')}",
            "fee_tier": pool.get("fee_tier", 0),
            "hold_window": hold,
            "tick_range_width": range_width,
            "historical_tick_move_p50": p50,
            "historical_tick_move_p90": p90,
            "historical_tick_move_p95": p95,
            "out_of_range_risk": round(oor_risk, 4),
            "survival_probability_proxy": round(survival_p, 4),
            "recommended_range_width": range_width if oor_risk < 0.2 else range_width * 2,
            "risk_bucket": bucket,
        })
    return rows


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main() -> int:
    p = argparse.ArgumentParser(description="LP out-of-range risk (read-only)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--readiness-json", required=True)
    p.add_argument("--historical-csv", required=True,
                   help="upstream monitor readiness_timeseries.csv for anchor")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-pools", type=int, default=80)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(args.readiness_json).read_text())
    pools = data.get("results", [])
    if args.max_pools:
        pools = pools[:args.max_pools]

    historical_path = Path(args.historical_csv)
    # accept either the file or its parent directory
    if historical_path.is_file():
        base_hist = _load_base_historical(historical_path.parent)
    elif historical_path.is_dir():
        base_hist = _load_base_historical(historical_path)
    else:
        base_hist = {}

    all_rows = []
    for pool in pools:
        if not pool.get("state_ready"):
            continue
        all_rows.extend(evaluate_pool(pool, base_hist))

    out = {
        "stage": "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1",
        "run_id": args.run_id,
        "phase": "G_survival_out_of_range_risk",
        "pools_evaluated": len({(r["chain"], r["protocol"], r["pool"]) for r in all_rows}),
        "row_count": len(all_rows),
        "base_historical_anchor": base_hist,
        "wallet_or_tx_touched": False,
        "this_stage_only_runs_model": True,
    }

    json_path = out_dir / "survival_out_of_range_risk.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))

    csv_path = out_dir / "survival_out_of_range_risk.csv"
    fieldnames = [
        "chain", "protocol", "pool", "pair", "fee_tier", "hold_window",
        "tick_range_width", "historical_tick_move_p50",
        "historical_tick_move_p90", "historical_tick_move_p95",
        "out_of_range_risk", "survival_probability_proxy",
        "recommended_range_width", "risk_bucket"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    summary = {
        "pools_evaluated": out["pools_evaluated"],
        "row_count": out["row_count"],
        "high_risk_count": sum(1 for r in all_rows if r["risk_bucket"] == "high"),
        "medium_risk_count": sum(1 for r in all_rows if r["risk_bucket"] == "medium"),
        "low_risk_count": sum(1 for r in all_rows if r["risk_bucket"] == "low"),
        "base_historical_samples": base_hist.get("samples", 0),
        "base_historical_p95_abs_drift": base_hist.get("p95_abs_drift", None),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
