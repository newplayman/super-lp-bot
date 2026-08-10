#!/usr/bin/env python3
"""Report reward-observation progress from scanner.db in SQLite read-only mode."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_reward_persistence_v1_readonly import (  # noqa: E402
    MAX_REWARD_OBSERVATION_GAP_HOURS,
    MIN_REWARD_OBSERVATION_HOURS,
    reward_high_duration_from_observations,
)


DEFAULT_DB = ROOT / "reports/lp_scanner/scanner.db"


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _ro_connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def _gap_evidence(rows: Sequence[Mapping[str, Any]], max_gap_hours: float) -> dict[str, Any]:
    stamps = sorted({_utc(str(row["as_of"])) for row in rows})
    gaps = []
    for older, newer in zip(stamps, stamps[1:]):
        hours = (newer - older).total_seconds() / 3600.0
        if hours > max_gap_hours:
            gaps.append({"after": older.isoformat(), "before": newer.isoformat(), "hours": hours})
    return {
        "gap_break_count": len(gaps),
        "max_gap_hours": max((gap["hours"] for gap in gaps), default=0.0),
        "latest_gap": gaps[-1] if gaps else None,
        "all_gaps": gaps,
    }


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0])


def build_progress(
    db_path: Path,
    *,
    as_of: datetime | str | None = None,
    max_gap_hours: float = MAX_REWARD_OBSERVATION_GAP_HOURS,
) -> dict[str, Any]:
    cutoff = _utc(as_of)
    if max_gap_hours <= 0.0:
        raise ValueError("max_gap_hours must be positive")
    with _ro_connect(db_path) as connection:
        observations = [dict(row) for row in connection.execute(
            "SELECT as_of,pool,chain,apy_reward,apy_base,tvl_usd,source "
            "FROM reward_observations WHERE as_of < ? ORDER BY pool,chain,as_of",
            (cutoff.isoformat(),),
        )]
        symbols: dict[str, str] = {}
        if _table_exists(connection, "pool_snapshots"):
            for row in connection.execute(
                "SELECT pool,symbol FROM pool_snapshots WHERE symbol IS NOT NULL ORDER BY as_of"
            ):
                symbols[str(row["pool"])] = str(row["symbol"])
        if _table_exists(connection, "opportunity_scores"):
            for row in connection.execute(
                "SELECT score_json FROM opportunity_scores ORDER BY as_of"
            ):
                try:
                    score = json.loads(row[0])
                except (TypeError, json.JSONDecodeError):
                    continue
                identity = score.get("llama_pool_id")
                symbol = score.get("symbol")
                if identity and symbol:
                    symbols[str(identity)] = str(symbol)
        severe = []
        if _table_exists(connection, "rpc_severe_incidents"):
            severe = [dict(row) for row in connection.execute(
                "SELECT source,opened_at,resolved_at,opening_health,resolution_health "
                "FROM rpc_severe_incidents ORDER BY opened_at"
            )]
        health_observations = []
        if _table_exists(connection, "shadow_gate_observations"):
            health_observations = [str(row[0]).upper() for row in connection.execute(
                "SELECT rpc_health FROM shadow_gate_observations"
            )]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in observations:
        grouped.setdefault((str(row["pool"]), str(row["chain"])), []).append(row)
    pools = []
    for (pool, chain), rows in grouped.items():
        canonical = reward_high_duration_from_observations(
            rows, cutoff=cutoff, max_gap_hours=max_gap_hours
        )
        gaps = _gap_evidence(rows, max_gap_hours)
        duration = canonical.get("duration_hours")
        finite_duration = 0.0 if duration is None else max(0.0, float(duration))
        remaining = max(0.0, MIN_REWARD_OBSERVATION_HOURS - finite_duration)
        rewards = [row.get("apy_reward") for row in rows]
        pools.append({
            "pool": pool,
            "symbol": symbols.get(pool),
            "chain": chain,
            "total_samples": len(rows),
            "first_observation": rows[0]["as_of"],
            "last_observation": rows[-1]["as_of"],
            "latest_reward_apr_pct": rewards[-1],
            "canonical_status": canonical["status"],
            "contiguous_positive_duration_hours": duration,
            "contiguous_sample_count": canonical["sample_count"],
            "contiguous_first_as_of": canonical["first_as_of"],
            "contiguous_last_as_of": canonical["last_as_of"],
            "trusted_24h": duration is not None and float(duration) >= MIN_REWARD_OBSERVATION_HOURS,
            "hours_remaining_to_trusted_24h": remaining,
            **gaps,
        })
    pools.sort(key=lambda row: (
        row["trusted_24h"],
        -(float(row["contiguous_positive_duration_hours"] or 0.0)),
        row["pool"],
    ))
    severe_counts = Counter(str(row.get("opening_health") or "UNKNOWN").upper() for row in severe)
    return {
        "schema": "lp_reward_observation_progress_v1",
        "generated_at": cutoff.isoformat(),
        "scanner_db": str(db_path),
        "policy": {
            "trusted_hours": MIN_REWARD_OBSERVATION_HOURS,
            "max_contiguous_gap_hours": max_gap_hours,
            "canonical_helper": "lp_reward_persistence_v1_readonly.reward_high_duration_from_observations",
        },
        "summary": {
            "observations": len(observations),
            "pools": len(pools),
            "trusted_24h": sum(row["trusted_24h"] for row in pools),
            "pools_with_gap_breaks": sum(row["gap_break_count"] > 0 for row in pools),
            "stale_pools": sum(row["canonical_status"] == "STALE_OBSERVATIONS" for row in pools),
        },
        "rpc_health_events": {
            "severe_total": len(severe),
            "severe_unresolved": sum(row.get("resolved_at") is None for row in severe),
            "severe_by_opening_health": dict(severe_counts),
            "shadow_observation_counts": dict(Counter(health_observations)),
            "persistence_note": "scanner persists EXIT_ONLY/KILLED as incidents; NORMAL resolves incidents; DEGRADED is not a standalone event row",
        },
        "pools": pools,
        "safety": {"sqlite_mode": "ro", "network_calls": 0, "scanner_process_control": 0},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary, rpc = report["summary"], report["rpc_health_events"]
    lines = [
        "# Reward observation progress（只读）",
        "",
        f"观测 {summary['observations']} 条 / {summary['pools']} 池；TRUSTED_24H={summary['trusted_24h']}；有 gap 断裂={summary['pools_with_gap_breaks']}；stale={summary['stale_pools']}。",
        f"RPC severe events={rpc['severe_total']}，unresolved={rpc['severe_unresolved']}；shadow health={json.dumps(rpc['shadow_observation_counts'], ensure_ascii=False, sort_keys=True)}。",
        "",
        "| 池 | samples | 连续时长 | 距 24h | 状态 | gaps | max gap |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in report["pools"]:
        duration = "—" if row["contiguous_positive_duration_hours"] is None else f"{float(row['contiguous_positive_duration_hours']):.3f}h"
        lines.append(
            f"| {row['symbol'] or row['pool']} | {row['total_samples']} | {duration} | "
            f"{float(row['hours_remaining_to_trusted_24h']):.3f}h | {row['canonical_status']} | "
            f"{row['gap_break_count']} | {float(row['max_gap_hours']):.3f}h |"
        )
    lines.extend([
        "",
        "连续性严格复用 canonical 0.5h gap 规则；本工具没有控制或触碰 scanner 进程。",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only reward observation progress")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", help="timezone-aware ISO cutoff; default now")
    parser.add_argument("--max-gap-hours", type=float, default=MAX_REWARD_OBSERVATION_GAP_HOURS)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_progress(args.db, as_of=args.as_of, max_gap_hours=args.max_gap_hours)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "progress.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (args.out / "progress.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        f"reward progress observations={report['summary']['observations']} "
        f"pools={report['summary']['pools']} trusted={report['summary']['trusted_24h']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
