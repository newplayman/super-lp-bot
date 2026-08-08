#!/usr/bin/env python3
"""Render a human-readable shadow digest from runner and scanner artifacts.

This is deliberately a consumer, not another producer: it opens heartbeat JSONL
and scanner SQLite read-only, tolerates a concurrently appended final JSONL line,
and writes only the requested Markdown report.  No RPC, credentials, wallet, or
transaction code is imported.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEARTBEAT = (
    REPO_ROOT
    / "reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/heartbeat.jsonl"
)
DEFAULT_SCANNER_DB = REPO_ROOT / "reports/lp_scanner/scanner.db"


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _record_day(record: Mapping[str, Any]) -> Optional[str]:
    raw = record.get("ts_utc")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def summarize_heartbeat(
    path: str | Path, *, day: str | date | None = None
) -> Dict[str, Any]:
    """Stream one heartbeat JSONL file and return runner health/PnL metrics.

    ``day=None`` intentionally means the whole artifact; this is useful for the
    2,150+ tick historical acceptance run.  The CLI defaults to the UTC day and
    offers ``--all`` explicitly.
    """
    heartbeat = Path(path)
    selected_day = day.isoformat() if isinstance(day, date) else day
    summary: Dict[str, Any] = {
        "available": heartbeat.is_file(),
        "path": str(heartbeat),
        "period": selected_day or "all",
        "ticks": 0,
        "unique_ticks": 0,
        "malformed_lines": 0,
        "first_tick": None,
        "last_tick": None,
        "first_ts_utc": None,
        "last_ts_utc": None,
        "start_portfolio_net_usd": None,
        "end_portfolio_net_usd": None,
        "min_portfolio_net_usd": None,
        "max_portfolio_net_usd": None,
        "max_drawdown_usd": 0.0,
        "breach_events": 0,
        "last_pool_count": 0,
        "last_exited_count": 0,
        "last_out_of_range_count": 0,
    }
    if not heartbeat.is_file():
        return summary

    tick_ids = set()
    running_peak: Optional[float] = None
    with heartbeat.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                summary["malformed_lines"] += 1
                continue
            if not isinstance(record, Mapping):
                summary["malformed_lines"] += 1
                continue
            if selected_day is not None and _record_day(record) != selected_day:
                continue

            tick = record.get("tick")
            summary["ticks"] += 1
            if tick is not None:
                tick_ids.add(tick)
            if summary["first_tick"] is None:
                summary["first_tick"] = tick
                summary["first_ts_utc"] = record.get("ts_utc")
            summary["last_tick"] = tick
            summary["last_ts_utc"] = record.get("ts_utc")

            portfolio_net = _finite(record.get("portfolio_net_usd"))
            if portfolio_net is not None:
                if summary["start_portfolio_net_usd"] is None:
                    summary["start_portfolio_net_usd"] = portfolio_net
                summary["end_portfolio_net_usd"] = portfolio_net
                current_min = summary["min_portfolio_net_usd"]
                current_max = summary["max_portfolio_net_usd"]
                summary["min_portfolio_net_usd"] = (
                    portfolio_net if current_min is None else min(current_min, portfolio_net)
                )
                summary["max_portfolio_net_usd"] = (
                    portfolio_net if current_max is None else max(current_max, portfolio_net)
                )
                running_peak = portfolio_net if running_peak is None else max(running_peak, portfolio_net)
                summary["max_drawdown_usd"] = max(
                    summary["max_drawdown_usd"], running_peak - portfolio_net
                )

            pools = record.get("by_pool")
            if not isinstance(pools, list):
                pools = []
            summary["breach_events"] += sum(
                1 for pool in pools if isinstance(pool, Mapping) and pool.get("new_breach")
            )
            summary["last_pool_count"] = len(pools)
            summary["last_exited_count"] = sum(
                1 for pool in pools if isinstance(pool, Mapping) and bool(pool.get("exited"))
            )
            summary["last_out_of_range_count"] = sum(
                1
                for pool in pools
                if isinstance(pool, Mapping)
                and pool.get("in_range") is False
                and not bool(pool.get("exited"))
            )

    summary["unique_ticks"] = len(tick_ids)
    return summary


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _max_as_of(connection: sqlite3.Connection, tables: Iterable[str]) -> Optional[str]:
    values = []
    for table in tables:
        if not _table_exists(connection, table):
            continue
        row = connection.execute(f"SELECT max(as_of) FROM {table}").fetchone()
        if row and row[0] is not None:
            values.append(str(row[0]))
    return max(values) if values else None


def summarize_scanner_db(path: str | Path) -> Dict[str, Any]:
    """Read the latest atomic scanner cycle without creating a missing DB."""
    db = Path(path)
    summary: Dict[str, Any] = {
        "available": db.is_file(),
        "path": str(db),
        "latest_as_of": None,
        "snapshot_count": 0,
        "opportunity_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "rejection_reasons": {},
        "market_sessions": {},
        "top_opportunities": [],
        "error": None,
    }
    if not db.is_file():
        return summary

    try:
        uri = f"file:{db.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            latest = _max_as_of(
                connection, ("pool_snapshots", "opportunity_scores", "market_sessions")
            )
            summary["latest_as_of"] = latest
            if latest is None:
                return summary

            if _table_exists(connection, "pool_snapshots"):
                summary["snapshot_count"] = connection.execute(
                    "SELECT count(*) FROM pool_snapshots WHERE as_of=?", (latest,)
                ).fetchone()[0]
            if _table_exists(connection, "opportunity_scores"):
                rows = connection.execute(
                    """
                    SELECT pool, symbol, expected_net_yield_usd, netcover_ratio,
                           accepted, rejection_reason
                    FROM opportunity_scores
                    WHERE as_of=?
                    ORDER BY accepted DESC,
                             expected_net_yield_usd DESC,
                             netcover_ratio DESC
                    """,
                    (latest,),
                ).fetchall()
                summary["opportunity_count"] = len(rows)
                summary["accepted_count"] = sum(int(row["accepted"]) for row in rows)
                summary["rejected_count"] = len(rows) - summary["accepted_count"]
                reasons = Counter(
                    str(row["rejection_reason"])
                    for row in rows
                    if not row["accepted"] and row["rejection_reason"]
                )
                summary["rejection_reasons"] = dict(sorted(reasons.items()))
                summary["top_opportunities"] = [dict(row) for row in rows[:10]]
            if _table_exists(connection, "market_sessions"):
                rows = connection.execute(
                    """
                    SELECT market_session, count(*) AS n
                    FROM market_sessions WHERE as_of=?
                    GROUP BY market_session ORDER BY market_session
                    """,
                    (latest,),
                ).fetchall()
                summary["market_sessions"] = {
                    str(row["market_session"]): int(row["n"]) for row in rows
                }
    except (sqlite3.Error, OSError) as exc:
        summary["error"] = str(exc)
    return summary


def _fmt_money(value: Any) -> str:
    number = _finite(value)
    return "—" if number is None else f"${number:,.2f}"


def _fmt_number(value: Any, digits: int = 2) -> str:
    number = _finite(value)
    return "—" if number is None else f"{number:,.{digits}f}"


def build_digest_markdown(
    heartbeat: Mapping[str, Any],
    scanner: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> str:
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    period = str(heartbeat.get("period") or "all")
    title_period = period if period != "all" else "all history"
    lines = [
        f"# LP Shadow Daily Digest — {title_period}",
        "",
        f"_generated {generated} · read-only/paper-only_",
        "",
        "## Runner heartbeat",
        "",
    ]
    if not heartbeat.get("available", True):
        lines.extend([f"Heartbeat unavailable: `{heartbeat.get('path')}`", ""])
    else:
        lines.extend(
            [
                f"- Source: `{heartbeat.get('path', 'in-memory')}`",
                f"- Valid ticks: **{heartbeat.get('ticks', 0):,}** "
                f"(unique {heartbeat.get('unique_ticks', 0):,}; malformed lines "
                f"{heartbeat.get('malformed_lines', 0):,})",
                f"- Window: {heartbeat.get('first_ts_utc') or '—'} → "
                f"{heartbeat.get('last_ts_utc') or '—'}",
                f"- Portfolio net: {_fmt_money(heartbeat.get('start_portfolio_net_usd'))} → "
                f"{_fmt_money(heartbeat.get('end_portfolio_net_usd'))}; "
                f"observed max drawdown {_fmt_money(heartbeat.get('max_drawdown_usd'))}",
                f"- Breach events: {heartbeat.get('breach_events', 0):,}; last tick pools "
                f"{heartbeat.get('last_pool_count', 0):,} "
                f"(exited {heartbeat.get('last_exited_count', 0):,}, active OOR "
                f"{heartbeat.get('last_out_of_range_count', 0):,})",
                "",
            ]
        )

    lines.extend(["## Scanner", ""])
    if not scanner.get("available", False):
        lines.extend([f"Scanner database unavailable: `{scanner.get('path')}`", ""])
    elif scanner.get("error"):
        lines.extend([f"Scanner database read error: {scanner.get('error')}", ""])
    else:
        lines.extend(
            [
                f"- Source: `{scanner.get('path')}`",
                f"- Latest atomic cycle: {scanner.get('latest_as_of') or '—'}",
                f"- Snapshots: {scanner.get('snapshot_count', 0):,}; opportunities "
                f"{scanner.get('opportunity_count', 0):,} (accepted "
                f"{scanner.get('accepted_count', 0):,}, rejected "
                f"{scanner.get('rejected_count', 0):,})",
            ]
        )
        sessions = scanner.get("market_sessions") or {}
        if sessions:
            lines.append(
                "- Market sessions: "
                + ", ".join(f"{name}={count}" for name, count in sorted(sessions.items()))
            )
        reasons = scanner.get("rejection_reasons") or {}
        if reasons:
            lines.append(
                "- Rejections: "
                + "; ".join(f"{reason} ({count})" for reason, count in reasons.items())
            )
        lines.append("")

        top = scanner.get("top_opportunities") or []
        if top:
            lines.extend(
                [
                    "### Latest opportunities",
                    "",
                    "| accepted | symbol | pool | expected net ($) | NetCover | rejection |",
                    "|---|---|---|---:|---:|---|",
                ]
            )
            for row in top:
                lines.append(
                    f"| {'yes' if row.get('accepted') else 'no'} | "
                    f"{row.get('symbol') or '—'} | {str(row.get('pool') or '—')[:18]} | "
                    f"{_fmt_number(row.get('expected_net_yield_usd'))} | "
                    f"{_fmt_number(row.get('netcover_ratio'))} | "
                    f"{row.get('rejection_reason') or '—'} |"
                )
            lines.append("")

    lines.extend(
        [
            "## Safety",
            "",
            "This digest reports shadow evidence only. It does not authorize or perform execution.",
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render runner + scanner shadow digest")
    parser.add_argument("--heartbeat", default=str(DEFAULT_HEARTBEAT))
    parser.add_argument("--scanner-db", default=str(DEFAULT_SCANNER_DB))
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--date", help="UTC date YYYY-MM-DD (default: today)")
    period.add_argument("--all", action="store_true", help="summarize the complete heartbeat")
    parser.add_argument("--out", default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    today = datetime.now(timezone.utc).date().isoformat()
    selected_day = None if args.all else (args.date or today)
    if selected_day is not None:
        try:
            date.fromisoformat(selected_day)
        except ValueError:
            _parser().error("--date must be YYYY-MM-DD")

    heartbeat = summarize_heartbeat(args.heartbeat, day=selected_day)
    scanner = summarize_scanner_db(args.scanner_db)
    markdown = build_digest_markdown(heartbeat, scanner)
    out = Path(args.out) if args.out else (
        REPO_ROOT / "reports/lp_report_digest" / (selected_day or "all") / "daily_digest.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
