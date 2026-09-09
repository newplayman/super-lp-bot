#!/usr/bin/env python3
"""RH-04g: Shadow daemon watchdog, read-only.

Watches the daemon's own store (reports/lp_rh/shadow.db) and reports whether
the resident Shadow daemon is alive: it prints the latest episode row and the
latest blocker rows, and exits

  0  OK      -- latest episode's started_at is fresh
  1  NO_DATA -- store missing, empty, or without any episode rows
  2  STALE   -- latest episode's started_at is older than
                --stale-multiplier x --period-secs (the daemon has stopped)

The store is opened read-only (file:...?mode=ro); nothing is ever written and
no network is used.  An unparseable started_at fails closed to STALE: the
watchdog cannot prove freshness, so it reports the daemon as down.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SHADOW_DB = "reports/lp_rh/shadow.db"
DEFAULT_PERIOD_SECS = 900.0
DEFAULT_STALE_MULTIPLIER = 3.0

_EXIT_BY_STATUS = {"OK": 0, "NO_DATA": 1, "STALE": 2}


def open_shadow_db_readonly(db_path):
    """Open the daemon store read-only.  Raises FileNotFoundError if absent
    (a missing store is reported as NO_DATA, never created)."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_rfc3339(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def latest_episode(conn):
    """The most recent episode row (started_at, then episode_id as tiebreak)."""
    row = conn.execute(
        "select * from rh_shadow_episodes"
        " order by started_at desc, episode_id desc limit 1").fetchone()
    return _row_to_dict(row) if row else None


def latest_blocker_episode_id(conn):
    """episode_id of the most recent episode that has at least one blocker row
    (the latest episode may have none, e.g. after the blocker is resolved)."""
    row = conn.execute(
        "select e.episode_id from rh_shadow_episodes e"
        " where exists (select 1 from rh_shadow_blockers b"
        "               where b.episode_id = e.episode_id)"
        " order by e.started_at desc, e.episode_id desc limit 1").fetchone()
    return row[0] if row else None


def blocker_rows(conn, episode_id):
    cur = conn.execute(
        "select episode_id, conjunct, sample_session, fail_count"
        " from rh_shadow_blockers where episode_id = ?"
        " order by conjunct, sample_session", (episode_id,))
    return [_row_to_dict(r) for r in cur.fetchall()]


def watchdog(db_path, *, period_secs, stale_multiplier, now):
    """Return (status, payload) with status in {"OK", "NO_DATA", "STALE"}.
    ``now`` is an aware datetime (injected for tests; main uses real UTC)."""
    try:
        conn = open_shadow_db_readonly(db_path)
    except FileNotFoundError:
        return "NO_DATA", {"db": str(db_path), "reason": "db file missing",
                           "latest_episode": None, "latest_blockers": [],
                           "blocker_episode_id": None}
    try:
        has_table = conn.execute(
            "select count(*) from sqlite_master where type='table'"
            " and name='rh_shadow_episodes'").fetchone()[0]
        if not has_table:
            return "NO_DATA", {"db": str(db_path),
                               "reason": "no rh_shadow_episodes table",
                               "latest_episode": None, "latest_blockers": [],
                               "blocker_episode_id": None}
        episode = latest_episode(conn)
        if episode is None:
            return "NO_DATA", {"db": str(db_path), "reason": "no episode rows",
                               "latest_episode": None, "latest_blockers": [],
                               "blocker_episode_id": None}
        blocker_ep = latest_blocker_episode_id(conn)
        blockers = blocker_rows(conn, blocker_ep) if blocker_ep else []
        payload = {"db": str(db_path), "now": now.isoformat(),
                   "latest_episode": episode, "latest_blockers": blockers,
                   "blocker_episode_id": blocker_ep}
        try:
            started = _parse_rfc3339(episode["started_at"])
        except (TypeError, ValueError):
            payload["reason"] = "unparseable started_at"
            return "STALE", payload
        age_secs = (now - started).total_seconds()
        threshold_secs = period_secs * stale_multiplier
        payload["age_secs"] = age_secs
        payload["stale_threshold_secs"] = threshold_secs
        status = "STALE" if age_secs > threshold_secs else "OK"
        return status, payload
    finally:
        conn.close()


def _print_human(status, p):
    print(f"RH-04g shadow watchdog: {status}")
    print(f"db: {p['db']}")
    if p.get("reason"):
        print(f"reason: {p['reason']}")
        return
    ep = p["latest_episode"]
    print(f"latest_episode: {ep['episode_id']}")
    for key in ("started_at", "ended_at", "pool", "n_samples",
                "eligible_steps", "status_counts_json", "error"):
        print(f"  {key}={ep.get(key)}")
    print(f"age_secs={p['age_secs']:.1f}"
          f" stale_threshold_secs={p['stale_threshold_secs']:.1f}")
    if p["latest_blockers"]:
        print(f"latest_blockers (episode={p['blocker_episode_id']}):")
        for b in p["latest_blockers"]:
            print(f"  conjunct={b['conjunct']}"
                  f" session={b['sample_session']}"
                  f" count={b['fail_count']}")
    else:
        print("latest_blockers: (none)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="RH-04g Shadow daemon watchdog (read-only).")
    parser.add_argument("--db", default=DEFAULT_SHADOW_DB,
                        help="daemon store (opened read-only)")
    parser.add_argument("--period-secs", type=float,
                        default=DEFAULT_PERIOD_SECS,
                        help="daemon period the staleness threshold scales from")
    parser.add_argument("--stale-multiplier", type=float,
                        default=DEFAULT_STALE_MULTIPLIER,
                        help="stale when age > multiplier x period-secs")
    parser.add_argument("--now", default=None,
                        help="RFC3339 override for 'now' (tests)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    now = _parse_rfc3339(args.now) if args.now else datetime.now(timezone.utc)
    status, payload = watchdog(args.db, period_secs=args.period_secs,
                               stale_multiplier=args.stale_multiplier, now=now)
    if args.as_json:
        payload["status"] = status
        print(json.dumps(payload, sort_keys=True))
    else:
        _print_human(status, payload)
    return _EXIT_BY_STATUS[status]


if __name__ == "__main__":
    sys.exit(main())
