#!/usr/bin/env python3
"""RH-02g: reorg rollback for the RH read-only pipeline (the second half of T11).

T11 failed because the six derived tables had no block provenance, so a
rollback could not be written.  RH-02f added ``derived_block_hash`` /
``derived_block_number`` and the read-only locator ``rows_derived_from_block``.
This module implements the rollback itself.

Design rules:
  1. Never delete a row.  A reorg means "derived from an abandoned chain",
     not "never existed".  Rows are marked, not removed, so the audit trail
     survives.
  2. A table without provenance is never treated as "unaffected".
     ``rows_derived_from_block`` reports it in ``tables_without_provenance``;
     the rollback surfaces it as ``undecidable`` instead of skipping it.
  3. The rollback is idempotent: rolling back the same block_hash twice
     leaves the database in the same state as rolling it back once.

Local writes only (the ``invalidated_by_block`` marker column); no network,
no chain state, no wallets.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import (
    DEFAULT_DB_PATH,
    DERIVED_TABLES,
    migrate,
    open_store,
    rows_derived_from_block,
)

INVALIDATED_COLUMN = "invalidated_by_block"


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add ``invalidated_by_block TEXT`` to the six derived tables.

    Follows the ``_ensure_columns`` pattern of lp_rh_store_v1_readonly: check
    ``PRAGMA table_info`` first and only ``ALTER TABLE ... ADD COLUMN`` the
    missing one.  Never drops or rebuilds a table, so existing rows and
    primary keys are left untouched.  ``NULL`` = valid; non-NULL = invalidated
    by the reorg of that block_hash.
    """
    for table in DERIVED_TABLES:
        records = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not records:
            continue
        existing = {record[1] for record in records}
        if INVALIDATED_COLUMN not in existing:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {INVALIDATED_COLUMN} TEXT"
            )


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Primary key column names of ``table``, in key order."""
    records = conn.execute(f"PRAGMA table_info({table})").fetchall()
    entries = sorted((record[5], record[1]) for record in records if record[5] > 0)
    return [name for _, name in entries]


def plan_rollback(conn: sqlite3.Connection, *, orphaned_block_hash: str) -> dict:
    """Read-only plan: which rows would be invalidated.  Never writes.

    Returns ``{"orphaned_block_hash", "affected": {table: [pk tuples]},
    "affected_total": int, "tables_without_provenance": [...],
    "undecidable": bool}``.  ``undecidable`` is True when any derived table
    holds rows but records no provenance at all: if one table cannot say
    whether it was affected, the completeness of the whole rollback cannot be
    asserted, and the caller must see that.
    """
    located = rows_derived_from_block(conn, block_hash=orphaned_block_hash)
    without = located.pop("tables_without_provenance")
    affected = {table: located[table] for table in DERIVED_TABLES}
    return {
        "orphaned_block_hash": orphaned_block_hash,
        "affected": affected,
        "affected_total": sum(len(v) for v in affected.values()),
        "tables_without_provenance": without,
        "undecidable": bool(without),
    }


def apply_rollback(conn: sqlite3.Connection, *, orphaned_block_hash: str,
                   plan: Optional[dict] = None) -> dict:
    """Mark (never delete) the rows derived from the orphaned block.

    Sets ``invalidated_by_block`` to ``orphaned_block_hash`` on every affected
    row.  Idempotent: a row already carrying the marker is counted in
    ``already_marked``, not ``marked``.  When ``undecidable`` is True the
    marking still proceeds for every row that can be located; the flag is
    preserved in the result so the caller knows coverage is incomplete.
    """
    if plan is None:
        plan = plan_rollback(conn, orphaned_block_hash=orphaned_block_hash)
    elif plan.get("orphaned_block_hash") not in (None, orphaned_block_hash):
        raise ValueError("plan was computed for a different block_hash")
    _ensure_columns(conn)
    marked: dict = {}
    already: dict = {}
    for table in DERIVED_TABLES:
        pks = plan["affected"].get(table, [])
        if not pks:
            continue
        where = " AND ".join(c + " = ?" for c in _pk_columns(conn, table))
        marked[table] = 0
        already[table] = 0
        for pk in pks:
            cur = conn.execute(
                f"UPDATE {table} SET {INVALIDATED_COLUMN} = ? "
                f"WHERE {where} AND {INVALIDATED_COLUMN} IS NULL",
                (orphaned_block_hash, *pk),
            )
            if cur.rowcount > 0:
                marked[table] += cur.rowcount
            else:
                already[table] += 1
    conn.commit()
    return {
        "marked": marked,
        "marked_total": sum(marked.values()),
        "already_marked": sum(already.values()),
        "undecidable": plan["undecidable"],
    }


def active_rows_only(table: str) -> str:
    """SQL fragment selecting only rows not invalidated by a reorg rollback.

    Returns ``"<table> WHERE invalidated_by_block IS NULL"`` for use in the
    FROM clause of downstream queries.  A downstream query that does NOT use
    this fragment will read rows already invalidated by a reorg.
    """
    return f"{table} WHERE {INVALIDATED_COLUMN} IS NULL"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-02g: reorg rollback (mark, never delete)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--orphaned-block-hash", required=True)
    mode = parser.add_mutually_exclusive_group()
    # store_false implies default=True; pin default=False so that omitting
    # both flags means dry-run.
    mode.add_argument("--dry-run", dest="apply", action="store_false",
                      default=False,
                      help="plan only, change nothing (default)")
    mode.add_argument("--apply", dest="apply", action="store_true",
                      help="mark the affected rows")
    parser.add_argument("--out", default=None,
                        help="write the JSON result to this path")
    args = parser.parse_args(argv)
    conn = open_store(args.db)
    try:
        migrate(conn)
        plan = plan_rollback(conn, orphaned_block_hash=args.orphaned_block_hash)
        if args.apply:
            result = apply_rollback(
                conn, orphaned_block_hash=args.orphaned_block_hash, plan=plan)
            result["mode"] = "apply"
        else:
            result = {"mode": "dry-run", **plan}
    finally:
        conn.close()
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
