#!/usr/bin/env python3
"""RH-04g: resident Shadow daemon ("Stage B's clock"), read-only.

After RH-04f the Shadow closed loop reaches COMPUTED_FAIL on live data with
one named blocker.  The batch replay tool runs once and exits; Stage B needs
>=14 days of continuous Shadow covering a weekend, so this daemon re-runs the
same episode on a fixed period and records, per round, which conjunct blocks,
in which session, for how long.  ``eligible_steps`` stays 0 until the "no
on-chain oracle" policy is resolved; that is expected -- the blocker record
IS the observation Stage B needs.  Reuses run_episode / load_samples_from_db /
episode_summary from scripts.lp_rh_shadow_runner_v1_readonly (not rewritten);
the live DB is opened read-only and all Shadow writes go to the daemon's own
store (reports/lp_rh/shadow.db) plus a per-round scratch store.  No network,
wallet, or broadcast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_market_session_v1_readonly import classify_session
from scripts.lp_rh_shadow_runner_v1_readonly import (  # noqa: E402
    DEFAULT_POOL, episode_summary, load_samples_from_db, run_episode,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store  # noqa: E402

# The daemon's own store (independent file; the other four RH DBs are untouched).
DEFAULT_SHADOW_DB = "reports/lp_rh/shadow.db"
# The live sample source, always opened read-only.  A module constant so tests
# can point it at a scratch live DB without touching reports/.
LIVE_DB = "reports/lp_rh/scanner.db"
DEFAULT_PERIOD_SECS = 900
TARGET_MODE = "SHADOW_SCENARIO"

_EPISODES_DDL = (
    "CREATE TABLE IF NOT EXISTS rh_shadow_episodes (\n"
    "  episode_id TEXT PRIMARY KEY,\n"
    "  started_at TEXT NOT NULL, ended_at TEXT,\n"
    "  pool TEXT NOT NULL, target_mode TEXT NOT NULL,\n"
    "  position_usd TEXT, capital_usd TEXT, horizon_hours INTEGER,\n"
    "  n_samples INTEGER, eligible_steps INTEGER, first_eligible_at TEXT,\n"
    "  status_counts_json TEXT, conjunct_failure_counts_json TEXT,\n"
    "  skipped_at_load INTEGER, steps_without_nav INTEGER,\n"
    "  nav_start TEXT, nav_end TEXT, net_pnl TEXT, hodl_delta TEXT,\n"
    "  pool_meta_hash TEXT, error TEXT\n"
    ");\n")
_BLOCKERS_DDL = (
    "CREATE TABLE IF NOT EXISTS rh_shadow_blockers (\n"
    "  episode_id TEXT NOT NULL, conjunct TEXT NOT NULL,\n"
    "  fail_count INTEGER NOT NULL, sample_session TEXT NOT NULL,\n"
    "  PRIMARY KEY (episode_id, conjunct, sample_session)\n"
    ");\n")


def open_shadow_store(db_path):
    """Open (creating if needed) the daemon's own WAL store with its two tables."""
    conn = open_store(db_path)
    conn.executescript(_EPISODES_DDL + _BLOCKERS_DDL)
    conn.commit()
    return conn


def open_live_store(live_db_path):
    """Open the live sample source read-only (it is never written)."""
    return open_store(live_db_path, read_only=True)


def pool_meta_hash_of(meta_text):
    """sha256 of the pool-meta JSON text, as stored in pool_meta_hash.

    Takes str, not Optional[str]: --pool-meta-json is required, so main always
    passes real text.  I briefly added a None guard here on the assumption that
    omitting the flag would reach this; the flag is required=True, so it cannot.
    The paired test pins the AttributeError as the documented behaviour.
    """
    return hashlib.sha256(meta_text.encode("utf-8")).hexdigest()


def load_pool_meta(path):
    """Read and parse the pool-meta JSON; return (dict, hash).

    The hash reuses pool_meta_hash_of so the episode hash semantics are
    unchanged.  Raises on read or parse failure; the caller decides whether a
    failure is fatal (first load) or a fallback (later episodes).
    """
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text), pool_meta_hash_of(text)


class PoolMetaProvider:
    """Per-episode pool-meta reload with last-known-good fallback.

    load() re-reads the file on every call (once per episode).  A successful
    read becomes the new last-known-good value.  A failed read reuses the
    last-known-good value and appends the error to reload_errors, so the
    failure is visible rather than silent.  Only the very first load, when no
    last-known-good value exists yet, propagates the error -- that preserves
    the daemon's startup-failure behaviour.
    """

    def __init__(self, path):
        self.path = path
        self._last = None
        self.reload_errors = []

    def load(self):
        try:
            self._last = load_pool_meta(self.path)
        except Exception as exc:
            if self._last is None:
                raise
            self.reload_errors.append(repr(exc))
        return self._last


def _money_text(value):
    """Decimal/int/None -> decimal TEXT or None (a missing value is never 0)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    raise TypeError("money value must be Decimal, int, or None")


def _parse_rfc3339(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stamp(rfc3339):
    return _parse_rfc3339(rfc3339).strftime("%Y%m%d%H%M%S")


def _session_of(sample):
    """Session for a sample, derived from its timestamp rather than its column.

    rh_market_states.session is hardcoded to "UNKNOWN" by the collector (see
    lp_rh_collector_v1_readonly line 228), so every row carries UNKNOWN and
    grouping blockers by it would be useless.  The session is a pure function of
    the timestamp and the calendar, so deriving it here is exact, needs no
    collector restart, and makes the rows already collected usable.  Falls back
    to the stored value only when the timestamp cannot be parsed.
    """
    raw = sample.get("sample_time")
    if raw:
        try:
            text = str(raw).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            session, _ = classify_session(parsed, calendar=None)
            return session
        except (TypeError, ValueError):
            pass
    return sample.get("session") or "UNKNOWN"


def blocker_rows_from_steps(steps, samples):
    """Per (conjunct, sample session) failure counts.  steps[i] <-> samples[i];
    the conjunct name is the part of each "<conjunct>: <why>" reason before the first colon."""
    counts = {}
    for step, sample in zip(steps, samples):
        session = _session_of(sample)
        for reason in getattr(step, "conjunct_reasons", ()) or ():
            name = str(reason).split(":", 1)[0].strip()
            counts[(name, session)] = counts.get((name, session), 0) + 1
    return [(n, s, c) for (n, s), c in sorted(counts.items())]


def persist_episode(conn, *, episode_id, started_at, ended_at, pool, target_mode,
                    position_usd, capital_usd, horizon_hours, pool_meta_hash,
                    summary=None, error=None, blocker_rows=None):
    """Upsert one round's episode row and its per-session blocker rows.
    INSERT OR REPLACE on the episode PK collapses a repeated episode_id to one row."""
    s = summary or {}

    def _j(v):
        return json.dumps(v, sort_keys=True) if v is not None else None

    conn.execute(
        "INSERT OR REPLACE INTO rh_shadow_episodes (episode_id, started_at,"
        " ended_at, pool, target_mode, position_usd, capital_usd, horizon_hours,"
        " n_samples, eligible_steps, first_eligible_at, status_counts_json,"
        " conjunct_failure_counts_json, skipped_at_load, steps_without_nav,"
        " nav_start, nav_end, net_pnl, hodl_delta, pool_meta_hash, error)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (episode_id, started_at, ended_at, pool, target_mode,
         _money_text(position_usd), _money_text(capital_usd), horizon_hours,
         s.get("total_steps"), s.get("eligible_steps"),
         s.get("first_eligible_at"), _j(s.get("status_counts")),
         _j(s.get("conjunct_failure_counts")),
         s.get("skipped_at_load"), s.get("steps_without_nav"),
         _money_text(s.get("nav_start")), _money_text(s.get("nav_end")),
         _money_text(s.get("net_pnl")), _money_text(s.get("hodl_delta")),
         pool_meta_hash, error))
    for conjunct, session, count in (blocker_rows or []):
        conn.execute(
            "INSERT OR REPLACE INTO rh_shadow_blockers (episode_id, conjunct,"
            " fail_count, sample_session) VALUES (?,?,?,?)",
            (episode_id, conjunct, count, session))


def _episode_kwargs(cfg, *, episode_id, sample_list, now_fn):
    """The run_episode kwargs shared by the scratch and ledger branches.

    Both branches must pass identical arguments to run_episode (only the
    connection differs), so the kwargs are built in one place.
    """
    return dict(strategy_episode=episode_id, samples=sample_list,
                position_usd=cfg["position_usd"],
                horizon_hours=cfg["horizon_hours"],
                capital_usd=cfg["capital_usd"], target_mode=cfg["target_mode"],
                now_fn=now_fn, pool_meta=cfg["pool_meta"])


def _copy_new_rows(scratch_conn, ledger_conn, existing_decision_ids):
    """Copy the episode's new rows from scratch into the ledger, skipping the
    duplicate decision_ids the ledger already holds (those rows are not
    re-written, and the ledger's existing rows are never deleted)."""
    for row in scratch_conn.execute(
            "SELECT decision_id, candidate_key, target_mode, primary_status,"
            " terminal_bits_json, dominant_blocker, reasons_json,"
            " snapshot_ids_json, decided_at FROM rh_gate_decisions"):
        if row[0] in existing_decision_ids:
            continue
        ledger_conn.execute(
            "INSERT INTO rh_gate_decisions (decision_id, candidate_key,"
            " target_mode, primary_status, terminal_bits_json, dominant_blocker,"
            " reasons_json, snapshot_ids_json, decided_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)", row)
    for row in scratch_conn.execute(
            "SELECT position_id, mark_time, price_snapshot_id, reference_nav,"
            " liquidation_nav, accrued_fee, unvalued_risk_json"
            " FROM rh_position_marks"):
        ledger_conn.execute(
            "INSERT INTO rh_position_marks (position_id, mark_time,"
            " price_snapshot_id, reference_nav, liquidation_nav, accrued_fee,"
            " unvalued_risk_json) VALUES (?,?,?,?,?,?,?)", row)
    for row in scratch_conn.execute(
            "SELECT intent_id, policy_version, bucket, amount_usd, status,"
            " created_at, released_at FROM rh_bucket_reservations"):
        ledger_conn.execute(
            "INSERT INTO rh_bucket_reservations (intent_id, policy_version,"
            " bucket, amount_usd, status, created_at, released_at)"
            " VALUES (?,?,?,?,?,?,?)", row)


def _run_episode_persisted(ledger_conn, *, cfg, episode_id, sample_list, now_fn):
    """Run the episode on the persistent ledger, counting duplicate decision_ids.

    decision_id does not include the episode, so re-running an overlapping
    sample window collides on the rh_gate_decisions PK.  The episode is run on
    the ledger; when a duplicate collides we roll back, re-run on a fresh
    scratch to recover the full steps, count the duplicates, and copy the new
    (non-duplicate) rows into the ledger.  Returns (steps, duplicate_rows).
    """
    kwargs = _episode_kwargs(cfg, episode_id=episode_id, sample_list=sample_list,
                             now_fn=now_fn)
    try:
        steps = run_episode(ledger_conn, **kwargs)
        ledger_conn.commit()
        return steps, 0
    except sqlite3.IntegrityError:
        ledger_conn.rollback()
        with tempfile.TemporaryDirectory() as scratch_dir:
            scratch_conn = open_store(Path(scratch_dir) / "scratch.db")
            migrate(scratch_conn)
            try:
                steps = run_episode(scratch_conn, **kwargs)
                scratch_conn.commit()
                decision_ids = [r[0] for r in scratch_conn.execute(
                    "SELECT decision_id FROM rh_gate_decisions")]
                existing = set()
                if decision_ids:
                    ph = ",".join("?" for _ in decision_ids)
                    existing = {r[0] for r in ledger_conn.execute(
                        "SELECT decision_id FROM rh_gate_decisions WHERE"
                        " decision_id IN (" + ph + ")", decision_ids)}
                _copy_new_rows(scratch_conn, ledger_conn, existing)
                ledger_conn.commit()
            finally:
                scratch_conn.close()
        return steps, len(existing)


def run_one_round(cfg, *, shadow_conn, episode_id, started_at, now_fn):
    """One round: read the latest live samples (read-only), run the episode, and
    upsert the summary into the daemon's store.  When cfg carries ledger_db the
    episode's rows are persisted to that store (duplicates counted, not masked);
    otherwise a throwaway scratch store is used and destroyed."""
    live_conn = open_live_store(cfg["live_db"])
    try:
        sample_list, skipped = load_samples_from_db(
            live_conn, pool=cfg["pool"], limit=cfg["samples"])
    finally:
        live_conn.close()
    ledger_db = cfg.get("ledger_db")
    if ledger_db:
        ledger_conn = open_store(Path(ledger_db))
        migrate(ledger_conn)
        try:
            steps, duplicate_rows = _run_episode_persisted(
                ledger_conn, cfg=cfg, episode_id=episode_id,
                sample_list=sample_list, now_fn=now_fn)
        finally:
            ledger_conn.close()
    else:
        duplicate_rows = None
        with tempfile.TemporaryDirectory() as scratch_dir:
            scratch_conn = open_store(Path(scratch_dir) / "scratch.db")
            migrate(scratch_conn)
            try:
                steps = run_episode(
                    scratch_conn, **_episode_kwargs(
                        cfg, episode_id=episode_id, sample_list=sample_list,
                        now_fn=now_fn))
                scratch_conn.commit()
            finally:
                scratch_conn.close()
    summary = episode_summary(steps, load_skipped=skipped)
    summary["ledger_duplicate_rows"] = duplicate_rows
    persist_episode(
        shadow_conn, episode_id=episode_id, started_at=started_at,
        ended_at=now_fn(), pool=cfg["pool"], target_mode=cfg["target_mode"],
        position_usd=cfg["position_usd"], capital_usd=cfg["capital_usd"],
        horizon_hours=cfg["horizon_hours"],
        pool_meta_hash=cfg["pool_meta_hash"], summary=summary,
        blocker_rows=blocker_rows_from_steps(steps, sample_list))
    shadow_conn.commit()
    return summary


def run_round_safe(cfg, *, shadow_conn, episode_id, now_fn):
    """Run one round; a round exception is recorded in the error column, never
    fatal to the daemon.  Returns 0 either way.  When the ledger is enabled the
    round's ledger_duplicate_rows is printed so the count is visible, not just
    stored in the summary."""
    started_at = now_fn()
    try:
        summary = run_one_round(cfg, shadow_conn=shadow_conn,
                                episode_id=episode_id, started_at=started_at,
                                now_fn=now_fn)
        if summary.get("ledger_duplicate_rows") is not None:
            print(f"[rh-shadow-daemon] {episode_id}: ledger_duplicate_rows="
                  f"{summary['ledger_duplicate_rows']}", file=sys.stderr)
    except Exception as exc:
        print(f"[rh-shadow-daemon] {episode_id}: round failed: {exc!r}",
              file=sys.stderr)
        try:
            persist_episode(
                shadow_conn, episode_id=episode_id, started_at=started_at,
                ended_at=None, pool=cfg["pool"], target_mode=cfg["target_mode"],
                position_usd=cfg["position_usd"],
                capital_usd=cfg["capital_usd"],
                horizon_hours=cfg["horizon_hours"],
                pool_meta_hash=cfg["pool_meta_hash"], error=repr(exc))
            shadow_conn.commit()
        except Exception:
            pass
    return 0


def run_daemon(cfg, *, shadow_conn, period_secs, now_fn, sleep_fn, stop_event,
               pool_meta_provider=None):
    """The resident loop.  Each round's deadline is counted from that round's
    start (not the previous round's end); sleeps in <=1.0s increments so SIGTERM/SIGINT are honored promptly.
    If pool_meta_provider is given, the pool-meta is re-read at the start of
    each episode and that episode's cfg is built from the fresh value, so a
    refreshed gas_usd_estimate takes effect from the next episode on; a failed
    re-read falls back to the last-known-good value (see PoolMetaProvider)."""
    round_index = 0
    while not stop_event.is_set():
        round_start = now_fn()
        episode_id = "rh-shadow-" + _stamp(round_start) + "-" + str(round_index)
        if pool_meta_provider is not None:
            meta, meta_hash = pool_meta_provider.load()
            cfg = {**cfg, "pool_meta": meta, "pool_meta_hash": meta_hash}
        run_round_safe(cfg, shadow_conn=shadow_conn, episode_id=episode_id,
                       now_fn=now_fn)
        round_index += 1
        deadline = _parse_rfc3339(round_start) + timedelta(seconds=period_secs)
        while not stop_event.is_set():
            remaining = (deadline - _parse_rfc3339(now_fn())).total_seconds()
            if remaining <= 0:
                break
            sleep_fn(min(remaining, 1.0))
    return 0


def _utc_now_rfc3339():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="RH-04g resident Shadow daemon (read-only).")
    parser.add_argument("--db", default=DEFAULT_SHADOW_DB, help="own store")
    parser.add_argument("--pool", default=DEFAULT_POOL)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--period-secs", type=int, default=DEFAULT_PERIOD_SECS)
    parser.add_argument("--pool-meta-json", required=True)
    parser.add_argument("--position-usd", required=True)
    parser.add_argument("--capital-usd", required=True)
    parser.add_argument("--horizon-hours", type=float, required=True)
    parser.add_argument("--pid-file", default=None)
    parser.add_argument("--once", action="store_true", help="one round, exit")
    parser.add_argument("--ledger-db", default=None,
                        help="persist every step's gate/mark/reservation rows to "
                             "this store; when omitted each round uses a "
                             "throwaway scratch store and the rows are destroyed")
    args = parser.parse_args(argv)

    # First load at startup: a failure here propagates out of main() exactly as
    # the old one-time read did (startup failure, not a silent fallback).  The
    # provider keeps this value as last-known-good for later episodes.
    provider = PoolMetaProvider(args.pool_meta_json)
    pool_meta, pool_meta_hash = provider.load()
    cfg = {"live_db": LIVE_DB, "pool": args.pool, "samples": args.samples,
           "position_usd": Decimal(args.position_usd),
           "capital_usd": Decimal(args.capital_usd),
           "horizon_hours": args.horizon_hours, "target_mode": TARGET_MODE,
           "pool_meta": pool_meta,
           "pool_meta_hash": pool_meta_hash,
           "ledger_db": args.ledger_db}
    shadow_conn = open_shadow_store(args.db)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    stop_event = threading.Event()

    def _handle(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    now_fn = _utc_now_rfc3339
    try:
        if args.once:
            # --once is a single episode: re-read at its start like any other.
            meta, meta_hash = provider.load()
            cfg = {**cfg, "pool_meta": meta, "pool_meta_hash": meta_hash}
            episode_id = "rh-shadow-" + _stamp(now_fn()) + "-once"
            rc = run_round_safe(cfg, shadow_conn=shadow_conn,
                                episode_id=episode_id, now_fn=now_fn)
        else:
            rc = run_daemon(cfg, shadow_conn=shadow_conn,
                            period_secs=args.period_secs, now_fn=now_fn,
                            sleep_fn=time.sleep, stop_event=stop_event,
                            pool_meta_provider=provider)
    finally:
        shadow_conn.close()
        if args.pid_file:
            Path(args.pid_file).unlink(missing_ok=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
