#!/usr/bin/env python3
"""Tests for the RH graduation readiness dashboard (offline/read-only)."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_readiness_v1_readonly import (  # noqa: E402
    STAGE_A_MIN_HOURS,
    STAGE_B_MIN_DAYS,
    graduation_verdict,
    live_gate_status,
    render_dashboard,
    stage_a_status,
    stage_b_status,
)


def clean_live_gate():
    return live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                            signatures=0, broadcasts=0, keys_created=0)


def passing_stage_a():
    return stage_a_status(first_sample="2026-09-08T00:00:00Z",
                          last_sample="2026-09-11T00:00:00Z",
                          expected_interval_secs=15,
                          actual_samples=72 * 3600 // 15)


def passing_stage_b():
    return stage_b_status(days_covered=STAGE_B_MIN_DAYS, weekends_covered=1,
                          unexplained_ledger_diffs=0, invariant_violations=0,
                          missed_risk_events=0)


# --- Stage A ---

def test_stage_a_denominator_is_planned_window():
    # 10h observed, 15s interval -> 2400 expected; 1200 actual -> 0.5 coverage.
    a = stage_a_status(first_sample="2026-09-08T00:00:00Z",
                       last_sample="2026-09-08T10:00:00Z",
                       expected_interval_secs=15, actual_samples=1200)
    assert a["expected_samples"] == 2400
    assert a["coverage_ratio"] == 0.5
    assert a["passed"] is False
    # The denominator must be the planned window, NOT the actual sample count.
    assert a["expected_samples"] != a["actual_samples"]
    assert a["coverage_ratio"] != 1.0


def test_stage_a_72h_but_low_coverage_fails():
    expected = 72 * 3600 // 15
    a = stage_a_status(first_sample="2026-09-08T00:00:00Z",
                       last_sample="2026-09-11T00:00:00Z",
                       expected_interval_secs=15,
                       actual_samples=int(expected * 0.98))
    assert a["hours_covered"] >= STAGE_A_MIN_HOURS
    assert a["passed"] is False
    assert "COVERAGE_INSUFFICIENT" in a["blockers"]


def test_stage_a_72h_full_coverage_passes():
    a = passing_stage_a()
    assert a["passed"] is True
    assert a["blockers"] == []


def test_stage_a_real_number_regression_6h():
    a = stage_a_status(first_sample="2026-09-08T00:00:00Z",
                       last_sample="2026-09-08T06:00:00Z",
                       expected_interval_secs=15, actual_samples=1440)
    assert a["passed"] is False
    assert a["hours_required"] == 72
    assert "HOURS_COVERED_INSUFFICIENT" in a["blockers"]


def test_stage_a_missing_window_unavailable():
    a = stage_a_status(first_sample=None, last_sample=None,
                       expected_interval_secs=15, actual_samples=0)
    assert a["passed"] is False
    assert "OBSERVATION_WINDOW_UNAVAILABLE" in a["blockers"]


# --- Stage B ---

def test_stage_b_full_days_but_invariant_violation_fails():
    b = stage_b_status(days_covered=STAGE_B_MIN_DAYS, weekends_covered=2,
                       unexplained_ledger_diffs=0, invariant_violations=1,
                       missed_risk_events=0)
    assert b["passed"] is False
    assert "INVARIANT_VIOLATIONS" in b["blockers"]


def test_stage_b_full_days_clean_passes():
    b = passing_stage_b()
    assert b["passed"] is True
    assert b["blockers"] == []


def test_stage_b_insufficient_days_fails():
    b = stage_b_status(days_covered=STAGE_B_MIN_DAYS - 1, weekends_covered=1,
                       unexplained_ledger_diffs=0, invariant_violations=0,
                       missed_risk_events=0)
    assert b["passed"] is False
    assert "DAYS_COVERED_INSUFFICIENT" in b["blockers"]


def test_stage_b_unexplained_diffs_fail():
    b = stage_b_status(days_covered=STAGE_B_MIN_DAYS, weekends_covered=1,
                       unexplained_ledger_diffs=1, invariant_violations=0,
                       missed_risk_events=0)
    assert b["passed"] is False
    assert "UNEXPLAINED_LEDGER_DIFFS" in b["blockers"]


def test_stage_b_missed_risk_events_fail():
    b = stage_b_status(days_covered=STAGE_B_MIN_DAYS, weekends_covered=1,
                       unexplained_ledger_diffs=0, invariant_violations=0,
                       missed_risk_events=1)
    assert b["passed"] is False
    assert "MISSED_RISK_EVENTS" in b["blockers"]

# --- LIVE gate ---

def test_live_gate_single_provider():
    lg = live_gate_status(usable_provider_count=1, capital_policy_approved=True,
                          signatures=0, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE" in lg["blockers"]


def test_live_gate_signatures():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=1, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_DETECTED" in lg["blockers"]


def test_live_gate_broadcasts():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=0, broadcasts=1, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_DETECTED" in lg["blockers"]


def test_live_gate_keys_created():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=0, broadcasts=0, keys_created=1)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_DETECTED" in lg["blockers"]


def test_live_gate_capital_policy_conflict():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=False,
                          signatures=0, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "CAPITAL_POLICY_CONFLICT" in lg["blockers"]


def test_live_gate_all_clean():
    lg = clean_live_gate()
    assert lg["live_allowed"] is True
    assert lg["blockers"] == []


# --- verdict ---

@pytest.mark.parametrize("blocker", [
    "SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE",
    "CAPITAL_POLICY_CONFLICT",
    "UNAUTHORIZED_ACTION_DETECTED",
])
def test_verdict_live_blocker_not_pass(blocker):
    live_gate = {"blockers": [blocker], "live_allowed": False}
    v = graduation_verdict(passing_stage_a(), passing_stage_b(), live_gate)
    assert v["verdict"] != "PASS"
    assert "LIVE_EXECUTION" in v["explicitly_not_authorized"]


def test_verdict_all_pass():
    v = graduation_verdict(passing_stage_a(), passing_stage_b(), clean_live_gate())
    assert v["verdict"] == "PASS"
    assert v["explicitly_not_authorized"] == []


def test_verdict_warn_when_stages_incomplete():
    incomplete_a = stage_a_status(first_sample="2026-09-08T00:00:00Z",
                                  last_sample="2026-09-08T06:00:00Z",
                                  expected_interval_secs=15, actual_samples=1440)
    v = graduation_verdict(incomplete_a, passing_stage_b(), clean_live_gate())
    assert v["verdict"] == "WARN"


# --- render_dashboard ---

def test_render_dashboard_none_field_not_measured():
    state = {"terminal_gate": {"legacy_required_conjunction": None}}
    out = render_dashboard(state)
    assert "legacy_required_conjunction: NOT_MEASURED" in out
    assert "legacy_required_conjunction: 0" not in out


def test_render_dashboard_contains_sections():
    out = render_dashboard({"stage_a": passing_stage_a(),
                            "stage_b": passing_stage_b(),
                            "live_gate": clean_live_gate()})
    for header in ("首页六问", "四阶段进度", "终闸十项当前值", "证据新鲜度", "预算用量"):
        assert header in out


def test_render_dashboard_empty_state_no_crash():
    out = render_dashboard({})
    assert "NOT_MEASURED" in out
