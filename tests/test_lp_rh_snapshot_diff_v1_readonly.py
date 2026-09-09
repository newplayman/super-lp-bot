"""Tests for lp_rh_snapshot_diff_v1_readonly (RH-08d frozen-snapshot gate diff).

Temp-dir SQLite only.  No network, no writes to reports/.
"""
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/opt/lpbot/lp-bot-v3-origin-check")

from scripts.lp_rh_snapshot_diff_v1_readonly import (
    diff_replays, freeze_snapshot, load_baseline, main, replay_gates,
    save_baseline,
)
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store

POOL = "0xtestpool"
POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 24.0


def _counts(db) -> dict:
    """Per-table row counts of a db file, opened read-only."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables}
    finally:
        conn.close()


def _seed_store(tmp_path, n_samples, name="src.db"):
    """Create a store with n_samples market-state rows for POOL."""
    db = tmp_path / name
    conn = open_store(db)
    migrate(conn)
    for i in range(n_samples):
        insert_row(conn, "rh_market_states", {
            "asset_address": POOL,
            "sample_time": f"2026-01-01T00:{i:02d}:00Z",
            "chain_id": 4663,
            "session": "RTH",
            "health_flags_json": "[]",
            "reference_mid": "100.0",
            "reference_age_secs": 10,
            "source_payload_hash": f"0xhash{i}",
            "oracle_paused": 0,
        })
    conn.commit()
    conn.close()
    return db


def _step(i, status="COMPUTED_FAIL", blocker="netcover_pass", **bits):
    return {
        "step_index": i,
        "sample_time": f"2026-01-01T00:{i:02d}:00Z",
        "primary_status": status,
        "dominant_blocker": blocker,
        "terminal_bits": {"netcover_pass": False, "identity_verified": True,
                          **bits},
    }


def _replay(snapshot, n=5):
    return replay_gates(snapshot, pool=POOL, samples=n,
                        position_usd=POSITION_USD, capital_usd=CAPITAL_USD,
                        horizon_hours=HORIZON_HOURS, pool_meta=None)


# 1. freeze_snapshot leaves the source untouched (mtime + row counts).
def test_freeze_snapshot_source_unmodified(tmp_path):
    src = _seed_store(tmp_path, 4)
    mtime_before = src.stat().st_mtime
    counts_before = _counts(src)
    freeze_snapshot(src, tmp_path / "snap.db")
    assert src.stat().st_mtime == mtime_before
    assert _counts(src) == counts_before


# 2. snapshot row counts match the source per-table.
def test_freeze_snapshot_row_counts_match(tmp_path):
    src = _seed_store(tmp_path, 4)
    meta = freeze_snapshot(src, tmp_path / "snap.db")
    assert meta["rows"] == _counts(src)
    assert meta["rows"]["rh_market_states"] == 4


# 3. same data replayed twice -> diff_replays identical is True.
def test_replay_twice_identical(tmp_path):
    src = _seed_store(tmp_path, 5)
    snap = tmp_path / "snap.db"
    freeze_snapshot(src, snap)
    a = _replay(snap)
    b = _replay(snap)
    assert a == b
    diff = diff_replays(a, b)
    assert diff["identical"] is True
    assert diff["changed_steps"] == []


# 4. change one step's primary_status -> changed_count==1, correct from/to.
def test_diff_detects_primary_status_change():
    baseline = [_step(0), _step(1), _step(2)]
    current = [_step(0), _step(1, status="COMPUTED_PASS"), _step(2)]
    diff = diff_replays(baseline, current)
    assert diff["changed_count"] == 1
    assert diff["changed_steps"][0]["field"] == "primary_status"
    assert diff["changed_steps"][0]["from"] == "COMPUTED_FAIL"
    assert diff["changed_steps"][0]["to"] == "COMPUTED_PASS"
    assert diff["changed_steps"][0]["step_index"] == 1


# 5. change dominant_blocker -> detected.
def test_diff_detects_dominant_blocker_change():
    baseline = [_step(0), _step(1)]
    current = [_step(0), _step(1, blocker="identity_verified")]
    diff = diff_replays(baseline, current)
    assert diff["changed_count"] == 1
    assert diff["changed_steps"][0]["field"] == "dominant_blocker"


# 6. two fields change in one step -> changed_count==2 (per-field, not step).
def test_diff_counts_per_field_not_per_step():
    baseline = [_step(0), _step(1)]
    current = [_step(0), _step(1, status="COMPUTED_PASS",
                     blocker="identity_verified")]
    diff = diff_replays(baseline, current)
    assert diff["changed_count"] == 2
    fields = {c["field"] for c in diff["changed_steps"]}
    assert fields == {"primary_status", "dominant_blocker"}


# 7. step-count mismatch -> STEP_COUNT_MISMATCH, no exception, no truncation.
def test_diff_step_count_mismatch():
    baseline = [_step(0), _step(1), _step(2)]
    current = [_step(0), _step(1)]
    diff = diff_replays(baseline, current)
    assert diff["error"] == "STEP_COUNT_MISMATCH"
    assert diff["baseline_steps"] == 3
    assert diff["current_steps"] == 2
    assert "changed_steps" not in diff


# 8. status_transitions: 3 steps COMPUTED_FAIL -> INPUTS_UNAVAILABLE.
def test_diff_status_transitions():
    baseline = [_step(0), _step(1), _step(2)]
    current = [_step(0, status="INPUTS_UNAVAILABLE"),
               _step(1, status="INPUTS_UNAVAILABLE"),
               _step(2, status="INPUTS_UNAVAILABLE")]
    diff = diff_replays(baseline, current)
    assert diff["status_transitions"] == {
        "COMPUTED_FAIL->INPUTS_UNAVAILABLE": 3}


# 9. save/load baseline round-trip; baseline includes git_head + frozen_at.
def test_baseline_round_trip(tmp_path):
    replay = [_step(0), _step(1)]
    path = tmp_path / "baseline.json"
    save_baseline(replay, path, git_head="abc123",
                  frozen_at="2026-01-01T00:00:00Z")
    loaded = load_baseline(path)
    assert loaded["steps"] == replay
    assert loaded["git_head"] == "abc123"
    assert loaded["frozen_at"] == "2026-01-01T00:00:00Z"


# 10. no baseline -> main returns 0 and outputs status NO_BASELINE.
def test_main_no_baseline(tmp_path, capsys):
    src = _seed_store(tmp_path, 3)
    snap = tmp_path / "snap.db"
    freeze_snapshot(src, snap)
    baseline = tmp_path / "nope.json"  # does not exist
    rc = main(["--snapshot", str(snap), "--baseline", str(baseline)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "NO_BASELINE"
    assert "hint" in out


# 11. replay_gates does not write the snapshot (mtime unchanged).
def test_replay_gates_does_not_write_snapshot(tmp_path):
    src = _seed_store(tmp_path, 5)
    snap = tmp_path / "snap.db"
    freeze_snapshot(src, snap)
    mtime_before = snap.stat().st_mtime
    _replay(snap)
    assert snap.stat().st_mtime == mtime_before


# 12. empty snapshot -> replay_gates returns [], diff_replays([],[]) identical.
def test_empty_snapshot(tmp_path):
    db = tmp_path / "empty.db"
    conn = open_store(db)
    migrate(conn)
    conn.close()
    snap = tmp_path / "snap.db"
    freeze_snapshot(db, snap)
    assert _replay(snap) == []
    assert diff_replays([], [])["identical"] is True


# 13. freeze_snapshot returns rows/sha256/frozen_at with a valid sha256.
def test_freeze_snapshot_metadata(tmp_path):
    src = _seed_store(tmp_path, 2)
    meta = freeze_snapshot(src, tmp_path / "snap.db")
    assert set(meta) == {"rows", "sha256", "frozen_at"}
    assert len(meta["sha256"]) == 64
    int(meta["sha256"], 16)  # valid hex
    assert "T" in meta["frozen_at"] and meta["frozen_at"].endswith("Z")


# 14. replay_gates returns the per-step fields.
def test_replay_gates_step_fields(tmp_path):
    src = _seed_store(tmp_path, 3)
    snap = tmp_path / "snap.db"
    freeze_snapshot(src, snap)
    steps = _replay(snap)
    assert len(steps) == 3
    for i, s in enumerate(steps):
        assert s["step_index"] == i
        assert set(s) == {"step_index", "sample_time", "primary_status",
                          "dominant_blocker", "terminal_bits"}
        assert isinstance(s["terminal_bits"], dict)
