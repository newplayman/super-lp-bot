from __future__ import annotations

import sqlite3

from scripts.lp_reward_observation_progress_v1_readonly import build_progress


CUTOFF = "2026-08-10T12:00:00+00:00"


def _db(path, observations, incidents=()):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reward_observations(
          as_of TEXT,pool TEXT,chain TEXT,apy_reward REAL,apy_base REAL,tvl_usd REAL,source TEXT
        );
        CREATE TABLE pool_snapshots(as_of TEXT,pool TEXT,symbol TEXT);
        CREATE TABLE rpc_severe_incidents(
          source TEXT,opened_at TEXT,resolved_at TEXT,opening_health TEXT,resolution_health TEXT
        );
        CREATE TABLE shadow_gate_observations(rpc_health TEXT);
        """
    )
    connection.executemany(
        "INSERT INTO reward_observations VALUES (?,?,?,?,?,?,?)",
        [(stamp, pool, "Base", reward, 1.0, 1_000_000.0, "test") for stamp, pool, reward in observations],
    )
    connection.execute("INSERT INTO pool_snapshots VALUES (?,?,?)", (CUTOFF, "pool", "AERO-USDC"))
    connection.executemany("INSERT INTO rpc_severe_incidents VALUES (?,?,?,?,?)", incidents)
    connection.execute("INSERT INTO shadow_gate_observations VALUES ('NORMAL')")
    connection.commit(); connection.close()


def test_contiguous_duration_and_remaining_reuse_canonical_policy(tmp_path):
    db = tmp_path / "scanner.db"
    _db(db, [
        ("2026-08-10T11:00:00+00:00", "pool", 2.0),
        ("2026-08-10T11:30:00+00:00", "pool", 2.0),
        ("2026-08-10T11:59:00+00:00", "pool", 2.0),
    ])
    report = build_progress(db, as_of=CUTOFF)
    pool = report["pools"][0]
    assert pool["symbol"] == "AERO-USDC"
    assert pool["contiguous_positive_duration_hours"] == 59 / 60
    assert pool["hours_remaining_to_trusted_24h"] == 24 - 59 / 60
    assert pool["gap_break_count"] == 0


def test_gap_break_is_counted_and_resets_contiguous_suffix(tmp_path):
    db = tmp_path / "scanner.db"
    _db(db, [
        ("2026-08-10T09:00:00+00:00", "pool", 2.0),
        ("2026-08-10T11:30:00+00:00", "pool", 2.0),
        ("2026-08-10T11:59:00+00:00", "pool", 2.0),
    ])
    pool = build_progress(db, as_of=CUTOFF)["pools"][0]
    assert pool["gap_break_count"] == 1
    assert pool["max_gap_hours"] == 2.5
    assert pool["contiguous_positive_duration_hours"] == 29 / 60


def test_stale_and_rpc_incidents_are_fail_visible(tmp_path):
    db = tmp_path / "scanner.db"
    _db(
        db,
        [("2026-08-10T10:00:00+00:00", "pool", 2.0)],
        incidents=[("scanner", "2026-08-10T10:00:00+00:00", None, "EXIT_ONLY", None)],
    )
    report = build_progress(db, as_of=CUTOFF)
    assert report["pools"][0]["canonical_status"] == "STALE_OBSERVATIONS"
    assert report["pools"][0]["hours_remaining_to_trusted_24h"] == 24
    assert report["rpc_health_events"]["severe_unresolved"] == 1
    assert report["rpc_health_events"]["severe_by_opening_health"] == {"EXIT_ONLY": 1}


def test_database_is_not_modified(tmp_path):
    db = tmp_path / "scanner.db"
    _db(db, [("2026-08-10T11:59:00+00:00", "pool", 2.0)])
    before = db.read_bytes()
    report = build_progress(db, as_of=CUTOFF)
    assert db.read_bytes() == before
    assert report["safety"]["sqlite_mode"] == "ro"
    assert report["safety"]["scanner_process_control"] == 0
