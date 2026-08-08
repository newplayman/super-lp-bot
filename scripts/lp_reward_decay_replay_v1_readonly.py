#!/usr/bin/env python3
"""Paper-only Reward Decay replay through the screener/allocator score chain.

This module contains no network, wallet, signing, transaction or paid-service
path.  It validates PRD v2.1 section 12.4 and PRD v1 section 16: current reward
APR decays are scored at their current value, reward persistence below 6h cannot
ENTER, and missing reward-duration evidence fails closed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_portfolio_allocator_v1_readonly import is_enterable, rank_metric  # noqa: E402
from scripts.lp_universe_screener_v1_readonly import assess  # noqa: E402

SCHEMA_VERSION = "lp-reward-decay-replay-v1"
DEFAULT_GATES = {
    "min_tvl": 500_000.0,
    "min_vol1d": 50_000.0,
    "suspect_reward_apr": 300.0,
    "suspect_vol_tvl": 20.0,
}


def build_decay_trajectory() -> List[Dict[str, float]]:
    """Return the required 100% -> 30% -> 5% reward APR trajectory."""
    return [
        {"step": 0, "elapsed_hours": 24.0, "reward_apr": 100.0},
        {"step": 1, "elapsed_hours": 30.0, "reward_apr": 30.0},
        {"step": 2, "elapsed_hours": 36.0, "reward_apr": 5.0},
    ]


def _pool(reward_apr: float, duration_hours: Optional[float]) -> Dict[str, Any]:
    pool: Dict[str, Any] = {
        "symbol": "WETH-USDC",
        "project": "aerodrome-slipstream",
        "pool": "reward-decay-paper-fixture",
        "poolMeta": "CL50 - 0.05%",
        "underlyingTokens": ["0xbase-paper", "0xquote-paper"],
        "rewardTokens": ["0xreward-paper"],
        "tvlUsd": 2_000_000.0,
        "volumeUsd1d": 500_000.0,
        "apyBase": 20.0,
        "apyReward": float(reward_apr),
        # Purposefully remains high across the decay: the scorer must cap stale
        # history at the current persistence-adjusted observation.
        "apyMean30d": 120.0,
    }
    if duration_hours is not None:
        pool["reward_high_duration"] = float(duration_hours)
    return pool


def _allocator_record(pool: Mapping[str, Any], screened: Mapping[str, Any]) -> Dict[str, Any]:
    reward_apr = float(pool.get("apyReward") or 0.0)
    return {
        **dict(screened),
        "status": "OK",
        "resolve_status": "OK",
        "wash_flag": False,
        "yield_cover": 5.0,
        "composite_score": float(screened["score"]),
        "fee_apr_onchain": 20.0,
        "reward_apr": reward_apr,
        "total_income_apr": 20.0 + reward_apr,
        "il_apr": 5.0,
    }


def _strictly_decreases(values: Iterable[float]) -> bool:
    sequence = list(values)
    return len(sequence) >= 2 and all(a > b for a, b in zip(sequence, sequence[1:]))


def run_replay(points: Optional[List[Mapping[str, float]]] = None) -> Dict[str, Any]:
    """Run deterministic replay and raise if any machine assertion fails."""
    trajectory: List[Dict[str, Any]] = []
    for point in points or build_decay_trajectory():
        reward_apr = float(point["reward_apr"])
        # All main decay points already have >=24h persistence.  This isolates
        # reward decay from the separate young-incentive rejection assertion.
        pool = _pool(reward_apr, duration_hours=float(point["elapsed_hours"]))
        screened = assess(pool, DEFAULT_GATES)
        allocator_record = _allocator_record(pool, screened)
        trajectory.append({
            "step": int(point["step"]),
            "elapsed_hours": float(point["elapsed_hours"]),
            "reward_apr": reward_apr,
            "stale_apy_mean_30d": float(pool["apyMean30d"]),
            "reward_persistence_status": screened["reward_persistence_status"],
            "reward_persistence_score": screened["reward_persistence_score"],
            "entry_eligible": bool(screened["entry_eligible"] and is_enterable(allocator_record)),
            "screener_score": float(screened["score"]),
            "allocator_rank_metric": round(float(rank_metric(allocator_record)), 6),
        })

    young_pool = _pool(300.0, duration_hours=0.5)
    young_screened = assess(young_pool, DEFAULT_GATES)
    young_allocator = _allocator_record(young_pool, young_screened)
    missing_pool = _pool(100.0, duration_hours=None)
    missing_screened = assess(missing_pool, DEFAULT_GATES)
    missing_allocator = _allocator_record(missing_pool, missing_screened)

    assertions = {
        "required_reward_path": [row["reward_apr"] for row in trajectory] == [100.0, 30.0, 5.0],
        "scores_strictly_decrease": _strictly_decreases(row["screener_score"] for row in trajectory),
        "allocator_scores_strictly_decrease": _strictly_decreases(
            row["allocator_rank_metric"] for row in trajectory
        ),
        "main_points_enterable": all(row["entry_eligible"] for row in trajectory),
        "young_300pct_rejected": (
            young_screened["entry_eligible"] is False
            and young_screened["reward_persistence_status"] == "TOO_YOUNG_SHADOW_ONLY"
            and not is_enterable(young_allocator)
        ),
        "missing_persistence_fail_closed": (
            missing_screened["entry_eligible"] is False
            and missing_screened["reward_persistence_status"] == "MISSING_FAIL_CLOSED"
            and not is_enterable(missing_allocator)
        ),
        "finite_scores": all(
            math.isfinite(row["screener_score"])
            and math.isfinite(row["allocator_rank_metric"])
            for row in trajectory
        ),
    }
    assertions["all_passed"] = all(assertions.values())
    if not assertions["all_passed"]:
        failed = [name for name, ok in assertions.items() if not ok]
        raise AssertionError(f"reward decay replay failed: {failed}")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "paper-only/read-only",
        "source_chain": [
            "lp_universe_screener_v1_readonly.assess/score_pool",
            "lp_portfolio_allocator_v1_readonly.is_enterable/rank_metric",
        ],
        "semantics": {
            "missing_reward_persistence": "FAIL_CLOSED_SHADOW_ONLY_REWARD_SCORE_ZERO",
            "fee_only_legacy": "COMPATIBLE_NOT_APPLICABLE",
            "under_6h": "SHADOW_ONLY_REWARD_SCORE_ZERO",
            "6h_to_24h": "ENTER_MINIMUM_WITH_LINEAR_CREDIBILITY_HAIRCUT",
            "at_least_24h": "TRUSTED_CURRENT_REWARD_APR",
            "stale_historical_apr": "CAPPED_AT_CURRENT_PERSISTENCE_ADJUSTED_APR",
        },
        "trajectory": trajectory,
        "young_incentive_fixture": {
            "reward_apr": 300.0,
            "reward_high_duration": 0.5,
            "entry_eligible": young_screened["entry_eligible"],
            "status": young_screened["reward_persistence_status"],
            "reasons": young_screened["entry_block_reasons"],
        },
        "missing_persistence_fixture": {
            "reward_apr": 100.0,
            "reward_high_duration": None,
            "entry_eligible": missing_screened["entry_eligible"],
            "status": missing_screened["reward_persistence_status"],
            "reasons": missing_screened["entry_block_reasons"],
        },
        "assertions": assertions,
    }


def _render_summary(replay: Mapping[str, Any]) -> str:
    rows = replay["trajectory"]
    lines = [
        "# LP Reward Decay Replay v1",
        "",
        f"Generated: {replay['generated_at']}",
        "",
        "Mode: paper-only/read-only. No wallet, signing, broadcast, paid API or chain write.",
        "",
        "The 30d headline is deliberately held at 120% while current rewards decay; both the real "
        "screener score and allocator rank must follow current evidence instead of extrapolating it.",
        "",
        "| step | elapsed | reward APR | screener score | allocator rank | persistence | ENTER |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['step']} | {row['elapsed_hours']:.1f}h | {row['reward_apr']:.2f}% | "
            f"{row['screener_score']:.2f} | {row['allocator_rank_metric']:.2f} | "
            f"{row['reward_persistence_status']} | {str(row['entry_eligible']).upper()} |"
        )
    young = replay["young_incentive_fixture"]
    missing = replay["missing_persistence_fixture"]
    lines.extend([
        "",
        "## Persistence gates",
        "",
        f"- 300% APR opened 30 minutes ago: ENTER={str(young['entry_eligible']).upper()}, "
        f"status={young['status']}.",
        f"- Missing duration on a reward-bearing pool: ENTER={str(missing['entry_eligible']).upper()}, "
        f"status={missing['status']}.",
        "- Fee-only legacy records: persistence is not applicable and remains compatible.",
        "",
        "## Machine assertions",
        "",
    ])
    for name, passed in replay["assertions"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    return "\n".join(lines) + "\n"


def write_report(replay: Mapping[str, Any], out_dir: os.PathLike[str] | str) -> Dict[str, Path]:
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    machine = destination / "reward_decay_replay.json"
    human = destination / "summary.md"
    machine.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    human.write_text(_render_summary(replay), encoding="utf-8")
    return {"machine_json": machine, "human_summary": human}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="report directory")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or os.path.join(_ROOT, "reports", "lp_reward_decay_replay", stamp)
    replay = run_replay()
    paths = write_report(replay, out_dir)
    print(f"reward decay replay: PASS ({len(replay['trajectory'])} points)")
    print(f"wrote {paths['machine_json']} and {paths['human_summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
