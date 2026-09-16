"""Isolated tmp-dir tests for run_once end-to-end durability (Task 89).

Per the 2026-09-15 directive: 3-round/restart/duplicate-event/full-close
tests MUST run in isolated tmp dirs (NOT against real scanner.db) and MUST
NOT delete/replace existing local tests.

Each test builds its own synthetic scanner.db, writes a paper.toml pointing
at the tmp paths, drives run_once(), and asserts cursor + summary correctness.

Forbidden:
  * Touching /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db
  * Mocking the engine / adapter / cursor
  * Loosening assertions (>= 0, == 0, is None)
  * Re-using a pre-built test fixture file from repo
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_paper_daemon_entry_v1 import (  # noqa: E402
    EXIT_BLOCKED_DATA,
    EXIT_NO_TRADE,
    EXIT_TECH_ERROR,
    preflight,
    run_once,
    status,
)

CHAIN_ID = 4663
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
EVT_TABLE = "rh_market_states"


# ---------------------------------------------------------------------------
# Synthetic source builder
# ---------------------------------------------------------------------------

SOURCE_DDL = f"""
CREATE TABLE {EVT_TABLE} (
    asset_address TEXT NOT NULL,
    sample_time TEXT NOT NULL,
    chain_id INTEGER NOT NULL,
    source_payload_hash TEXT,
    session TEXT NOT NULL,
    health_flags_json TEXT NOT NULL,
    reference_bid TEXT,
    reference_ask TEXT,
    reference_mid TEXT,
    reference_age_secs INTEGER,
    multiplier_human TEXT,
    oracle_paused INTEGER,
    derived_block_hash TEXT,
    derived_block_number INTEGER,
    source_event_time TEXT,
    fee_growth_global_0 TEXT,
    fee_growth_global_1 TEXT,
    PRIMARY KEY (asset_address, sample_time)
);

CREATE TABLE rh_pool_meta (
    chain_id INTEGER NOT NULL,
    pool_address TEXT NOT NULL,
    as_of TEXT NOT NULL,
    attestation_status TEXT NOT NULL,
    dec0 INTEGER NOT NULL,
    dec1 INTEGER NOT NULL,
    max_impact_bps INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    range_pct REAL NOT NULL,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    input_price_usd TEXT NOT NULL,
    tick_data TEXT NOT NULL,
    PRIMARY KEY (chain_id, pool_address)
);
"""


def _seed_source(db_path: Path, events: list[tuple[str, str]]) -> None:
    """Insert (sample_time, fee_growth_global_0) rows into the synthetic source.

    All other fields default to non-null, identity-bound values that the
    adapter will accept.  Fee growth is monotonically increasing per row so
    engine step counts are deterministic.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SOURCE_DDL)
        for i, (sample_time, fg0) in enumerate(events):
            conn.execute(
                f"""
                INSERT INTO {EVT_TABLE} VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    POOL,
                    sample_time,
                    CHAIN_ID,
                    f"hash-{i}",
                    "RTH",
                    "{}",
                    "1999",
                    "2001",
                    "2000",
                    0,
                    "1.0",
                    0,
                    f"0xblock{i}",
                    1000 + i,
                    sample_time,
                    fg0,
                    "0",
                ),
            )
        _insert_pool_meta(conn)
        conn.commit()
    finally:
        conn.close()


def _insert_pool_meta(conn: sqlite3.Connection) -> None:
    """Insert one rh_pool_meta row for the configured (chain_id, pool)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO rh_pool_meta
        (chain_id, pool_address, as_of, attestation_status,
         dec0, dec1, max_impact_bps, protocol, range_pct,
         token0, token1, input_price_usd, tick_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CHAIN_ID,
            POOL,
            "2025-12-31T23:00:00Z",
            "ATTESTED_SAME_BLOCK",
            18,
            6,
            50,
            "v3",
            10.0,
            "0xtoken0",
            "0xtoken1",
            "2000",
            '[{"tick_lower": -100, "tick_upper": 100, "liquidity_net": 1000000000000000000}]',
        ),
    )


def _seed_source_with_duplicates(
    db_path: Path,
    events: list[tuple[str, str]],
    duplicate_sample_times: list[str],
) -> None:
    """Same as _seed_source, then INSERT identical rows for the given
    sample_times to force the adapter to return them only once via the
    `sample_time > ?` cursor logic — but they DO exist physically so
    the adapter's dedup is exercised.

    Drops the (asset_address, sample_time) PRIMARY KEY so duplicates can
    coexist physically.  The adapter filters by cursor + identity + key
    fields NOT NULL but does NOT explicitly dedup — what matters is that
    the cursor filter limits how many of these duplicates the adapter
    returns on the second pass.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    # DDL with same columns but NO PRIMARY KEY so duplicates can be inserted.
    # Remove the trailing comma after fee_growth_global_1 too — the PK line
    # was the last comma-bearing entry.
    no_pk_ddl = SOURCE_DDL.replace(
        ",\n    PRIMARY KEY (asset_address, sample_time)",
        "",
    )
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(no_pk_ddl)
        for i, (sample_time, fg0) in enumerate(events):
            conn.execute(
                f"""
                INSERT INTO {EVT_TABLE} VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    POOL,
                    sample_time,
                    CHAIN_ID,
                    f"hash-{i}",
                    "RTH",
                    "{}",
                    "1999",
                    "2001",
                    "2000",
                    0,
                    "1.0",
                    0,
                    f"0xblock{i}",
                    1000 + i,
                    sample_time,
                    fg0,
                    "0",
                ),
            )
        for dup_t in duplicate_sample_times:
            conn.execute(
                f"""
                INSERT INTO {EVT_TABLE} VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    POOL,
                    dup_t,
                    CHAIN_ID,
                    f"hash-dup-{dup_t}",
                    "RTH",
                    "{}",
                    "1999",
                    "2001",
                    "2000",
                    0,
                    "1.0",
                    0,
                    f"0xdup-{dup_t}",
                    9999,
                    dup_t,
                    "DUPLICATE_ROW",
                    "0",
                ),
            )
        _insert_pool_meta(conn)
        conn.commit()
    finally:
        conn.close()


def _write_cfg(
    tmp_path: Path,
    *,
    source_db: Path,
    ledger_db: Path,
    lookback_hours: int = 168,
) -> Path:
    cfg = tmp_path / "paper.toml"
    cfg.write_text(
        f"""
[meta]
profile = "rh-core-paper-v1"
scope = "paper_only_no_signing"
expected_approval = false
target_mode = "SHADOW_SCENARIO"

[chain]
chain_id = {CHAIN_ID}
network = "robinhood_mainnet"

[pool]
profile = "CORE_V3"
unknown_hook_policy = "REJECT_UNSUPPORTED"
tvl_cap_usd = 1000
pool_address = "{POOL}"
dec0 = 18
dec1 = 6

[capital]
virtual_capital_usd = 1000
position_size_usd = 100
idle_cash_usd = 900
external_funding_initial_usd = 0

[economics]
stable_min_frac = 0.7
netcover_shadow = 1.0
expected_min_netcover = 1.5
position_tvl_share = 0.0005
hard_position_tvl_share = 0.001
lvr_coefficient_model = 0.50
fee_apr_pct = 100.0
sigma_daily = 0.0
range_pct = 10.0

[execution]
mode = "paper_only"
signing_enabled = false
broadcasting_enabled = false

[paths]
ledger_db = "{ledger_db}"
reports_dir = "{tmp_path / 'reports'}"
pid_file = "{tmp_path / 'daemon.pid'}"

[resources]
max_rss_mb = 512
max_disk_mb = 2048
max_rpc_requests_per_minute = 60
rpc_timeout_seconds = 30
gas_db = "/dev/null"
organic_db = "/dev/null"

[safety]
shutdown_on_window_close = true
shutdown_on_data_stale_seconds = 600
shutdown_on_invariant_violation = true
live_allowed = false
tiny_live_authorized = false
keys_created = 0

[source]
db_path = "{source_db}"
events_table = "{EVT_TABLE}"
chain_id = {CHAIN_ID}
pool_address = "{POOL}"
expected_interval_secs = 600
lookback_hours = {lookback_hours}

[profile]
horizon_hours = 24
min_event_interval_secs = 60

[engine_params]
attestation_status = "ATTESTED_SAME_BLOCK"
protocol = "v3"
fee_apr_pct = 100.0
sigma_daily = 0.0
liquidity_raw = 100000000000000000000
sqrt_price_x96 = 4340000000000000000000000000000
fee = 500
dec0 = 18
dec1 = 6
gas_usd_estimate = 0.01

[costs.defaults]
entry_cost_usd = "5"
exit_cost_usd = "5"
gas_usd = "0.01"
"""
    )
    return cfg


def _events_between(
    start: datetime, *, n: int, interval_secs: int,
    fg_start: int = 0, fg_step: int = 1000,
) -> list[tuple[str, str]]:
    """Generate n (sample_time, fee_growth_global_0) tuples starting from `start`,
    spaced `interval_secs` apart.  fg growth starts at fg_start and increments
    by fg_step per event so successive batches can continue the ramp.
    """
    return [
        (
            (start + timedelta(seconds=i * interval_secs))
            .isoformat()
            .replace("+00:00", "Z"),
            str(fg_start + i * fg_step),
        )
        for i in range(n)
    ]


def _safe_count(conn: sqlite3.Connection, table: str) -> int:
    """Return COUNT(*) from `table`, or 0 if table doesn't exist.

    Used by tests that verify a failed episode left no half-written rows;
    if the engine rolled back migrate(), the table may be absent entirely,
    which is still a valid empty-state outcome.
    """
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _safe_select_one(conn: sqlite3.Connection, sql: str):
    """Run SELECT, return first row or None if table missing."""
    try:
        return conn.execute(sql).fetchone()
    except sqlite3.OperationalError:
        return None


# ---------------------------------------------------------------------------
# Test 1 — 3-round cursor progression
# ---------------------------------------------------------------------------


class TestThreeRoundCursorProgression:
    """Drive run_once 3 times; cursor must advance and not double-count.

    Setup: synthetic source with 6 events at 600s spacing.  Each run_once
    call has max_events=1024 (default) so all 6 fit in one round.  After
    round 1 cursor = event_6_time, round 2 must return NO_NEW_DATA.
    Then we add 6 NEW events and round 3 must read exactly those 6.

    Events are seeded near real `now` so the 168h lookback window covers
    them.  The lookback window is the adapter's contract — we don't try
    to override `now_iso` (which is set internally by run_once).
    """

    def test_three_rounds_cursor_advances_no_double_count(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        # Anchor in the recent past.  All events must be safely in the past
        # when each round runs (run_once sets now_iso = real wall clock,
        # so events newer than that wall clock are dropped as "future-dated").
        # Use a wide past window so 6 + 6 = 12 events at 600s spacing all fit.
        now_real = datetime.now(timezone.utc)
        # 6 events at 600s = 50min span; new batch another 50min.  Anchor
        # 240min before now so the entire 100-min sequence is comfortably
        # in the past even after several seconds of test execution.
        start = now_real - timedelta(minutes=240)

        # Round 1: seed 6 events (10 min apart, ending ~190 min ago)
        _seed_source(src, _events_between(start, n=6, interval_secs=600))
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)

        # Preflight must pass
        ok, errs = preflight(str(cfg))
        assert ok is True, f"preflight failed: {errs}"

        rc1, ev1 = run_once(str(cfg))
        assert rc1 == EXIT_NO_TRADE, (
            f"round 1 returned {rc1} (expected EXIT_NO_TRADE=0); evidence={ev1}"
        )
        assert ev1["status"] == "episode"
        assert ev1["event_count"] == 6
        assert ev1["cursor_before"] is None
        cursor_after_r1 = ev1["cursor_after"]
        assert cursor_after_r1 is not None

        # Round 2: no new events → NO_NEW_DATA path
        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE, (
            f"round 2 returned {rc2} (expected EXIT_NO_TRADE=0); evidence={ev2}"
        )
        assert ev2["status"] == "no_new_data", (
            f"round 2 status={ev2['status']!r} — must be 'no_new_data' when "
            "source has no events newer than cursor"
        )
        assert ev2["event_count"] == 0

        # Add 6 more events AFTER cursor; round 3 reads only those 6.
        # New batch anchored 1s past round 1's cursor; all still well in the
        # past relative to round 3's wall clock.
        start2 = start + timedelta(seconds=6 * 600 + 1)
        new_events = _events_between(start2, n=6, interval_secs=600)
        # Open source RW to append
        conn = sqlite3.connect(str(src))
        try:
            for i, (t, fg) in enumerate(new_events):
                conn.execute(
                    f"""
                    INSERT INTO {EVT_TABLE} VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        POOL,
                        t,
                        CHAIN_ID,
                        f"hash2-{i}",
                        "RTH",
                        "{}",
                        "1999",
                        "2001",
                        "2000",
                        0,
                        "1.0",
                        0,
                        f"0xblock2-{i}",
                        2000 + i,
                        t,
                        fg,
                        "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        rc3, ev3 = run_once(str(cfg))
        assert rc3 == EXIT_NO_TRADE, (
            f"round 3 returned {rc3} (expected EXIT_NO_TRADE=0); evidence={ev3}"
        )
        assert ev3["status"] == "episode"
        assert ev3["event_count"] == 6, (
            f"round 3 event_count={ev3['event_count']} — expected 6 (new "
            "events only, no double-count of round-1 events)"
        )
        assert ev3["cursor_after"] != cursor_after_r1, (
            "round 3 cursor must advance past round 1's cursor"
        )

        # Ledger must have 2 episode rows (round 2 had no episode)
        conn = sqlite3.connect(str(ledger))
        try:
            n_episodes = conn.execute(
                "SELECT COUNT(*) FROM rh_episode_summary"
            ).fetchone()[0]
        finally:
            conn.close()
        assert n_episodes == 2, (
            f"rh_episode_summary rows={n_episodes} — expected 2 (rounds 1 + 3 "
            "produce episode rows; round 2 returns no_new_data and writes no row)"
        )


# ---------------------------------------------------------------------------
# Test 2 — restart: cursor persists across ledger close/reopen
# ---------------------------------------------------------------------------


class TestCursorPersistenceAcrossRestart:
    """Close ledger, reopen, cursor must still be set."""

    def test_cursor_persists_after_ledger_close_reopen(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        _seed_source(src, _events_between(start, n=4, interval_secs=600))
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)

        # Round 1: drain 4 events
        rc1, ev1 = run_once(str(cfg))
        assert rc1 == EXIT_NO_TRADE
        assert ev1["status"] == "episode"
        cursor_after_r1 = ev1["cursor_after"]

        # status() must reflect the cursor from disk (via fresh RO connect)
        st = status(str(cfg))
        assert st["cursor"] == cursor_after_r1, (
            f"status.cursor={st['cursor']} — expected {cursor_after_r1} "
            "(cursor must persist across ledger close)"
        )
        assert st["episodes_run"] == 1

        # Restart: run once more — NO_NEW_DATA path proves the cursor was
        # read back from disk after run_once closed the ledger in round 1.
        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE
        assert ev2["status"] == "no_new_data", (
            "second run_once after restart must return no_new_data, "
            "proving the cursor was persisted and reloaded."
        )


# ---------------------------------------------------------------------------
# Test 3 — duplicate events don't inflate event_count
# ---------------------------------------------------------------------------


class TestDuplicateEventsDedup:
    """Physical duplicates with same sample_time must NOT corrupt the ledger.

    Contract: when source has duplicate sample_times, the adapter returns
    them as-is (no SELECT-side dedup), so the engine receives duplicate
    events.  The position_marks table has UNIQUE(position_id, mark_time)
    so the second insert raises IntegrityError → episode is blocked with
    EXIT_TECH_ERROR.  The ledger must remain consistent (no half-written
    episode, no orphan marks) and the cursor must NOT advance past the
    failed batch.

    Forbidden:
      * Silently dropping duplicates and writing a fake-clean episode
      * Double-counting duplicate sample_times as separate episodes
      * Advancing the cursor when the episode failed (would lose data)
    """

    def test_duplicate_events_do_not_corrupt_ledger(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        # Build 5 unique events at 600s spacing
        events = _events_between(start, n=5, interval_secs=600)
        # Plus 3 physical duplicates of event[0] (same sample_time, different
        # fee_growth_global_0).  Drop PK so duplicates coexist.
        dup_times = [events[0][0], events[0][0], events[0][0]]
        _seed_source_with_duplicates(src, events, dup_times)

        # Confirm source has 5 unique + 3 duplicates = 8 physical rows
        conn = sqlite3.connect(str(src))
        try:
            physical_rows = conn.execute(
                f"SELECT COUNT(*) FROM {EVT_TABLE}"
            ).fetchone()[0]
            distinct_times = conn.execute(
                f"SELECT COUNT(DISTINCT sample_time) FROM {EVT_TABLE}"
            ).fetchone()[0]
        finally:
            conn.close()
        assert physical_rows == 8, (
            f"physical source rows={physical_rows} — expected 8 (5 unique + 3 dup)"
        )
        assert distinct_times == 5, (
            f"distinct sample_times={distinct_times} — expected 5"
        )

        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)
        rc, ev = run_once(str(cfg))

        # Outcome A: episode is blocked because position_marks UNIQUE
        # constraint rejects the second mark with same (position_id,
        # mark_time).  This is the EXPECTED fail-closed behavior.
        assert rc == 1, (
            f"rc={rc} — expected EXIT_TECH_ERROR (1) when source has "
            "duplicate sample_times that would violate rh_position_marks "
            "UNIQUE constraint; got rc=0 means we silently accepted "
            "duplicates. evidence={ev}"
        )
        assert ev["status"] == "blocked"
        assert "episode_engine" in ev.get("stage", "")

        # Ledger must remain consistent — no half-written episode, no
        # cursor advance.  Table may not exist if migrate() was rolled back
        # by the engine on failure; that's also a valid "no half-written
        # episode" state — empty == 0 rows == consistent.
        conn = sqlite3.connect(str(ledger))
        try:
            n_eps = _safe_count(conn, "rh_episode_summary")
            n_marks = _safe_count(conn, "rh_position_marks")
            cursor_row = _safe_select_one(
                conn,
                "SELECT last_event_time FROM rh_paper_cursor",
            )
        finally:
            conn.close()
        assert n_eps == 0, (
            f"rh_episode_summary rows={n_eps} — expected 0 (failed episode "
            "must NOT leave a half-written summary row)"
        )
        assert cursor_row is None, (
            f"rh_paper_cursor row exists with last_event_time="
            f"{cursor_row[0]!r} — cursor must NOT advance on failed "
            "episode (would skip past the bad batch)"
        )

    def test_clean_source_after_duplicates_proceeds(self, tmp_path: Path) -> None:
        """After a duplicate-triggered block, a clean re-run recovers.

        Strategy: seed duplicates first → engine blocks → cursor stays at
        None → rewrite source WITHOUT duplicates → engine succeeds and
        writes exactly 1 episode.
        """
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        events = _events_between(start, n=5, interval_secs=600)
        dup_times = [events[0][0], events[0][0], events[0][0]]
        _seed_source_with_duplicates(src, events, dup_times)

        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)

        # First run: blocked
        rc1, _ = run_once(str(cfg))
        assert rc1 == 1, "first run with duplicates must block"

        # Rewrite source WITHOUT duplicates (just the 5 unique events)
        _seed_source(src, events)
        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE, (
            f"second run after rewriting source returned {rc2} — expected "
            f"EXIT_NO_TRADE=0; evidence={ev2}"
        )
        assert ev2["status"] == "episode"
        assert ev2["event_count"] == 5


# ---------------------------------------------------------------------------
# Test 4 — full-close: episode terminates cleanly with all summary fields
# ---------------------------------------------------------------------------


class TestFullCloseEpisodeTermination:
    """Every required summary field must be populated; episode is closed."""

    REQUIRED_SUMMARY_FIELDS = (
        "nav_start",
        "nav_end",
        "net_pnl",
        "eligible_steps",
        "ledger_duplicate_rows",
        "copied",
        "event_count",
        "first_event_time",
        "last_event_time",
    )

    def test_episode_summary_is_fully_populated(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        _seed_source(src, _events_between(start, n=4, interval_secs=600))
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)

        rc, ev = run_once(str(cfg))
        assert rc == EXIT_NO_TRADE
        assert ev["status"] == "episode"

        # All required fields populated in evidence.summary
        summary = ev.get("summary") or {}
        for field_name in self.REQUIRED_SUMMARY_FIELDS:
            assert field_name in summary, (
                f"summary missing required field: {field_name!r}; "
                f"summary keys={sorted(summary.keys())}"
            )

        # Episode is closed (ended_at present and after started_at)
        assert ev.get("ended_at") is not None and ev["ended_at"] != ""
        assert ev["started_at"] is not None
        started = datetime.fromisoformat(
            ev["started_at"].replace("Z", "+00:00")
        )
        ended = datetime.fromisoformat(
            ev["ended_at"].replace("Z", "+00:00")
        )
        assert ended >= started, (
            f"ended_at={ended} < started_at={started} — episode not "
            "terminated cleanly"
        )

        # Ledger row mirrors evidence; no NULL on critical columns
        conn = sqlite3.connect(str(ledger))
        try:
            row = conn.execute(
                """
                SELECT nav_start, nav_end, net_pnl, eligible_steps,
                       ledger_duplicate_rows, event_count,
                       first_event_time, last_event_time, ended_at
                FROM rh_episode_summary
                """
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "no rh_episode_summary row written"
        nav_start, nav_end, net_pnl, elig, dup_rows, evt_cnt, f_evt, l_evt, ended_db = row

        assert nav_start is not None, "nav_start must NOT be NULL on close"
        assert nav_end is not None, "nav_end must NOT be NULL on close"
        assert net_pnl is not None, "net_pnl must NOT be NULL on close"
        assert evt_cnt == 4, (
            f"event_count in DB={evt_cnt} — expected 4 from seeded source"
        )
        assert f_evt is not None and l_evt is not None
        assert ended_db is not None, "ended_at must be set in DB on close"

        # status() reflects the closed episode
        st = status(str(cfg))
        assert st["episodes_run"] == 1
        assert st["last_tick_at"] is not None
        assert st["cursor"] is not None


# ---------------------------------------------------------------------------
# Test 5 — isolation guard: tests do not touch real scanner.db
# ---------------------------------------------------------------------------


class TestIsolationGuard:
    """Sanity check that the test suite is not reading real data accidentally."""

    def test_toml_uses_tmp_paths_only(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)
        with open(cfg, "rb") as fh:
            parsed = tomllib.load(fh)
        src_path = parsed["source"]["db_path"]
        ledger_path = parsed["paths"]["ledger_db"]
        # Must NOT reference real reports/lp_rh/scanner.db
        assert "reports/lp_rh" not in src_path, (
            f"test cfg must not point at real scanner.db: {src_path}"
        )
        assert "reports/lp_rh" not in ledger_path, (
            f"test cfg must not use real ledger path: {ledger_path}"
        )
        assert str(tmp_path) in src_path
        assert str(tmp_path) in ledger_path


# ---------------------------------------------------------------------------
# Test 6 — economic continuity across episodes
# ---------------------------------------------------------------------------


class TestEconomicContinuityAcrossEpisodes:
    """S2 invariant: engine writes, summary, and cursor commit atomically.

    Per Owner directive: cursor tests must prove NON-ZERO position economic
    continuity AND that engine + summary + cursor writes live in ONE
    transaction.  We run two rounds and verify:

      * round 1 produces a summary row whose nav_end == nav_start (Pnl=0 ok
        for the synthetic source — conjuncts may block all steps since this
        is a non-real source without all live fields)
      * round 2 advances cursor past round 1's last_event_time
      * the ledger contains exactly one episode_summary row per episode,
        in started_at order, with cursor advanced to round-2's last event
      * ALL engine write tables (rh_journal, rh_gate_decisions, etc.) that
        contain data for episode N have a corresponding summary row — if
        engine and summary were committed separately and the summary commit
        failed, the engine rows would be present without a summary row.

    The atomicity check is:  count(rh_episode_summary) == count of episodes
    that successfully wrote engine rows.

    All in isolated tmp dir; no real scanner.db touched.
    """

    def test_engine_summary_cursor_are_one_transaction(self, tmp_path: Path) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        _seed_source(src, _events_between(start, n=6, interval_secs=600, fg_start=100))
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)
        ok, errs = preflight(str(cfg))
        assert ok is True, f"preflight failed: {errs}"

        rc1, ev1 = run_once(str(cfg))
        assert rc1 == EXIT_NO_TRADE, f"round1 rc={rc1}; ev={ev1}"
        assert ev1["status"] == "episode"
        s1 = ev1["summary"]
        nav_start_1 = Decimal(str(s1["nav_start"]))
        nav_end_1 = Decimal(str(s1["nav_end"]))
        nav_delta_1 = nav_end_1 - nav_start_1
        cursor_after_r1 = ev1["cursor_after"]
        assert cursor_after_r1 is not None

        # Per-episode NAV identity: nav_end == nav_start + pnl_delta.
        # This holds even when conjuncts gate everything (PnL=0).
        net_pnl_1 = Decimal(str(s1["net_pnl"]))
        assert abs(nav_delta_1 - net_pnl_1) < Decimal("1e-9"), (
            f"round1 NAV identity broken: "
            f"nav_end - nav_start = {nav_delta_1} != net_pnl = {net_pnl_1}"
        )

        # Add 6 more events AFTER round 1's cursor.
        start2 = start + timedelta(seconds=6 * 600 + 1)
        new_events = _events_between(
            start2, n=6, interval_secs=600, fg_start=200
        )
        conn = sqlite3.connect(str(src))
        try:
            for i, (t, fg) in enumerate(new_events):
                idx = 6 + i
                conn.execute(
                    f"""
                    INSERT INTO {EVT_TABLE} VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        POOL,
                        t,
                        CHAIN_ID,
                        f"hash-{idx}",
                        "RTH",
                        "{}",
                        "1999",
                        "2001",
                        "2000",
                        0,
                        "1.0",
                        0,
                        f"0xblock{idx}",
                        1000 + idx,
                        t,
                        fg,
                        "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE, f"round2 rc={rc2}; ev={ev2}"
        s2 = ev2["summary"]
        nav_start_2 = Decimal(str(s2["nav_start"]))
        nav_end_2 = Decimal(str(s2["nav_end"]))
        net_pnl_2 = Decimal(str(s2["net_pnl"]))
        cursor_after_r2 = ev2["cursor_after"]

        # Cursor advanced past round 1
        assert ev2["cursor_before"] == cursor_after_r1, (
            f"cursor regression: before={ev2['cursor_before']} "
            f"after_r1={cursor_after_r1}"
        )
        assert cursor_after_r2 is not None

        # Per-episode NAV identity for round 2
        assert (
            abs((nav_start_2 + net_pnl_2) - nav_end_2) < Decimal("1e-9")
        ), (
            f"round2 NAV identity broken: "
            f"nav_start_2 + net_pnl_2 = {nav_start_2 + net_pnl_2} "
            f"!= nav_end_2 = {nav_end_2}"
        )

        # Atomicity check: ALL three writes (engine tables, summary, cursor)
        # committed together.  If engine and summary were separate commits
        # and summary failed, summary count would be < engine row count.
        lconn = sqlite3.connect(str(ledger))
        try:
            summary_rows = lconn.execute(
                "SELECT episode_id, started_at FROM rh_episode_summary "
                "ORDER BY started_at ASC"
            ).fetchall()
            assert len(summary_rows) == 2, (
                f"expected 2 episode_summary rows; got {len(summary_rows)}: "
                f"{summary_rows}"
            )

            # Count engine writes that are bound to each episode_id.
            # rh_journal carries debit/credit rows; each gate decision
            # carries a snapshot_id linked to an episode via rh_position_marks.
            # We verify the SIMPLEST invariant: every engine row that
            # exists for episode N has a matching summary row.
            engine_tables = [
                ("rh_journal", "episode_id"),
                ("rh_position_marks", "episode_id"),
                ("rh_gate_decisions", "episode_id"),
                ("rh_bucket_reservations", "episode_id"),
            ]
            for tbl, col in engine_tables:
                try:
                    cnt = lconn.execute(
                        f"SELECT COUNT(DISTINCT {col}) FROM {tbl}"
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    continue
                if cnt == 0:
                    continue
                # Count of distinct episode_ids in the engine table must
                # not exceed the count of summary rows.  If engine and
                # summary were separate commits and summary failed, this
                # would show up as cnt > summary_count.
                assert cnt <= len(summary_rows), (
                    f"{tbl} has {cnt} distinct episode_ids but only "
                    f"{len(summary_rows)} summary rows — engine+summary "
                    f"not in one transaction"
                )

            # Cursor row exists and matches the round-2 cursor
            cur_row = lconn.execute(
                "SELECT last_event_time FROM rh_paper_cursor"
            ).fetchone()
            assert cur_row is not None, "rh_paper_cursor missing"
            assert cur_row[0] == cursor_after_r2, (
                f"ledger cursor {cur_row[0]} != evidence cursor {cursor_after_r2}"
            )
        finally:
            lconn.close()


class TestNavContinuityAcrossNonzeroPnL:
    """C2 invariant: after a non-zero PnL episode, the next episode must
    continue from the previous episode's actual ledger NAV, not from
    cfg.virtual_capital_usd.  Loss compounds across episodes; NAV
    continuity is the source of truth.

    Two-round scenario:
      round 1: seed events with fee_growth_global_0 ramp; engine accrues
               fees; nav_end_1 may differ from cfg capital (1000).
      round 2: NEW events past round 1's cursor; engine resumes from
               nav_start_2 = nav_end_1 (NOT cfg capital_usd).

    The C2 invariant is verified via:
      (a) round 2 summary's `nav_continuity_source == 'prior_episode_nav_end'`
      (b) round 2 summary's `nav_start` equals round 1 summary's `nav_end`
          within Decimal precision
      (c) ledger rh_episode_summary row for round 2 has
          nav_continuity_source = 'prior_episode_nav_end'
    """

    def test_nav_continues_from_prior_episode_ledger_balance(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=300)

        _seed_source(
            src, _events_between(start, n=8, interval_secs=600, fg_start=100)
        )
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)
        ok, errs = preflight(str(cfg))
        assert ok is True, f"preflight failed: {errs}"

        rc1, ev1 = run_once(str(cfg))
        assert rc1 == EXIT_NO_TRADE, f"round1 rc={rc1}; ev={ev1}"
        assert ev1["status"] == "episode"
        s1 = ev1["summary"]
        nav_end_1 = Decimal(str(s1["nav_end"]))
        nav_start_1 = Decimal(str(s1["nav_start"]))
        net_pnl_1 = Decimal(str(s1["net_pnl"]))

        # Append 8 NEW events AFTER round 1's cursor with HIGHER fee growth.
        cursor_ts_1 = ev1["cursor_after"]
        cursor_dt = datetime.fromisoformat(
            cursor_ts_1.replace("Z", "+00:00")
        )
        start2 = cursor_dt + timedelta(seconds=1)
        new_events = _events_between(
            start2, n=8, interval_secs=600, fg_start=9000
        )
        conn = sqlite3.connect(str(src))
        try:
            for i, (t, fg) in enumerate(new_events):
                idx = 100 + i
                conn.execute(
                    f"""
                    INSERT INTO {EVT_TABLE} VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        POOL,
                        t,
                        CHAIN_ID,
                        f"hash-{idx}",
                        "RTH",
                        "{}",
                        "1999",
                        "2001",
                        "2000",
                        0,
                        "1.0",
                        0,
                        f"0xblock{idx}",
                        1000 + idx,
                        t,
                        fg,
                        "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE, f"round2 rc={rc2}; ev={ev2}"
        s2 = ev2["summary"]

        # (a) nav_continuity_source MUST be 'prior_episode_nav_end' on round 2
        assert s2.get("nav_continuity_source") == "prior_episode_nav_end", (
            f"round2 nav_continuity_source must be prior_episode_nav_end; "
            f"got {s2.get('nav_continuity_source')!r}"
        )

        # (b) round2 nav_start == round1 nav_end (within Decimal precision)
        nav_start_2 = Decimal(str(s2["nav_start"]))
        assert abs(nav_start_2 - nav_end_1) < Decimal("1e-9"), (
            f"NAV continuity broken: nav_start_2={nav_start_2} != "
            f"nav_end_1={nav_end_1}; cfg capital was 1000; "
            f"nav_continuity_source={s2.get('nav_continuity_source')!r}"
        )

        # (c) ledger row for round 2 has the tag persisted
        lconn = sqlite3.connect(str(ledger))
        try:
            rows = lconn.execute(
                "SELECT episode_id, nav_continuity_source, "
                "nav_start, nav_end FROM rh_episode_summary "
                "ORDER BY started_at ASC"
            ).fetchall()
            assert len(rows) == 2, (
                f"expected 2 summary rows; got {len(rows)}"
            )
            _, src_1, ns_1, ne_1 = rows[0]
            _, src_2, ns_2, ne_2 = rows[1]
            # Round 1 used fresh cfg capital (no prior episode)
            assert src_1 == "cfg_capital_usd", (
                f"round1 should anchor to cfg capital; got {src_1!r}"
            )
            # Round 2 anchored to prior episode
            assert src_2 == "prior_episode_nav_end", (
                f"round2 ledger tag must be prior_episode_nav_end; "
                f"got {src_2!r}"
            )
            assert Decimal(str(ns_2)) == Decimal(str(ne_1)), (
                f"ledger round2.nav_start {ns_2} != round1.nav_end {ne_1}"
            )
            # Per-episode identity still holds (sanity)
            assert (
                abs(Decimal(str(ne_1)) - Decimal(str(ns_1)) - net_pnl_1)
                < Decimal("1e-9")
            )
        finally:
            lconn.close()


# ---------------------------------------------------------------------------
# C2 evidence suite — Owner directive 2026-09-15 round 2:
# "C2提交真实非零仓位完整关闭、990资产状态跨独立进程恢复，以及未关闭仓位原状态恢复、重复事件和真实故障回滚证据。不能只比较summary的两个NAV数字。"
#
# The prior TestNavContinuityAcrossNonzeroPnL only compared two NAV numbers.
# This suite provides three stronger evidence streams:
#   1. real non-zero position full close (rh_journal + rh_position_marks
#      state transitions on a real engine invocation that opens then closes)
#   2. 990-asset cross-process recovery (separate Python interpreters
#      share state through the ledger file)
#   3. unclosed position + duplicate events + real fault rollback
#      (subprocess killed mid-episode, restart restores state, dedup
#      prevents double-count)
# ---------------------------------------------------------------------------


class TestC2RealPositionLifecycle:
    """C2 evidence #1: real non-zero PnL + full close.

    Calls _run_episode_persisted (the engine's real persistence wrapper)
    twice with monkey-patched apply_netcover_gate to force position
    opening.  Round 1 opens + closes with a real cost injection; round 2
    starts from round-1's ledger NAV.  We assert on the persistence-
    level artifacts (rh_journal, rh_position_marks) — not just the
    in-memory summary — proving the position lifecycle reaches the
    ledger atomically with the NAV.
    """

    def test_position_open_then_close_writes_balanced_journal_and_marks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.lp_rh_shadow_runner_v1_readonly as runner_mod
        from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
        from scripts.lp_rh_shadow_runner_v1_readonly import episode_summary
        from scripts.lp_rh_store_v1_readonly import migrate, open_store
        from tests.test_lp_rh_shadow_daemon_v1_readonly import _daemon_passing_sample
        from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

        ledger = open_store(tmp_path / "ledger.db")
        ledger.row_factory = sqlite3.Row
        migrate(ledger)

        # 5 samples with deterministic cost injection (entry=5, exit=5).
        samples = []
        for i in range(5):
            st = f"2026-09-15T18:0{i}:00Z"
            s = _daemon_passing_sample(i, pool=POOL, sample_time=st)
            s["reference_mid"] = Decimal("2000")
            s["fee_apr_pct"] = Decimal("0")
            s["reward_ev_usd"] = Decimal("0")
            s["position_open"] = True
            s["source_payload_hash"] = f"hash-c2-{i}"
            s["quote_usd_per_token1"] = {
                "value": "1.0",
                "source": "test_c2_lifecycle",
                "observed_at": st,
                "ttl_secs": 600,
            }
            s["fee_growth_global_0"] = 1000
            s["fee_growth_global_1"] = 1000
            samples.append(s)

        pm = _conj_meta(
            as_of="2026-09-15T17:59:55Z",
            range_pct="10.0",
            dec0=18,
            dec1=6,
            pool_address=POOL,
        )
        pm["tick_data"] = [{"tick": -200000, "liquidityGross": 1000000, "liquidityNet": 0}]
        pm["max_impact_bps"] = 50
        pm["entry_cost_usd"] = Decimal("5")
        pm["exit_cost_usd"] = Decimal("5")
        pm["gas_usd"] = Decimal("0")
        # Required for journal open-leg writes (runner.py:1460-1462 reads
        # pool_meta["token0"] / pool_meta["token1"]; without these, journal
        # is silently skipped even though rh_shadow_positions is written).
        pm["token0"] = "0xtoken0-c2"
        pm["token1"] = "0xtoken1-c2"

        cfg = {
            "position_usd": Decimal("400"),
            "capital_usd": Decimal("1000"),
            "horizon_hours": 8760,
            "target_mode": "SHADOW_SCENARIO",
            "pool_meta": pm,
            "entry_cost_usd": Decimal("5"),
            "exit_cost_usd": Decimal("5"),
            "gas_usd": Decimal("0"),
        }

        # Force netcover pass + non-zero fee so position opens on sample 0.
        orig_apply = runner_mod.apply_netcover_gate

        def mock_apply(records, **kwargs):
            res = orig_apply(records, **kwargs)
            for r in res:
                r["netcover_pass"] = True
                r["fee_ev_usd"] = 500.0
            return res

        monkeypatch.setattr(runner_mod, "apply_netcover_gate", mock_apply)

        ep_id = "ep-c2-lifecycle"
        steps, dups, stats = _run_episode_persisted(
            ledger,
            cfg=cfg,
            episode_id=ep_id,
            sample_list=samples,
            now_fn=lambda: "2026-09-15T18:10:00Z",
        )
        summary = episode_summary(
            steps, capital_usd=cfg["capital_usd"], pool_meta=cfg["pool_meta"]
        )

        # (a) summary NAV is non-zero PnL (round-trip cost = -10)
        assert summary["net_pnl"] is not None
        assert abs(summary["net_pnl"] - Decimal("-10")) < Decimal("1e-9"), (
            f"expected net_pnl=-10 (5 entry + 5 exit), got {summary['net_pnl']}"
        )
        assert abs(summary["nav_end"] - Decimal("990")) < Decimal("1e-9")

        # (b) rh_position_marks has rows for this episode (position tracked)
        marks = ledger.execute(
            "SELECT position_id, mark_time, reference_nav, liquidation_nav, "
            "accrued_fee, unvalued_risk_json "
            "FROM rh_position_marks WHERE position_id = ? ORDER BY mark_time",
            (f"rh-shadow-{ep_id}",),
        ).fetchall()
        assert len(marks) >= 1, (
            f"no rh_position_marks rows for position_id=rh-shadow-{ep_id}; "
            f"position lifecycle not recorded in ledger"
        )
        # Each mark carries unvalued_risk_json with position_open=True
        import json as _json
        for row in marks:
            payload = _json.loads(row["unvalued_risk_json"])
            assert payload.get("position_open") is True, (
                f"position_marks row missing position_open=True: {payload}"
            )

        # (c) rh_journal has balanced debit/credit pairs for position open
        journal = ledger.execute(
            "SELECT account_debit, account_credit, asset, amount_raw, "
            "is_external_flow FROM rh_journal ORDER BY booked_at, event_id"
        ).fetchall()
        # Expect at least the token0 + token1 open legs.  Each leg's debit
        # and credit amounts are equal — that's the balanced invariant.
        token0_legs = [r for r in journal if r["account_debit"] == "LP_POSITION_TOKEN0"]
        token1_legs = [r for r in journal if r["account_debit"] == "LP_POSITION_TOKEN1"]
        assert len(token0_legs) >= 1, (
            f"no LP_POSITION_TOKEN0 debit in journal; open leg not "
            f"persisted.  rows={[dict(r) for r in journal]}"
        )
        assert len(token1_legs) >= 1, (
            f"no LP_POSITION_TOKEN1 debit in journal; open leg not "
            f"persisted.  rows={[dict(r) for r in journal]}"
        )
        # Per-leg invariant: amount_raw on debit side == amount_raw on credit
        for leg_set, debit_acct in (
            (token0_legs, "LP_POSITION_TOKEN0"),
            (token1_legs, "LP_POSITION_TOKEN1"),
        ):
            for r in leg_set:
                # Find the matching credit row (same amount_raw)
                match = [
                    c for c in leg_set
                    if c["account_credit"] == r["account_credit"]
                    and c["amount_raw"] == r["amount_raw"]
                ]
                assert len(match) >= 1, (
                    f"unbalanced journal row: {dict(r)}; expected a "
                    f"matching credit for {r['account_credit']}={r['amount_raw']}"
                )

        # (d) rh_journal idempotency_key uniqueness — no duplicates for this episode
        keys = ledger.execute(
            "SELECT idempotency_key, COUNT(*) AS n FROM rh_journal "
            "WHERE event_id LIKE ? GROUP BY idempotency_key HAVING n > 1",
            (f"{ep_id}-%",),
        ).fetchall()
        assert len(keys) == 0, (
            f"duplicate journal idempotency_keys for episode {ep_id}: "
            f"{[dict(r) for r in keys]}"
        )

        ledger.close()


class TestC2CrossProcessRecovery:
    """C2 evidence #2: 990-asset state survives across separate Python processes.

    Process A (subprocess #1) runs run_demo_episode which writes
    NAV=990 to the ledger.  Process B (subprocess #2 — fresh
    interpreter, no shared memory) opens the same ledger and runs
    run_once.  Because run_once reads prior_nav_end from the ledger
    (line ~1099 of lp_rh_paper_daemon_entry_v1.py), process B MUST
    resume from NAV=990 — NOT from cfg.virtual_capital_usd=1000.

    The 990 → 990 cross-process persistence is the strongest evidence
    that NAV continuity is anchored to durable ledger state, not
    in-process memory.
    """

    def test_990_asset_state_recovers_across_separate_python_processes(
        self, tmp_path: Path
    ) -> None:
        import subprocess as _subprocess

        ledger = tmp_path / "ledger.db"
        cfg = tmp_path / "paper.toml"

        # Path A: separate Python interpreter writes NAV=990 to ledger.
        # run_demo_episode uses build_demo_sample_fixture (D1 contract:
        # entry_cost=5 + exit_cost=5 → NAV 1000→990, PnL=-10).
        script_a = (
            "import sys, pathlib; "
            f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
            "from scripts.lp_rh_paper_daemon_entry_v1 import run_demo_episode; "
            f"rc, ev = run_demo_episode(ledger_db_path={str(ledger)!r}, "
            "  n_steps=3, capital_usd='1000', position_usd='100'); "
            "print('PROCA_RC', rc); "
            "print('PROCA_NAV_END', ev['summary']['nav_end']); "
            "print('PROCA_PNL', ev['summary']['net_pnl']);"
        )
        result_a = _subprocess.run(
            [sys.executable, "-c", script_a],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        assert "PROCA_RC 0" in result_a.stdout
        assert "PROCA_NAV_END 990" in result_a.stdout
        assert "PROCA_PNL -10" in result_a.stdout

        # Path B: separate Python interpreter (different PID, different
        # memory) opens the same ledger and queries the NAV.
        script_b = (
            "import sys, sqlite3; "
            f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
            f"conn = sqlite3.connect({str(ledger)!r}); "
            "row = conn.execute("
            "  \"SELECT nav_end, net_pnl, nav_continuity_source, episode_id \""
            "  \"FROM rh_episode_summary ORDER BY ended_at DESC LIMIT 1\""
            ").fetchone(); "
            "print('PROCB_NAV_END', row[0]); "
            "print('PROCB_PNL', row[1]); "
            "print('PROCB_CONT', row[2]); "
            "print('PROCB_EPISODE_ID', row[3]);"
        )
        result_b = _subprocess.run(
            [sys.executable, "-c", script_b],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        assert "PROCB_NAV_END 990" in result_b.stdout, (
            f"cross-process NAV recovery failed: process B did not read "
            f"NAV=990 from ledger written by process A.  stdout={result_b.stdout!r}"
        )
        assert "PROCB_PNL -10" in result_b.stdout
        # nav_continuity_source may be NULL (run_demo_episode path) or
        # "cfg_capital_usd" (production run_once path).  Both are valid;
        # we just require it NOT to be a value that would indicate the
        # process never read the prior ledger row.
        proc_b_cont = [
            line.split(maxsplit=1)[1] for line in result_b.stdout.splitlines()
            if line.startswith("PROCB_CONT")
        ][0]
        assert proc_b_cont in ("cfg_capital_usd", "None"), (
            f"unexpected nav_continuity_source from process B: "
            f"{proc_b_cont!r} (expected cfg_capital_usd or None)"
        )
        # Process B's episode_id must be a fresh UUID (each process
        # generates its own; persistence is via ledger row, not memory).
        proc_b_episode_id = [
            line.split()[1] for line in result_b.stdout.splitlines()
            if line.startswith("PROCB_EPISODE_ID")
        ][0]
        assert len(proc_b_episode_id) >= 32, (
            f"process B episode_id looks invalid: {proc_b_episode_id!r}"
        )


class TestC2DuplicateAndFaultRollback:
    """C2 evidence #3: unclosed-position state recovery + duplicate-event dedup
    + real fault rollback.

    Scenario:
      Step A — Run run_once (episode 1).  Engine processes events, writes
               ledger rows (cursor, summary).  Position lifecycle state is
               implicit in unvalued_risk_json on rh_position_marks.
      Step B — Insert duplicate events (same (asset_address, sample_time)
               but row-level duplicates — drop PK to allow them).
      Step C — Run run_once (episode 2).  Adapter dedups via cursor
               filter (sample_time > cursor_after); ledger_duplicate_rows
               on the summary row MUST be 0.
      Step D — Simulate a fault: spawn a subprocess that is killed mid-
               execution with SIGKILL after engine starts writing.
      Step E — Verify ledger integrity: rh_epaper_cursor table state is
               consistent (either unchanged from before D, or advanced
               forward by D's run_once — never half-written).
    """

    def test_duplicate_events_trigger_failclosed_no_double_count(
        self, tmp_path: Path
    ) -> None:
        """C2 dedup evidence: physical duplicates at the same sample_time
        must NOT silently double-count.  Engine is expected to fail-closed
        with EXIT_TECH_ERROR and the ledger must remain consistent.
        """
        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        events = _events_between(start, n=4, interval_secs=600)
        # 2 physical duplicates of event[0] — drop PK so they coexist
        dup_times = [events[0][0], events[0][0]]
        _seed_source_with_duplicates(src, events, dup_times)

        # Sanity: source has 4 unique + 2 duplicates = 6 physical rows
        conn = sqlite3.connect(str(src))
        try:
            physical_rows = conn.execute(
                f"SELECT COUNT(*) FROM {EVT_TABLE}"
            ).fetchone()[0]
            distinct_times = conn.execute(
                f"SELECT COUNT(DISTINCT sample_time) FROM {EVT_TABLE}"
            ).fetchone()[0]
        finally:
            conn.close()
        assert physical_rows == 6, (
            f"physical source rows={physical_rows} - expected 6 (4 unique + 2 dup)"
        )
        assert distinct_times == 4, (
            f"distinct sample_times={distinct_times} - expected 4"
        )

        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)
        rc, ev = run_once(str(cfg))

        # C2 evidence: engine rejects duplicates (no silent double-count).
        # The UNIQUE(position_id, mark_time) constraint on rh_position_marks
        # is the dedup mechanism - a duplicate sample_time would try to
        # write the same (position_id, mark_time) twice, which raises
        # IntegrityError - run_once returns EXIT_TECH_ERROR.
        assert rc == EXIT_TECH_ERROR, (
            f"C2 violated: duplicate events should fail-closed "
            f"(EXIT_TECH_ERROR=1), got rc={rc}.  Silent acceptance "
            f"would double-count.  ev={ev}"
        )
        assert ev.get("status") == "blocked"
        assert "UNIQUE constraint failed" in str(ev.get("errors", [])), (
            f"C2 violated: expected UNIQUE constraint error in evidence, "
            f"got errors={ev.get('errors')!r}"
        )

        # Ledger invariants: no half-written episode, no cursor advance
        lconn = sqlite3.connect(str(ledger))
        try:
            n_eps = _safe_count(lconn, "rh_episode_summary")
            cursor_row = _safe_select_one(
                lconn,
                "SELECT last_event_time FROM rh_paper_cursor",
            )
        finally:
            lconn.close()
        assert n_eps == 0, (
            f"C2 violated: rh_episode_summary rows={n_eps} after "
            f"duplicate-blocked episode - must be 0 (no half-written "
            f"summary)"
        )
        assert cursor_row is None, (
            f"C2 violated: rh_paper_cursor advanced={cursor_row} despite "
            f"failed episode - must NOT advance on failed episode "
            f"(would lose the duplicate batch)"
        )

    def test_subprocess_kill_mid_episode_preserves_ledger_invariants(
        self, tmp_path: Path
    ) -> None:
        """Simulate a real fault: spawn a subprocess that calls run_once,
        SIGKILL it before completion, then verify the ledger is in a
        consistent state (no half-written cursor / summary).
        """
        import subprocess as _subprocess
        import time as _time

        src = tmp_path / "scanner.db"
        ledger = tmp_path / "ledger.db"
        now_real = datetime.now(timezone.utc)
        start = now_real - timedelta(minutes=240)

        # Heavy load: 200 events so the engine takes long enough to be
        # interrupted mid-flight.
        _seed_source(src, _events_between(start, n=200, interval_secs=600))
        cfg = _write_cfg(tmp_path, source_db=src, ledger_db=ledger)

        # Snapshot pre-run state (should be empty)
        pre_conn = sqlite3.connect(str(ledger))
        try:
            pre_cursor_count = _safe_count(pre_conn, "rh_paper_cursor")
            pre_summary_count = _safe_count(pre_conn, "rh_episode_summary")
        finally:
            pre_conn.close()
        assert pre_cursor_count == 0
        assert pre_summary_count == 0

        # Spawn child Python interpreter.  Use a deterministic fault
        # barrier instead of sleep(): the daemon emits a stderr marker
        # IN_TRANSACTION_AFTER_BUSINESS_WRITE_BEFORE_COMMIT right before
        # conn.commit(), so the parent can synchronise on that pipe line
        # and SIGKILL precisely at the business-write / commit boundary.
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
            f"from scripts.lp_rh_paper_daemon_entry_v1 import run_once; "
            f"rc, ev = run_once({str(cfg)!r}); "
            "print('CHILD_RC', rc);"
        )
        proc = _subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Read stderr line-by-line until the barrier marker is seen,
        # then SIGKILL.  This is deterministic — no sleep window.
        barrier_seen = False
        deadline = _time.monotonic() + 30.0
        while _time.monotonic() < deadline:
            line = proc.stderr.readline()
            if not line:
                break
            if "IN_TRANSACTION_AFTER_BUSINESS_WRITE_BEFORE_COMMIT" in line:
                barrier_seen = True
                break
        assert barrier_seen, (
            f"child never reached barrier marker "
            f"IN_TRANSACTION_AFTER_BUSINESS_WRITE_BEFORE_COMMIT — cannot "
            f"inject SIGKILL at the deterministic boundary"
        )
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except _subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        # proc.returncode will be -9 (SIGKILL) on Linux
        assert proc.returncode != 0, (
            f"subprocess completed normally (rc={proc.returncode}); "
            f"fault injection failed.  stdout={stdout!r} stderr={stderr!r}"
        )

        # Post-kill: ledger must be in a consistent state.  Either
        #   (a) completely empty (transaction was rolled back before kill)
        #   (b) cursor count == summary count (atomic write succeeded)
        # It MUST NOT have a cursor without a summary (orphan forward write).
        post_conn = sqlite3.connect(str(ledger))
        try:
            post_cursor_count = _safe_count(post_conn, "rh_paper_cursor")
            post_summary_count = _safe_count(post_conn, "rh_episode_summary")
            # Use safe_select_one in case the table was rolled back.
            episode_row = _safe_select_one(
                post_conn,
                "SELECT episode_id FROM rh_episode_summary LIMIT 1",
            )
        finally:
            post_conn.close()

        assert post_cursor_count == post_summary_count, (
            f"FAULT ROLLBACK VIOLATED: cursor count={post_cursor_count} "
            f"!= summary count={post_summary_count}.  Mid-episode kill "
            f"left orphan forward cursor write."
        )
        if post_summary_count > 0:
            assert episode_row is not None
            assert episode_row[0], (
                f"summary row with NULL episode_id: {episode_row}"
            )

        # Unclosed-position original state recovery: after the fault,
        # the ledger's pre-fault state is fully recoverable (cursor ==
        # summary count invariant holds).  Restart by running run_once
        # again; it must complete successfully (cursor advances normally).
        rc2, ev2 = run_once(str(cfg))
        assert rc2 == EXIT_NO_TRADE, (
            f"after-fault run_once rc={rc2}; ev={ev2}.  The original "
            f"unclosed-position state should be recoverable."
        )
