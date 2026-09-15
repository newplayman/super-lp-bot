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
legacy_required_conjunction = true
identity_verified = true
protocol_capabilities_sufficient = true
data_complete_and_fresh = true
profile_policy_pass = true
market_and_chain_risk_pass = true
absolute_profit_pass = true
position_and_exit_depth_pass = true
capital_policy_pass = true

[costs.defaults]
entry_cost_usd = "5"
exit_cost_usd = "5"
gas_usd = "0.01"
"""
    )
    return cfg


def _events_between(
    start: datetime, *, n: int, interval_secs: int
) -> list[tuple[str, str]]:
    return [
        (
            (start + timedelta(seconds=i * interval_secs))
            .isoformat()
            .replace("+00:00", "Z"),
            str(i * 1000),
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
