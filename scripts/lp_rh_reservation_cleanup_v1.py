#!/usr/bin/env python3
"""RH-02ch: Clean up orphaned bucket reservations left by pre-cap-check daemon runs.

Idempotently releases orphaned PENDING reservations via release() without DELETING
rows, preserving historical evidence of cap failure.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_bucket_ledger_v1_readonly import (
    POLICY_ID,
    bucket_active_cap,
    release,
    reserved_total,
)
from scripts.lp_rh_store_v1_readonly import open_store


def parse_utc_iso(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        s = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def extract_candidate_episodes(intent_id: str) -> List[str]:
    candidates = [intent_id]
    if intent_id.startswith("rh-shadow-"):
        rest = intent_id[len("rh-shadow-"):]
        candidates.append(rest)
        if "-" in rest:
            ep = rest.rsplit("-", 1)[0]
            candidates.extend([ep, f"rh-shadow-{ep}"])
    if "-" in intent_id:
        ep = intent_id.rsplit("-", 1)[0]
        candidates.extend([ep, f"rh-shadow-{ep}"])
    out, seen = [], set()
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def latest_open_episode(conn: sqlite3.Connection) -> Optional[str]:
    """The episode of the most recently opened shadow position, or None.

    Shadow holds at most one virtual position at a time (run_episode guards with
    position_open), and since RH-02ce an episode releases its own reservation on
    normal completion. So a reservation still sitting PENDING belongs to an
    episode that has already ended -- unless it is the one currently running,
    which is the most recent by opened_at.
    """
    try:
        # closed_at is NULL for every row Shadow writes today (there is no close
        # path), so in practice this picks the most recent episode. The filter
        # still matters: an episode that *has* been closed is finished by
        # definition and its reservation is an orphan regardless of recency, and
        # it keeps the criterion correct once a close path exists.
        row = conn.execute(
            "SELECT strategy_episode FROM rh_shadow_positions "
            "WHERE closed_at IS NULL ORDER BY opened_at DESC LIMIT 1").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def belongs_to_latest_episode(intent_id: str, latest_episode: Optional[str]) -> bool:
    """True when this reservation was made by the most recent episode."""
    if not latest_episode:
        return False
    return str(intent_id).startswith(f"rh-shadow-{latest_episode}-")


def has_unclosed_position(conn: sqlite3.Connection, intent_id: str) -> bool:
    try:
        candidates = extract_candidate_episodes(intent_id)
        placeholders = ", ".join("?" for _ in candidates)
        row = conn.execute(
            f"SELECT 1 FROM rh_shadow_positions "
            f"WHERE (strategy_episode IN ({placeholders}) OR position_id IN ({placeholders})) "
            f"AND closed_at IS NULL LIMIT 1",
            tuple(candidates) + tuple(candidates),
        ).fetchone()
        if row is not None:
            return True
        row = conn.execute(
            "SELECT 1 FROM rh_shadow_positions "
            "WHERE (? LIKE position_id || '-%' OR ? LIKE 'rh-shadow-' || strategy_episode || '-%') "
            "AND closed_at IS NULL LIMIT 1",
            (intent_id, intent_id),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def scan_reservations(
    conn: sqlite3.Connection, *, older_than_hours: float = 1.0,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    cutoff = now_dt - timedelta(hours=older_than_hours)
    rows = conn.execute(
        "SELECT intent_id, policy_version, bucket, amount_usd, status, created_at, released_at "
        "FROM rh_bucket_reservations WHERE status = 'PENDING' AND released_at IS NULL "
        "ORDER BY created_at ASC, intent_id ASC"
    ).fetchall()
    latest_ep = latest_open_episode(conn)
    all_pending, orphans = [], []
    total_pending_usd = Decimal("0")
    semantic_count, semantic_usd = 0, Decimal("0")
    time_count, time_usd = 0, Decimal("0")
    for r in rows:
        intent_id, pol, bucket, amt_str, status, created_at, _ = r
        amt = Decimal(amt_str)
        item = {
            "intent_id": intent_id, "policy_version": pol, "bucket": bucket,
            "amount_usd": amt, "status": status, "created_at": created_at,
        }
        all_pending.append(item)
        total_pending_usd += amt
        # closed_at is never set -- Shadow has no close path -- so
        # has_unclosed_position() is true for every episode that ever opened one
        # and can never identify an orphan. What actually distinguishes a live
        # reservation is whether its episode is the one still running.
        is_live = belongs_to_latest_episode(intent_id, latest_ep)
        has_pos = is_live
        created_dt = parse_utc_iso(created_at)
        older = bool(created_dt is not None and created_dt < cutoff)
        if not has_pos:
            semantic_count += 1
            semantic_usd += amt
            crit = ["EPISODE_ENDED"]
            if older:
                crit.append(f"OLDER_THAN_{older_than_hours}H")
            item["criterion"] = ",".join(crit)
            orphans.append(item)
        if older:
            time_count += 1
            time_usd += amt
    return {
        "all_pending": all_pending, "total_pending_count": len(all_pending),
        "total_pending_usd": total_pending_usd,
        "semantic_count": semantic_count, "semantic_usd": semantic_usd,
        "time_count": time_count, "time_usd": time_usd,
        "orphans": orphans, "orphan_count": len(orphans),
        "orphan_usd": sum((o["amount_usd"] for o in orphans), Decimal("0")),
    }


def execute_cleanup(
    conn: sqlite3.Connection, *, orphans: List[Dict[str, Any]],
    now_str: Optional[str] = None,
) -> Tuple[int, int]:
    if now_str is None:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    released, failed = 0, 0
    for o in orphans:
        if release(conn, o["intent_id"], now=now_str, reason="ORPHANED_PRE_CAP_FIX"):
            released += 1
        else:
            failed += 1
    if released > 0:
        conn.commit()
    return released, failed


def run_cleanup(
    db_path: str | Path, *, capital_usd: Decimal = Decimal("10000"),
    older_than_hours: float = 1.0, apply: bool = False, bucket: str = "CORE",
    policy_version: str = POLICY_ID, now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = open_store(Path(db_path), read_only=not apply)
    try:
        cap = bucket_active_cap(capital_usd, bucket)
        cur_reserved = reserved_total(conn, bucket, policy_version)
        cur_room = cap - cur_reserved
        scan = scan_reservations(conn, older_than_hours=older_than_hours, now_dt=now_dt)
        print("=" * 70 + "\nRH-02ch Reservation Cleanup Report")
        print(f"Database: {db_path} (mode={'RW' if apply else 'RO'})")
        print(f"Total PENDING: {scan['total_pending_count']} ({scan['total_pending_usd']} USD)")
        print(f"  - Semantic criterion (episode already ended): {scan['semantic_count']} ({scan['semantic_usd']} USD)")
        print(f"  - Time criterion (older than {older_than_hours}h): {scan['time_count']} ({scan['time_usd']} USD)")
        print(f"Orphans identified (semantic priority): {scan['orphan_count']} ({scan['orphan_usd']} USD)\n" + "-" * 70)
        for o in scan["orphans"]:
            print(f"  {o['intent_id']} | {o['amount_usd']} USD | {o['created_at']} | {o['criterion']}")
        print("-" * 70)
        print(f"{bucket} active cap: {cap} USD (capital: {capital_usd} USD)")
        print(f"Current reserved_total: {cur_reserved} USD | room: {cur_room} USD")
        released, failed = 0, 0
        if apply:
            released, failed = execute_cleanup(conn, orphans=scan["orphans"], now_str=now_str)
            post_reserved = reserved_total(conn, bucket, policy_version)
            post_room = cap - post_reserved
            print(f"APPLY: Released {released} reservations, failed {failed}")
            print(f"Cleaned reserved_total: {post_reserved} USD | room: {post_room} USD")
        else:
            orphan_sum = sum((o["amount_usd"] for o in scan["orphans"] if o["bucket"] == bucket), Decimal("0"))
            post_reserved = cur_reserved - orphan_sum
            post_room = cap - post_reserved
            print(f"Projected reserved_total: {post_reserved} USD | room: {post_room} USD")
            print("DRY-RUN: 未修改任何数据，加 --apply 才会写库")
        print("=" * 70)
        return {
            "scan": scan, "cap": cap, "cur_reserved": cur_reserved, "cur_room": cur_room,
            "post_reserved": post_reserved, "post_room": post_room,
            "apply": apply, "released": released, "failed": failed,
        }
    finally:
        conn.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Clean up orphaned reservations (RH-02ch)")
    parser.add_argument("--db", default="reports/lp_rh/scanner.db", help="path to scanner db")
    parser.add_argument("--older-than-hours", type=float, default=1.0, help="age in hours")
    parser.add_argument("--capital-usd", default="10000", help="total capital in USD")
    parser.add_argument("--apply", action="store_true", help="actually release reservations")
    parser.add_argument("--bucket", default="CORE", help="bucket name")
    parser.add_argument("--policy-version", default=POLICY_ID, help="policy version")
    args = parser.parse_args(argv)
    run_cleanup(
        args.db, capital_usd=Decimal(args.capital_usd), older_than_hours=args.older_than_hours,
        apply=args.apply, bucket=args.bucket, policy_version=args.policy_version,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
