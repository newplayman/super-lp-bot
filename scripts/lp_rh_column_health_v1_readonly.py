#!/usr/bin/env python3
"""RH-02r: column health sentinel (offline, read-only).

Catches the defect shape that coverage audits structurally cannot see:
tables that have rows but whose columns are entirely NULL (or constant).
Coverage only asks "is there a sample at this timestamp" and never asks
"how many columns in the sample are empty".

Per-column classification:
  NO_ROWS    - the table has zero rows (distinct from EMPTY: an empty
               table and a table with rows but empty columns differ)
  EMPTY      - every row is NULL in this column
  CONSTANT   - no NULLs and exactly one distinct value
               (e.g. session always "UNKNOWN")
  POPULATED  - anything else (including partially NULL)

Read-only: the only SQL executed is SELECT and PRAGMA; the database is
opened in SQLite read-only mode (mode=ro). No network.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_rh/scanner.db"

# Classification labels.
NO_ROWS = "NO_ROWS"
EMPTY = "EMPTY"
CONSTANT = "CONSTANT"
POPULATED = "POPULATED"

# sample values are truncated to this many characters.
SAMPLE_MAX_CHARS = 60


def _quote(identifier: str) -> str:
    """Double-quote a SQL identifier (table/column name)."""
    return '"' + identifier.replace('"', '""') + '"'


def _to_text(value: Any) -> str:
    """Render a stored value as text for the sample field."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _table_names(conn: sqlite3.Connection, *, prefix: str) -> List[str]:
    """All user tables whose name starts with prefix (sorted)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return sorted(name for (name,) in rows if name.startswith(prefix))


def column_stats(conn: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    """Per-column null/distinct stats and first non-NULL sample.

    Returns one dict per column:
      {"column", "null_count", "distinct_count", "sample"}
    sample is the first non-NULL value truncated to 60 chars, or None.
    """
    cols = [
        row[1]
        for row in conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    ]
    stats: List[Dict[str, Any]] = []
    for col in cols:
        qcol = _quote(col)
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM {_quote(table)} WHERE {qcol} IS NULL"
        ).fetchone()[0]
        distinct_count = conn.execute(
            f"SELECT COUNT(DISTINCT {qcol}) FROM {_quote(table)}"
        ).fetchone()[0]
        row = conn.execute(
            f"SELECT {qcol} FROM {_quote(table)} WHERE {qcol} IS NOT NULL LIMIT 1"
        ).fetchone()
        sample = None if row is None else _to_text(row[0])[:SAMPLE_MAX_CHARS]
        stats.append(
            {
                "column": col,
                "null_count": null_count,
                "distinct_count": distinct_count,
                "sample": sample,
            }
        )
    return stats


def classify_column(stat: Dict[str, Any], *, total_rows: int) -> str:
    """Classify one column stat against the table's total row count.

    NO_ROWS is checked first: an empty table must never be reported as
    EMPTY, and the check must not divide by zero.
    """
    if total_rows == 0:
        return NO_ROWS
    if stat["null_count"] == total_rows:
        return EMPTY
    if stat["null_count"] == 0 and stat["distinct_count"] == 1:
        return CONSTANT
    return POPULATED


def scan_database(conn: sqlite3.Connection, *, prefix: str = "rh_") -> Dict[str, Any]:
    """Scan every table named prefix* and classify all of its columns.

    Returns:
      {"tables": {name: {"total_rows", "columns": [...]}},
       "summary": {"empty_columns": [...], "constant_columns": [...]}}
    summary lists hold "<table>.<column>" strings, sorted.
    """
    tables: Dict[str, Any] = {}
    for name in _table_names(conn, prefix=prefix):
        total_rows = conn.execute(
            f"SELECT COUNT(*) FROM {_quote(name)}"
        ).fetchone()[0]
        tables[name] = {
            "total_rows": total_rows,
            "columns": column_stats(conn, name),
        }
    empty_columns: List[str] = []
    constant_columns: List[str] = []
    for name in sorted(tables):
        total_rows = tables[name]["total_rows"]
        for stat in tables[name]["columns"]:
            label = classify_column(stat, total_rows=total_rows)
            if label == EMPTY:
                empty_columns.append(f"{name}.{stat['column']}")
            elif label == CONSTANT:
                constant_columns.append(f"{name}.{stat['column']}")
    return {
        "tables": tables,
        "summary": {
            "empty_columns": sorted(empty_columns),
            "constant_columns": sorted(constant_columns),
        },
    }


def format_report(scan: Dict[str, Any]) -> str:
    """Human-readable report: one line per column, classification marked."""
    lines: List[str] = ["Column health report", "=" * 72]
    for name in sorted(scan["tables"]):
        info = scan["tables"][name]
        lines.append(f"{name} (total_rows={info['total_rows']})")
        for stat in info["columns"]:
            label = classify_column(stat, total_rows=info["total_rows"])
            sample = stat["sample"]
            lines.append(
                f"  {stat['column']:<28} nulls={stat['null_count']:<8} "
                f"distinct={stat['distinct_count']:<8} {label:<10} "
                f"{'-' if sample is None else sample}"
            )
    lines.append("")
    lines.append(f"empty_columns ({len(scan['summary']['empty_columns'])}):")
    lines.extend(f"  {item}" for item in scan["summary"]["empty_columns"])
    lines.append(f"constant_columns ({len(scan['summary']['constant_columns'])}):")
    lines.extend(f"  {item}" for item in scan["summary"]["constant_columns"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Column health sentinel (read-only): flag tables whose "
        "columns are entirely NULL or constant."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH),
                        help="path to the SQLite database (opened read-only)")
    parser.add_argument("--prefix", default="rh_",
                        help="only scan tables whose name starts with this")
    parser.add_argument("--json", action="store_true",
                        help="emit the raw scan dict as JSON")
    parser.add_argument("--fail-on-empty", action="store_true",
                        help="exit 1 if any column is EMPTY (for cron/watchdog)")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=30.0)
    try:
        scan = scan_database(conn, prefix=args.prefix)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(scan, indent=2, sort_keys=True))
    else:
        print(format_report(scan))

    if args.fail_on_empty and scan["summary"]["empty_columns"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
