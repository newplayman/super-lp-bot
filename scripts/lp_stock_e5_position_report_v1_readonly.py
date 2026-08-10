#!/usr/bin/env python3
"""Generate per-pool TP-E E5 sizing and absolute-profit evidence.

Pools without measured Stage-2 exit depth/economics are assigned 0 U.  This is
intentional fail-closed sizing, not a claim that DefiLlama TVL is zero.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_stock_tier_policy_v1_readonly import TIER_CONFIG, evaluate_position


AMM_HORIZON_HOURS = 720.0
INCOME_HAIRCUT = 0.65
SOLANA_FIXED_ROUND_TRIP_USD = 0.02


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "pools", "data"):
            if isinstance(payload.get(key), list):
                return _records(payload[key])
    raise ValueError("universe must contain records")


def preliminary_cap(tier: str, tvl: float, depth: float) -> float:
    cfg = TIER_CONFIG[str(tier).upper()]
    return max(0.0, min(cfg["position_max_usd"], tvl * 0.0005, depth * 0.02, tvl * 0.001))


def economics_for_cap(stage2: Mapping[str, Any], cap: float) -> tuple[float | None, float | None]:
    economics = stage2.get("economics") or {}
    resolved = stage2.get("resolved") or {}
    if economics.get("passed") is not True or cap <= 0:
        return None, None
    try:
        fee_apr = float(economics["recomputed_fee_apr_pct"]) / 100.0
        il = abs(float(economics["il_24h_worst"]))
        fee_rate = float(resolved["fee_rate"])
    except (KeyError, TypeError, ValueError):
        return None, None
    fee_income = cap * fee_apr * INCOME_HAIRCUT * (AMM_HORIZON_HOURS / 8760.0)
    round_trip = cap * 2.0 * fee_rate + SOLANA_FIXED_ROUND_TRIP_USD
    # The observed 24h worst IL is charged once, plus the unchanged 0.5 LVR model.
    expected_net = fee_income - cap * il * 1.5 - round_trip
    return expected_net, round_trip


def build_report(universe: list[Mapping[str, Any]], stage2_payload: Mapping[str, Any]) -> dict[str, Any]:
    by_id = {
        str(row.get("llama_pool_id")): row
        for row in stage2_payload.get("results") or []
        if row.get("llama_pool_id")
    }
    rows = []
    for source in universe:
        pool_id = str(source.get("pool") or source.get("pool_id") or source.get("llama_pool_id") or "")
        tier = str(source.get("tier") or source.get("stock_tier") or "").upper()
        stage2 = by_id.get(pool_id, {})
        economics = stage2.get("economics") or {}
        if tier not in TIER_CONFIG:
            rows.append({
                "llama_pool_id": pool_id, "symbol": source.get("symbol"),
                "chain": source.get("chain"), "project": source.get("project"), "tier": tier,
                "tvl_usd": source.get("tvlUsd", source.get("tvl_usd")),
                "measured_exit_depth_usd": None, "stage2_pass": False,
                "candidate": False, "position_cap_usd": 0.0,
                "absolute_profit_pass": False,
                "reason": "STOCK_STOCK_RESEARCH_ONLY_NO_POSITION_TIER",
            })
            continue
        try:
            tvl = float(source.get("tvlUsd", source.get("tvl_usd")))
            depth = float(economics.get("exit_depth_usd"))
            cap = preliminary_cap(tier, tvl, depth)
        except (TypeError, ValueError, KeyError):
            tvl, depth, cap = source.get("tvlUsd", source.get("tvl_usd")), None, 0.0
        expected_net, round_trip = economics_for_cap(stage2, cap)
        decision = evaluate_position(
            tier=tier, tvl_usd=tvl, exit_depth_usd=depth,
            expected_net_profit_usd=expected_net, round_trip_cost_usd=round_trip,
        )
        rows.append({
            "llama_pool_id": pool_id, "symbol": source.get("symbol"),
            "chain": source.get("chain"), "project": source.get("project"), "tier": tier,
            "tvl_usd": tvl, "measured_exit_depth_usd": depth,
            "stage2_pass": stage2.get("stage2_pass") is True,
            **decision.to_dict(),
        })
    return {
        "pool_count": len(rows),
        "rules": {
            "stock_coarse_tvl_min_usd": 20_000,
            "position_cap": "min(tier_max,TVL*0.0005,measured_exit_depth*0.02,TVL*0.001)",
            "regular_and_hard_tvl_shares_changed": False,
            "absolute_profit": "ExpectedNetProfit >= max(1,5*RoundTripCost)",
            "unresolved_position_usd": 0,
        },
        "candidate_count": sum(row["candidate"] for row in rows),
        "absolute_profit_pass_count": sum(row["absolute_profit_pass"] for row in rows),
        "tier_summary": {
            tier: {
                "total": sum(row["tier"] == tier for row in rows),
                "positive_position": sum(row["tier"] == tier and row["position_cap_usd"] > 0 for row in rows),
                "absolute_profit_pass": sum(row["tier"] == tier and row["absolute_profit_pass"] for row in rows),
                "candidate": sum(row["tier"] == tier and row["candidate"] for row in rows),
            } for tier in ("A", "B", "C", "STOCK_STOCK")
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    universe = _records(json.loads(args.universe.read_text()))
    stage2 = json.loads(args.stage2.read_text())
    report = build_report(universe, stage2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("pool_count", "candidate_count", "absolute_profit_pass_count", "tier_summary")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
