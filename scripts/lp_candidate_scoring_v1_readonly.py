#!/usr/bin/env python3
"""LP candidate scoring (read-only).

Combines:
  - survival_horizon_ev_model.json (Stage F)
  - survival_out_of_range_risk.json (Stage G)
  - multichain_pool_readiness_probe.json (Stage E)

into a single weighted score per pool per notional.

Output: lp_candidate_scoring.{csv,json} with top_5 per notional (10/20/100/500/1000/2000)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

NOTIONALS_USD = [10, 20, 100, 500, 1000, 2000]

# Weight configuration
WEIGHTS = {
    "fee_velocity": 0.15,
    "survival": 0.20,
    "cost": 0.15,
    "capacity": 0.15,
    "liquidity": 0.10,
    "data_confidence": 0.10,
    "wallet_availability": 0.05,
    "actual_probe_feasibility": 0.05,
    "notional_scalability": 0.03,
    "chain_risk": 0.02,
}

# Wallet currently funded on Base only; non-Base = no wallet
WALLET_FUNDED_CHAINS = {"Base"}

# Per-chain risk (heuristic; lower = better)
CHAIN_RISK_SCORE = {
    "Base": 0.8,
    "BSC": 0.7,
    "Arbitrum": 0.85,
    "Optimism": 0.8,
    "Polygon": 0.7,
    "Ethereum": 0.95,  # most secure, but gas is the highest
}


def _normalize(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def score_pool(
    pool: dict,
    best_realistic_ev_for_n: dict,
    oor_lookup: dict,
    n: int,
) -> dict:
    chain = pool["chain"]
    protocol = pool["protocol"]
    pool_addr = pool.get("pool", "")
    key = (chain, protocol, pool_addr, n)
    realistic_ev = best_realistic_ev_for_n.get(key)
    oor_at_15m = oor_lookup.get((chain, protocol, pool_addr, "15m"), 1.0)

    # Components
    # fee_velocity_score: net_ev / notional, normalized
    if realistic_ev is not None:
        fee_score = _normalize(realistic_ev["net_ev_proxy_pct"], -5.0, 5.0)
    else:
        fee_score = 0.0

    # survival_score: 1 - oor_risk at 15m
    survival = 1.0 - oor_at_15m

    # cost_score: 1 - cost/notional
    if realistic_ev:
        cost = (realistic_ev["entry_cost_usd"] + realistic_ev["exit_cost_usd"]) / max(n, 1)
        cost_score = 1.0 - _normalize(cost, 0.0, 0.5)  # 50% cost -> 0 score
    else:
        cost_score = 0.0

    # capacity_score: capacity_N
    cap = pool.get(f"capacity_{n}", 0.0) or 0.0
    capacity_score = cap

    # liquidity_score: log-scaled
    liq = pool.get("liquidity", 0) or 0
    liq_score = _normalize(math.log10(max(liq, 1)), 10, 25)

    # data_confidence
    conf = pool.get("confidence", 0.0) or 0.0
    data_score = conf

    # wallet_availability_score: 1 if Base, 0 otherwise
    wallet_score = 1.0 if chain in WALLET_FUNDED_CHAINS else 0.0

    # actual_probe_feasibility: combines state_ready, quote_ready, cost_ready
    probe_feas = (
        (1.0 if pool.get("state_ready") else 0.0) * 0.4
        + (1.0 if pool.get("quote_ready") else 0.0) * 0.3
        + (1.0 if pool.get("cost_ready") else 0.0) * 0.3
    )

    # notional_scalability: how well capacity scales
    cap_10 = pool.get("capacity_10", 0) or 0
    cap_2000 = pool.get("capacity_2000", 0) or 0
    if cap_10 > 0:
        scalability = min(1.0, cap_2000 / cap_10)
    else:
        scalability = 0.0

    # chain_risk
    chain_score = CHAIN_RISK_SCORE.get(chain, 0.5)

    total = (
        WEIGHTS["fee_velocity"] * fee_score
        + WEIGHTS["survival"] * survival
        + WEIGHTS["cost"] * cost_score
        + WEIGHTS["capacity"] * capacity_score
        + WEIGHTS["liquidity"] * liq_score
        + WEIGHTS["data_confidence"] * data_score
        + WEIGHTS["wallet_availability"] * wallet_score
        + WEIGHTS["actual_probe_feasibility"] * probe_feas
        + WEIGHTS["notional_scalability"] * scalability
        + WEIGHTS["chain_risk"] * chain_score
    )

    return {
        "chain": chain,
        "protocol": protocol,
        "pool": pool_addr,
        "pair": f"{pool.get('token_a_symbol', '')}/{pool.get('token_b_symbol', '')}",
        "fee_tier": pool.get("fee_tier", 0),
        "notional": n,
        "fee_velocity_score": round(fee_score, 4),
        "survival_score": round(survival, 4),
        "cost_score": round(cost_score, 4),
        "capacity_score": round(capacity_score, 4),
        "liquidity_score": round(liq_score, 4),
        "data_confidence_score": round(data_score, 4),
        "wallet_availability_score": round(wallet_score, 4),
        "actual_probe_feasibility_score": round(probe_feas, 4),
        "notional_scalability_score": round(scalability, 4),
        "chain_risk_score": round(chain_score, 4),
        "total_score": round(total, 4),
        "candidate_class": _classify(total, wallet_score, realistic_ev, n),
    }


def _classify(total: float, wallet_score: float, ev: dict | None, n: int) -> str:
    if total < 0.4:
        return "reject"
    if total < 0.55:
        return "needs_data"
    if wallet_score == 0.0:
        return "watch"
    if ev is None or ev.get("net_ev_proxy_usd", 0) <= 0:
        return "watch"
    return "candidate_now"


def main() -> int:
    p = argparse.ArgumentParser(description="LP candidate scoring (read-only)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--ev-model-json", required=True)
    p.add_argument("--risk-json", required=True)
    p.add_argument("--readiness-json", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pools = json.loads(Path(args.readiness_json).read_text()).get("results", [])
    ev_data = json.loads(Path(args.ev_model_json).read_text())
    risk_data = json.loads(Path(args.risk_json).read_text())

    # Build best realistic ev per (chain, protocol, pool, notional)
    best_realistic_ev: dict[tuple, dict] = {}
    for r in ev_data.get("top_20_realistic", []):
        key = (r["chain"], r["protocol"], r["pool"], r["notional"])
        # top_20 is already sorted desc; first occurrence is best
        if key not in best_realistic_ev:
            best_realistic_ev[key] = r
    # For pools that didn't make top_20, look at the full row set
    # (we re-load it from CSV to avoid huge JSON duplication in summary)
    ev_csv = out_dir.parent / "survival_horizon_ev_model.csv"
    if ev_csv.is_file():
        with ev_csv.open() as f:
            for row in csv.DictReader(f):
                if row["scenario"] != "realistic":
                    continue
                key = (row["chain"], row["protocol"], row["pool"], int(row["notional"]))
                if key in best_realistic_ev:
                    continue
                try:
                    best_realistic_ev[key] = {
                        "net_ev_proxy_usd": float(row["net_ev_proxy_usd"]),
                        "net_ev_proxy_pct": float(row["net_ev_proxy_pct"]),
                        "entry_cost_usd": float(row["entry_cost_usd"]),
                        "exit_cost_usd": float(row["exit_cost_usd"]),
                    }
                except ValueError:
                    continue

    # oor lookup at 15m
    oor_lookup = {}
    for r in risk_data.get("row_count", 0) and [] or []:
        pass
    risk_csv = out_dir.parent / "survival_out_of_range_risk.csv"
    if risk_csv.is_file():
        with risk_csv.open() as f:
            for row in csv.DictReader(f):
                if row["hold_window"] == "15m":
                    key = (row["chain"], row["protocol"], row["pool"], "15m")
                    try:
                        oor_lookup[key] = float(row["out_of_range_risk"])
                    except ValueError:
                        continue

    # Score
    all_scores = []
    for pool in pools:
        if not pool.get("state_ready"):
            continue
        for n in NOTIONALS_USD:
            sc = score_pool(pool, best_realistic_ev, oor_lookup, n)
            all_scores.append(sc)

    # Top 5 per notional
    top_per_n: dict[int, list[dict]] = {}
    for n in NOTIONALS_USD:
        rs = sorted([s for s in all_scores if s["notional"] == n],
                    key=lambda x: x["total_score"], reverse=True)
        top_per_n[n] = rs[:5]

    out = {
        "stage": "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1",
        "run_id": args.run_id,
        "phase": "H_candidate_scoring",
        "pools_scored": len({(s["chain"], s["protocol"], s["pool"]) for s in all_scores}),
        "score_count": len(all_scores),
        "top_5_by_notional": {str(n): top_per_n[n] for n in NOTIONALS_USD},
        "wallet_or_tx_touched": False,
        "this_stage_only_runs_model": True,
        "weights": WEIGHTS,
    }

    json_path = out_dir / "lp_candidate_scoring.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))

    csv_path = out_dir / "lp_candidate_scoring.csv"
    fieldnames = [
        "chain", "protocol", "pool", "pair", "fee_tier", "notional",
        "fee_velocity_score", "survival_score", "cost_score", "capacity_score",
        "liquidity_score", "data_confidence_score", "wallet_availability_score",
        "actual_probe_feasibility_score", "notional_scalability_score",
        "chain_risk_score", "total_score", "candidate_class"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for s in all_scores:
            w.writerow(s)

    summary = {
        "pools_scored": out["pools_scored"],
        "score_count": out["score_count"],
        "top_5_keys": {str(n): [c["pair"] for c in top_per_n[n]] for n in NOTIONALS_USD},
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
