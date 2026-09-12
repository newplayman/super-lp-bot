"""R2-04 + R3 / Package F: stage_b wiring AND multi-day partial first/last
day counts use the actual span, not a 6h compromise.

Re-audit 04e8a45 / 6fda329 confirmed:
  * 6fda329 still carried ``expected = max(span_secs/interval, 21600/interval)``
    on first/last partial days, so 12h of pre-noon samples declared a
    full weekend day.
  * The re-audit example: 2026-09-11 18:00 UTC to 2026-09-12 05:59:45 UTC,
    2880 samples at 15s, two calendar days with the first day being
    partial (6h).
"""

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

    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
    rows = [("0xasset", (start + timedelta(seconds=15 * i)).isoformat().replace("+00:00", "Z"))
            for i in range(648)]
    conn.executemany("INSERT INTO rh_market_states VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address="0xasset", interval_secs=15)
    assert res["weekends_covered"] == 0
    assert res["days"][0]["complete"] is False
    assert res["days"][0]["expected"] == 5760.0  # 86400 / 15

    conn.close()


def test_multi_day_partial_first_day_uses_actual_span(tmp_path):
    """R3 / Package F: a multi-day window with partial first/last days
    must score each day by its actual span, not by a 6h floor.

    The re-audit example: 2026-09-11 18:00 UTC to 2026-09-12 05:59:45 UTC,
    15s sampling.  First day (Sep 11) is partial — 6 hours (21600s) of
    samples, which is far less than the 86,400 / 15 = 5,760 expected for
    a full day.  The 6fda329 code would have floored ``expected`` to
    21,600 / 15 = 1,440; with 1,440 samples collected, the day would
    count as complete.  R3 / Package F drops that compromise.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT)")

    # First day: 17:00 -> 23:59:45 (Wed) = ~25,185s (~7h).  This
    # span is strictly greater than 21,600s (6h), so a no-floor formula
    # yields expected > 1,440 (the 6fda329 floor).
    # Second day: 00:00 -> 05:59:45 (Thu) = ~21,585s, partial.
    # Both days are weekdays so weekends_covered stays 0.
    start = datetime(2026, 9, 9, 17, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, 5, 59, 45, tzinfo=timezone.utc)
    rows = []
    t = start
    while t <= end:
        rows.append(("0xasset", t.isoformat().replace("+00:00", "Z")))
        t = t + timedelta(seconds=15)
    conn.executemany("INSERT INTO rh_market_states VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address="0xasset", interval_secs=15)
    days = res["days"]
    assert len(days) == 2
    # R3 fix: each partial day uses its ACTUAL span_secs / interval, NOT
    # the 21,600s / 15 = 1,440 compromise.  Sep 11 captures 21,945s of
    # data, so expected ≈ 21,945 / 15 ≈ 1,463.
    sep9 = next(d for d in days if d["date"] == "2026-09-09")
    sep10 = next(d for d in days if d["date"] == "2026-09-10")
    # The 6fda329 floor would have rounded expected DOWN to 1,440.  R3
    # expects it to reflect actual span — strictly greater than 1,440.
    assert sep9["expected"] > 1440.0, (
        f"Sep 9 expected {sep9['expected']} must be > 1,440; the 6fda329 "
        "compromise ``max(span/interval, 21600/interval)`` would have floored "
        "this to 1,440 even though the actual span is ~25,200s"
    )
    # The expected for the second (last) day is also span-driven, NOT
    # floored to 1,440.  Sep 10 captures ~21,585s = 1,439 samples.
    assert abs(sep10["expected"] - 1439.0) < 1.0, (
        f"Sep 10 expected {sep10['expected']} must reflect actual "
        f"span ~21,585s (≈ 1,439 samples), not a 1,440 floor"
    )
    # No weekend coverage — both days are weekday.
    assert res["weekends_covered"] == 0
    conn.close()


def test_isolated_single_day_strict_full_denominator():
    """R3 / Package F control: an isolated single day with only 648 samples
    in 2.7h still uses 86,400 / interval and stays incomplete (the 6fda329
    code happened to handle this case correctly; keep the regression
    check)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT)")

    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
    rows = [("0xasset", (start + timedelta(seconds=15 * i)).isoformat().replace("+00:00", "Z"))
            for i in range(648)]
    conn.executemany("INSERT INTO rh_market_states VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address="0xasset", interval_secs=15)
    assert res["weekends_covered"] == 0
    assert res["days"][0]["complete"] is False
    assert res["days"][0]["expected"] == 5760.0
    conn.close()
