from __future__ import annotations

import contextlib
import sqlite3
from decimal import Decimal
import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    stage_b_status,
    audit_weekends_covered,
    STAGE_B_MIN_DAYS,
    STAGE_B_MIN_WEEKENDS,
)


def test_stage_b_fails_without_economic_gates():
    """F05: stage_b_status must reject evaluation without economic gates and version locks."""
    res = stage_b_status(
        days_covered=14,
        weekends_covered=1,
        unexplained_ledger_diffs=0,
        invariant_violations=0,
        missed_risk_events=0,
    )
    assert res["passed"] is False
    assert "PROFILE_NOT_LOCKED" in res["blockers"]
    assert "CODE_VERSION_NOT_LOCKED" in res["blockers"]
    assert "POLICY_VERSION_NOT_LOCKED" in res["blockers"]
    assert "CAPITAL_POLICY_VERSION_NOT_LOCKED" in res["blockers"]
    assert "ECONOMIC_EVIDENCE_MISSING" in res["blockers"]
    assert "OOS_EPISODE_RATIO_UNAVAILABLE" in res["blockers"]
    assert "EXIT_STRESS_NOT_PASSED" in res["blockers"]
    assert "NETCOVER_NOT_PASSED" in res["blockers"]


def test_stage_b_passes_with_all_conjunct_gates_met():
    """F05: stage_b_status passes when all engineering, policy, and economic gates are met."""
    res = stage_b_status(
        days_covered=STAGE_B_MIN_DAYS,
        weekends_covered=STAGE_B_MIN_WEEKENDS,
        unexplained_ledger_diffs=0,
        invariant_violations=0,
        missed_risk_events=0,
        profile_locked=True,
        code_version_locked=True,
        policy_version_locked=True,
        capital_policy_version_locked=True,
        full_cost_profitable_episodes=10,
        min_profitable_episodes=10,
        oos_episode_ratio=Decimal("0.30"),
        min_oos_ratio=Decimal("0.30"),
        exit_stress_passed=True,
        netcover_passed=True,
    )
    assert res["passed"] is True
    assert res["blockers"] == []


def test_audit_weekends_covered_single_sample_fails():
    """F05: A single sample on a weekend day must not count as a completed weekend."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT)")
    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time) VALUES ('0xpool', '2026-09-12T12:00:00Z')"
    )
    res = audit_weekends_covered(conn, asset_address="0xpool", interval_secs=15)
    assert res["weekends_covered"] == 0
    assert len(res["days"]) == 1
    assert res["days"][0]["complete"] is False
    conn.close()


def test_stage_b_reverse_validation_defect_simulation():
    """Reverse validation: simulating old defect where only time duration was checked."""
    # Under defect: time alone passes
    def defective_stage_b(days_covered, weekends_covered, unexplained_ledger_diffs, invariant_violations, missed_risk_events):
        blockers = []
        if days_covered < 14:
            blockers.append("DAYS")
        if weekends_covered < 1:
            blockers.append("WEEKENDS")
        if unexplained_ledger_diffs:
            blockers.append("DIFFS")
        if invariant_violations:
            blockers.append("INVARIANTS")
        if missed_risk_events:
            blockers.append("MISSED")
        return {"passed": len(blockers) == 0, "blockers": blockers}

    # Defect yields true with 0 economics
    defect_res = defective_stage_b(14, 1, 0, 0, 0)
    assert defect_res["passed"] is True

    # Fixed code rejects it
    fixed_res = stage_b_status(
        days_covered=14,
        weekends_covered=1,
        unexplained_ledger_diffs=0,
        invariant_violations=0,
        missed_risk_events=0,
    )
    assert fixed_res["passed"] is False
    assert len(fixed_res["blockers"]) > 0
