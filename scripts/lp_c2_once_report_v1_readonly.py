#!/usr/bin/env python3
"""Render the latest C2 scanner cycle as a per-pool PositionCap report."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


FIELDS = (
    "capital_tier", "coarse_tvl_min_usd", "tier_configured_max_usd",
    "tvlUsd", "active_liquidity_notional_usd", "position_cap_usd",
    "position_requested_usd", "position_investable_usd", "position_cap_tvl_share",
    "position_cap_hard_tvl_share_limit", "position_cap_hard_tvl_share_ok",
    "position_cap_pass", "netcover_pass", "entry_eligible", "vetted",
    "netcover_ratio", "position_cap_reason", "rejection_reason",
)


def build(db_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    latest = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()[0]
    if not latest:
        raise RuntimeError("scanner database has no completed score cycle")
    rows = []
    for db_row in connection.execute(
        "SELECT pool,symbol,accepted,rejection_reason,score_json FROM opportunity_scores "
        "WHERE as_of=? ORDER BY accepted DESC, expected_net_yield_pct DESC, pool",
        (latest,),
    ):
        score = json.loads(db_row["score_json"])
        row = {"pool": db_row["pool"], "symbol": db_row["symbol"],
               "accepted": bool(db_row["accepted"]),
               "db_rejection_reason": db_row["rejection_reason"]}
        row.update({field: score.get(field) for field in FIELDS})
        rows.append(row)
    return {
        "stage": "FIX-C2_REAL_SCANNER_ONCE",
        "as_of": latest,
        "pool_count": len(rows),
        "accepted_count": sum(row["accepted"] for row in rows),
        "position_cap_pass_count": sum(row["position_cap_pass"] is True for row in rows),
        "capital_tier": "M1",
        "coarse_tvl_floor_usd": 150_000.0,
        "formula": "min(TierConfiguredMax, TVL*0.0005, ActiveLiquidityNotional*0.02)",
        "hard_tvl_share": 0.001,
        "pools": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# FIX-C2 真实 scanner --once 逐池报告", "",
        f"- as_of: `{report['as_of']}`",
        f"- pools: `{report['pool_count']}`; accepted: `{report['accepted_count']}`; PositionCap pass: `{report['position_cap_pass_count']}`",
        f"- M1 coarse TVL floor: `{report['coarse_tvl_floor_usd']:.0f} U`",
        f"- runtime cap: `{report['formula']}`; hard TVL share: `{report['hard_tvl_share']:.3%}`",
        "", "| pool | pair | TVL | active notional | cap | cap pass | terminal accepted | reason |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in report["pools"]:
        def number(value): return "N/A" if value is None else f"{float(value):.4f}"
        reason = row.get("db_rejection_reason") or row.get("rejection_reason") or "PASS"
        lines.append(
            f"| `{row['pool']}` | {row.get('symbol') or ''} | {number(row.get('tvlUsd'))} | "
            f"{number(row.get('active_liquidity_notional_usd'))} | {number(row.get('position_cap_usd'))} | "
            f"{row.get('position_cap_pass')} | {row['accepted']} | {reason} |"
        )
    lines.extend(["", "accepted 为 0 也是有效结果；本报告不调整任何 NC/STABLE/FEE_COVER 阈值。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build(args.db)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "C2_POOL_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (args.out_dir / "C2_POOL_REPORT.md").write_text(render_markdown(report))
    print(json.dumps({key: report[key] for key in ("as_of", "pool_count", "accepted_count", "position_cap_pass_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
