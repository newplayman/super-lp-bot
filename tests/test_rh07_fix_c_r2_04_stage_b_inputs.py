from datetime import datetime, timedelta, timezone
import sqlite3
import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    _build_state,
    audit_weekends_covered,
    stage_b_status,
)


from scripts.lp_rh_store_v1_readonly import open_store, migrate


def test_build_state_forwards_eight_economic_inputs(tmp_path):
    """R2-04: Verify _build_state correctly forwards the 8 economic evidence parameters to stage_b_status."""
    db_file = tmp_path / "readiness.db"
    conn = open_store(db_file)
    migrate(conn)

    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time, chain_id, session, health_flags_json) VALUES (?, ?, ?, ?, ?)",
        ("0xasset", "2026-09-11T12:00:00Z", 4663, "REGULAR", "[]"),
    )
    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time, chain_id, session, health_flags_json) VALUES (?, ?, ?, ?, ?)",
        ("0xasset", "2026-09-11T12:00:15Z", 4663, "REGULAR", "[]"),
    )
    conn.commit()

    state = _build_state(
        conn,
        str(db_file),
        15.0,
        "0xasset",
        as_of="2026-09-11T12:00:00Z",
        profile_locked=True,
        code_version_locked=True,
        policy_version_locked=True,
        capital_policy_version_locked=True,
        full_cost_profitable_episodes=5,
        oos_episode_ratio=0.85,
        exit_stress_passed=True,
        netcover_passed=True,
    )

    stage_b = state["stage_b"]
    assert stage_b["profile_locked"] is True
    assert stage_b["code_version_locked"] is True
    assert stage_b["policy_version_locked"] is True
    assert stage_b["capital_policy_version_locked"] is True
    assert stage_b["full_cost_profitable_episodes"] == 5
    assert float(stage_b["oos_episode_ratio"]) == 0.85
    assert stage_b["exit_stress_passed"] is True
    assert stage_b["netcover_passed"] is True

    # When economic inputs are missing, stage_b reports blockers
    state_missing = _build_state(
        conn,
        str(db_file),
        15.0,
        "0xasset",
        as_of="2026-09-11T12:00:00Z",
    )
    b_missing = state_missing["stage_b"]
    assert "PROFILE_NOT_LOCKED" in b_missing["blockers"]
    assert "ECONOMIC_EVIDENCE_MISSING" in b_missing["blockers"]

    conn.close()


def test_audit_weekends_covered_uses_full_day_denominator():
    """R2-04: Verify isolated days use full 86,400s denominator and do not qualify with partial counts."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT)")

    # 648 samples across 2.7 hours on Saturday
    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
    rows = [("0xasset", (start + timedelta(seconds=15 * i)).isoformat().replace("+00:00", "Z"))
            for i in range(648)]
    conn.executemany("INSERT INTO rh_market_states VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address="0xasset", interval_secs=15)
    assert res["weekends_covered"] == 0
    assert res["days"][0]["complete"] is False
    assert res["days"][0]["expected"] == 5760.0  # 86400 / 15

    conn.close()
