#!/usr/bin/env python3
"""RH-02k: reorg-divergence resolution (which hash is the orphan, then roll back).

The detector (lp_rh_capabilities_v1_readonly.provider_independence) reports
BLOCK_HASH_DIVERGENCE when two providers disagree on the hash at one height,
but does NOT say which hash is the orphan.  That moment's information cannot
identify the canonical chain, so calling apply_rollback directly would pick one
arbitrarily and could invalidate correct data.  This module adds the mandatory
confirmation step: record_contested (register, no rollback) -> resolve_contested
(re-query after the head advanced >= min_depth; winner canonical, loser orphan)
-> apply_resolved_rollbacks (roll back ONLY resolved orphans, reusing
plan_rollback / apply_rollback, never rewritten).

A divergence stays CONTESTED until a deeper re-query decides it; a re-query that
finds neither hash (or a third) is UNRESOLVABLE or stays CONTESTED -- never
guessed, and never rolled back.  Rollback delegates to apply_rollback (mark,
never delete; idempotent).  Local writes only; no network, no chain state.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_reorg_rollback_v1_readonly import (
    apply_rollback,
    plan_rollback,
)
from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH, open_store

CONTENDED_TABLE = "rh_reorg_contested"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_table(conn: sqlite3.Connection) -> None:
    """Idempotently create rh_reorg_contested.

    PK (block_number, hash_a, hash_b) so the same divergence is one row;
    orphaned_hash is NULL until a deeper re-query decides the orphan.
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CONTENDED_TABLE} (
            block_number   INTEGER NOT NULL,
            hash_a         TEXT NOT NULL,
            hash_b         TEXT NOT NULL,
            first_seen_at  TEXT NOT NULL,
            resolved_at    TEXT,
            canonical_hash TEXT,
            orphaned_hash  TEXT,
            status         TEXT NOT NULL,
            PRIMARY KEY (block_number, hash_a, hash_b)
        )
        """
    )
    conn.commit()


def record_contested(conn: sqlite3.Connection, *, block_number: int,
                     hash_a: str, hash_b: str,
                     now: Optional[str] = None) -> dict:
    """Register a divergence.  NO rollback here; status=CONTESTED.

    Idempotent: same (block_number, hash_a, hash_b) combo is one row
    (INSERT OR IGNORE).  Returns {..., "created"} (False if pre-existed).
    """
    ensure_table(conn)
    now = now or _utc_now()
    cur = conn.execute(
        f"""
        INSERT OR IGNORE INTO {CONTENDED_TABLE}
            (block_number, hash_a, hash_b, first_seen_at, status)
        VALUES (?, ?, ?, ?, 'CONTESTED')
        """,
        (block_number, hash_a, hash_b, now),
    )
    conn.commit()
    return {
        "block_number": block_number,
        "hash_a": hash_a,
        "hash_b": hash_b,
        "status": "CONTESTED",
        "created": cur.rowcount > 0,
    }


def resolve_contested(conn: sqlite3.Connection, *, block_number: int,
                      canonical_hash_fn: Callable[[int], Optional[str]],
                      now: Optional[str] = None,
                      min_depth: int = 64) -> dict:
    """Decide which hash is the orphan via a deeper re-query.

    canonical_hash_fn(block_number) -> str | None is injected by the caller
    (real impl re-queries the hash after the head advanced >= min_depth).
    For every CONTESTED row at block_number: fn==hash_a -> orphan=hash_b,
    RESOLVED; fn==hash_b -> orphan=hash_a, RESOLVED; fn None -> stays
    CONTESTED (do NOT guess); fn a third hash -> UNRESOLVABLE, orphan None
    (both providers wrong or a multi-reorg; neither side may be rolled back).
    """
    ensure_table(conn)
    now = now or _utc_now()
    canonical = canonical_hash_fn(block_number)
    rows = conn.execute(
        f"""
        SELECT hash_a, hash_b FROM {CONTENDED_TABLE}
        WHERE block_number = ? AND status = 'CONTESTED'
        """,
        (block_number,),
    ).fetchall()
    resolved = 0
    unresolvable = []
    still = 0
    for hash_a, hash_b in rows:
        if canonical is None:
            still += 1
            continue
        if canonical == hash_a:
            orphan, canon = hash_b, hash_a
        elif canonical == hash_b:
            orphan, canon = hash_a, hash_b
        else:
            conn.execute(
                f"""
                UPDATE {CONTENDED_TABLE}
                SET status = 'UNRESOLVABLE', resolved_at = ?,
                    canonical_hash = NULL, orphaned_hash = NULL
                WHERE block_number = ? AND hash_a = ? AND hash_b = ?
                """,
                (now, block_number, hash_a, hash_b),
            )
            unresolvable.append({"hash_a": hash_a, "hash_b": hash_b})
            continue
        conn.execute(
            f"""
            UPDATE {CONTENDED_TABLE}
            SET status = 'RESOLVED', resolved_at = ?,
                canonical_hash = ?, orphaned_hash = ?
            WHERE block_number = ? AND hash_a = ? AND hash_b = ?
            """,
            (now, canon, orphan, block_number, hash_a, hash_b),
        )
        resolved += 1
    conn.commit()
    return {
        "block_number": block_number,
        "canonical_hash": canonical,
        "min_depth": min_depth,
        "resolved": resolved,
        "unresolvable": len(unresolvable),
        "unresolvable_rows": unresolvable,
        "still_contested": still,
    }


def apply_resolved_rollbacks(conn: sqlite3.Connection, *,
                             now: Optional[str] = None) -> dict:
    """Roll back ONLY the RESOLVED orphans; never CONTESTED / UNRESOLVABLE.

    For each RESOLVED row with a non-NULL orphaned_hash, delegate to
    apply_rollback (mark, never delete; idempotent).  Returns
    {"resolved_count", "rolled_back": {orphan: result},
    "undecidable_tables": [...]} (union of tables_without_provenance).
    """
    ensure_table(conn)
    rows = conn.execute(
        f"""
        SELECT orphaned_hash FROM {CONTENDED_TABLE}
        WHERE status = 'RESOLVED' AND orphaned_hash IS NOT NULL
        ORDER BY block_number, hash_a, hash_b
        """
    ).fetchall()
    rolled_back: dict = {}
    undecidable: set = set()
    for (orphaned_hash,) in rows:
        plan = plan_rollback(conn, orphaned_block_hash=orphaned_hash)
        undecidable.update(plan["tables_without_provenance"])
        rolled_back[orphaned_hash] = apply_rollback(
            conn, orphaned_block_hash=orphaned_hash, plan=plan)
    return {
        "resolved_count": len(rows),
        "rolled_back": rolled_back,
        "undecidable_tables": sorted(undecidable),
    }


def _default_canonical_hash_fn(block_number: int) -> Optional[str]:
    """Offline default: no chain access, so it cannot decide (returns None).

    The caller must inject a real re-query for resolution to make progress.
    """
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-02k: reorg-divergence resolution (mark, never delete)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--block-number", type=int, default=None)
    parser.add_argument("--hash-a", default=None)
    parser.add_argument("--hash-b", default=None)
    parser.add_argument("--resolve", action="store_true",
                        help="resolve CONTESTED rows at --block-number")
    parser.add_argument("--apply", action="store_true",
                        help="roll back the RESOLVED orphans")
    parser.add_argument("--out", default=None,
                        help="write the JSON result to this path")
    args = parser.parse_args(argv)

    register = (args.block_number is not None and args.hash_a is not None
                and args.hash_b is not None
                and not args.resolve and not args.apply)
    if not (register or args.resolve or args.apply):
        print(json.dumps({"mode": "no-op", "changed": False}, indent=2))
        return 0

    conn = open_store(args.db)
    try:
        results = []
        if register:
            results.append(record_contested(
                conn, block_number=args.block_number,
                hash_a=args.hash_a, hash_b=args.hash_b))
        if args.resolve:
            if args.block_number is None:
                raise SystemExit("--resolve requires --block-number")
            results.append(resolve_contested(
                conn, block_number=args.block_number,
                canonical_hash_fn=_default_canonical_hash_fn))
        if args.apply:
            results.append(apply_resolved_rollbacks(conn))
        payload = results[0] if len(results) == 1 else results
    finally:
        conn.close()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
