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
from scripts.lp_rh_store_v1_readonly import (  # noqa: E402
    DEFAULT_DB_PATH,
    insert_row,
    migrate,
    open_store,
)

# The real shape returned by lp_rh_store.budget_status -- there is no
# "over_budget" key.  Fixtures that invent one test a contract the code
# does not have, which is how a store at 0.7% of budget came out blocked.
BUDGET_OK = {"bytes": 15077192, "soft_budget_bytes": 2147483648,
             "fraction": 0.007, "state": "OK"}
BUDGET_WARN = {"bytes": 1900000000, "soft_budget_bytes": 2147483648,
               "fraction": 0.88, "state": "WARN"}
BUDGET_OVER = {"bytes": 2147483649, "soft_budget_bytes": 2147483648,
               "fraction": 1.0, "state": "OVER"}


def clean_live_gate():
    return live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                            signatures=0, broadcasts=0, keys_created=0)


def passing_stage_a():
    return stage_a_status(first_sample="2026-09-08T00:00:00Z",
                          last_sample="2026-09-11T00:00:00Z",
                          expected_interval_secs=15,
                          actual_samples=72 * 3600 // 15,
                          synthetic_tests_passed=True,
                          key_field_health={"passed": True},
                          pool_attestation_status={"passed": True},
                          budget=BUDGET_OK,
                          invariant_violations=0,
                          unknown_state_positions=0)


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


# --- RH-02az: PRD §21.1 7 Criteria Unit Tests ---

def test_stage_a_synthetic_tests_missing_or_failed_blocks():
    # Evidence missing -> blocked
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=None, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_SYNTHETIC_TESTS_UNKNOWN" in a_none["blockers"]

    # Evidence False -> blocked
    a_false = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=False, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_false["passed"] is False
    assert "STAGE_A_SYNTHETIC_TESTS_UNKNOWN" in a_false["blockers"]


def test_stage_a_synthetic_tests_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_SYNTHETIC_TESTS_UNKNOWN" not in a["blockers"]
    assert a["passed"] is True


def test_stage_a_key_fields_incomplete_blocks():
    # Missing / None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health=None,
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_KEY_FIELDS_INCOMPLETE" in a_none["blockers"]

    # Incomplete (passed: False)
    a_fail = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": False, "reason": "fee_growth low"},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_fail["passed"] is False
    assert "STAGE_A_KEY_FIELDS_INCOMPLETE" in a_fail["blockers"]


def test_stage_a_key_fields_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_KEY_FIELDS_INCOMPLETE" not in a["blockers"]
    assert a["passed"] is True


def test_stage_a_pool_attestation_missing_blocks():
    # Missing attestation / None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status=None, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_POOL_NOT_ATTESTED" in a_none["blockers"]

    # Attestation failed
    a_fail = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": False, "missing": ["rh_contract_attestations"]},
        budget=BUDGET_OK, invariant_violations=0, unknown_state_positions=0,
    )
    assert a_fail["passed"] is False
    assert "STAGE_A_POOL_NOT_ATTESTED" in a_fail["blockers"]


def test_stage_a_pool_attestation_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_POOL_NOT_ATTESTED" not in a["blockers"]
    assert a["passed"] is True


def test_stage_a_budget_exceeded_blocks():
    # Budget None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=None,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_BUDGET_EXCEEDED" in a_none["blockers"]

    # Budget over_budget True
    a_over = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OVER,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_over["passed"] is False
    assert "STAGE_A_BUDGET_EXCEEDED" in a_over["blockers"]


def test_stage_a_budget_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_BUDGET_EXCEEDED" not in a["blockers"]
    assert a["passed"] is True


def test_stage_a_budget_warn_passes():
    """RH-02bd: Budget WARN (soft threshold reached, but still <= 100%) does NOT block."""
    a_warn = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_WARN,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_warn["passed"] is True
    assert "STAGE_A_BUDGET_EXCEEDED" not in a_warn["blockers"]


def test_stage_a_budget_over_blocks():
    """RH-02bd: Budget OVER (exceeding soft budget) strictly blocks."""
    a_over = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OVER,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_over["passed"] is False
    assert "STAGE_A_BUDGET_EXCEEDED" in a_over["blockers"]


def test_stage_a_invariant_violations_blocks():
    # None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=None, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_INVARIANT_VIOLATIONS" in a_none["blockers"]

    # > 0
    a_viol = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=2, unknown_state_positions=0,
    )
    assert a_viol["passed"] is False
    assert "STAGE_A_INVARIANT_VIOLATIONS" in a_viol["blockers"]


def test_stage_a_invariant_violations_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_INVARIANT_VIOLATIONS" not in a["blockers"]
    assert a["passed"] is True


def test_stage_a_unknown_state_positions_blocks():
    # None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=None,
    )
    assert a_none["passed"] is False
    assert "STAGE_A_UNKNOWN_STATE_POSITIONS" in a_none["blockers"]

    # > 0
    a_viol = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=3,
    )
    assert a_viol["passed"] is False
    assert "STAGE_A_UNKNOWN_STATE_POSITIONS" in a_viol["blockers"]


def test_stage_a_unknown_state_positions_clean_passes():
    a = passing_stage_a()
    assert "STAGE_A_UNKNOWN_STATE_POSITIONS" not in a["blockers"]
    assert a["passed"] is True


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


# --- RH-02am: unknown/invalid LIVE action counts ---

def test_live_gate_all_action_counts_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=None, broadcasts=None, keys_created=None)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_signatures_none_is_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=None, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_broadcasts_none_is_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=0, broadcasts=None, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_keys_created_none_is_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=0, broadcasts=0, keys_created=None)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_keys_created_bool_is_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=0, broadcasts=0, keys_created=False)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]
    assert "UNAUTHORIZED_ACTION_DETECTED" not in lg["blockers"]


@pytest.mark.parametrize("field_value", [True, "0", 0.0])
def test_live_gate_non_integer_action_count_is_unavailable(field_value):
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=field_value, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_negative_action_count_is_unavailable():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=-1, broadcasts=0, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]


def test_live_gate_unknown_and_detected_counts_report_both_blockers():
    lg = live_gate_status(usable_provider_count=2, capital_policy_approved=True,
                          signatures=None, broadcasts=1, keys_created=0)
    assert lg["live_allowed"] is False
    assert "UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE" in lg["blockers"]
    assert "UNAUTHORIZED_ACTION_DETECTED" in lg["blockers"]


# --- RH-02am: missing Stage B audit counts and LIVE verdict ---

@pytest.mark.parametrize("field_and_blocker", [
    ("unexplained_ledger_diffs", "UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE"),
    ("invariant_violations", "INVARIANT_VIOLATIONS_UNAVAILABLE"),
    ("missed_risk_events", "MISSED_RISK_EVENTS_UNAVAILABLE"),
])
def test_stage_b_missing_audit_count_blocks(field_and_blocker):
    field, expected_blocker = field_and_blocker
    values = {
        "days_covered": STAGE_B_MIN_DAYS,
        "weekends_covered": 1,
        "unexplained_ledger_diffs": 0,
        "invariant_violations": 0,
        "missed_risk_events": 0,
    }
    values[field] = None
    b = stage_b_status(**values)
    assert b["passed"] is False
    assert expected_blocker in b["blockers"]


@pytest.mark.parametrize("live_gate", [None, {"blockers": [], "live_allowed": None}])
def test_verdict_missing_live_gate_is_not_pass(live_gate):
    v = graduation_verdict(passing_stage_a(), passing_stage_b(), live_gate)
    assert v["verdict"] != "PASS"
    assert "LIVE_EXECUTION" in v["explicitly_not_authorized"]


def test_verdict_non_boolean_live_allowed_is_not_authorized():
    v = graduation_verdict(
        passing_stage_a(), passing_stage_b(),
        {"blockers": [], "live_allowed": "yes"},
    )
    assert v["verdict"] == "FAIL"
    assert v["explicitly_not_authorized"]


def test_verdict_true_live_allowed_without_blockers_passes():
    v = graduation_verdict(
        passing_stage_a(), passing_stage_b(),
        {"blockers": [], "live_allowed": True},
    )
    assert v["verdict"] == "PASS"
    assert v["explicitly_not_authorized"] == []


# --- Asset-scoped Stage A & CLI tests ---

def test_build_state_requires_asset_address():
    import sqlite3
    from scripts.lp_rh_readiness_v1_readonly import _build_state

    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises((ValueError, TypeError)):
            _build_state(conn, ":memory:", 15.0, asset_address="")
    finally:
        conn.close()


def test_build_state_no_asset_data_fails_stage_a():
    import sqlite3
    from scripts.lp_rh_readiness_v1_readonly import _build_state
    from scripts.lp_rh_coverage_audit_v1_readonly import NO_ASSET_DATA

    from scripts.lp_rh_store_v1_readonly import migrate

    conn = sqlite3.connect(":memory:")
    # Build the real schema rather than one hand-rolled table: _build_state
    # reads rh_gate_decisions further down, so a partial fixture fails for a
    # reason that has nothing to do with what this test is about.
    migrate(conn)
    try:
        state = _build_state(conn, ":memory:", 15.0, asset_address="0xnonexistent")
        st_a = state["stage_a"]
        assert st_a["passed"] is False
        assert st_a["coverage_ratio"] is None
        assert NO_ASSET_DATA in st_a["blockers"]
        assert st_a["reason"] == "无该资产数据"
    finally:
        conn.close()


def test_main_cli_requires_asset_address():
    from scripts.lp_rh_readiness_v1_readonly import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "some.db"])
    assert exc_info.value.code != 0


def test_build_state_real_asset_coverage_reference():
    from scripts.lp_rh_readiness_v1_readonly import (
        STAGE_A_POOL_NOT_ATTESTED,
        _build_state,
    )
    from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH, open_store

    if not Path(DEFAULT_DB_PATH).exists():
        pytest.skip("scanner.db not present")
    conn = open_store(DEFAULT_DB_PATH, read_only=True)
    try:
        target_asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
        state = _build_state(conn, str(DEFAULT_DB_PATH), 15.0, asset_address=target_asset)
        st_a = state["stage_a"]
        assert st_a["coverage_ratio"] is not None
        assert float(st_a["coverage_ratio"]) == pytest.approx(0.9678, abs=0.01)
        assert st_a["passed"] is False
        assert "COVERAGE_INSUFFICIENT" in st_a["blockers"]
        # Attestation state is data, not behaviour: this asserted the live pool
        # had none, which stopped being true the moment the backfill ran.  What
        # is worth pinning here is that the blocker tracks the data -- present
        # when the pool is unattested, absent when it is attested.  The
        # constructed cases above cover both directions.
        attested = conn.execute(
            "SELECT COUNT(*) FROM rh_contract_attestations WHERE LOWER(address) = LOWER(?)",
            (target_asset,),
        ).fetchone()[0]
        if attested:
            assert STAGE_A_POOL_NOT_ATTESTED not in st_a["blockers"]
        else:
            assert STAGE_A_POOL_NOT_ATTESTED in st_a["blockers"]
    finally:
        conn.close()


def test_stage_a_regression_preserves_duration_and_coverage_logic():
    """Anti-regression: Duration (< 72h) and coverage (< 0.99) behavior is identical
    to baseline when other criteria are met."""
    from decimal import Decimal

    # 1. 72h satisfied, coverage < 0.99
    expected = 72 * 3600 // 15
    a1 = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=int(expected * 0.98),
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a1["hours_covered"] == 72.0
    assert Decimal(str(a1["coverage_ratio"])) < Decimal("0.99")
    assert a1["passed"] is False
    assert a1["blockers"] == ["COVERAGE_INSUFFICIENT"]

    # 2. 72h not satisfied (< 72h), coverage >= 0.99
    a2 = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-10T00:00:00Z",
        expected_interval_secs=15, actual_samples=48 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a2["hours_covered"] == 48.0
    assert a2["passed"] is False
    assert a2["blockers"] == ["HOURS_COVERED_INSUFFICIENT"]

    # 3. Both satisfied
    a3 = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a3["passed"] is True
    assert a3["blockers"] == []


def test_address_case_insensitivity_coverage_and_build_state(tmp_path):
    """RH-02bd Acceptance 1: lowercase, uppercase, and EIP-55 checksum addresses
    yield identical results in coverage_for_asset, audit_key_field_health, and _build_state."""
    from scripts.lp_rh_readiness_v1_readonly import (
        _build_state,
        audit_key_field_health,
        audit_pool_attestation,
        coverage_for_asset,
    )
    from scripts.lp_rh_coverage_audit_v1_readonly import fetch_asset_sample_times

    db_file = tmp_path / "test_case.db"
    conn = open_store(str(db_file))
    migrate(conn)

    # Insert sample data with lowercase address
    addr_lower = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    addr_upper = "0X52E65B17FB6E5BA00ED806F37AFCD2DAA50271CA"
    addr_checksum = "0x52E65b17fb6E5bA00ed806f37AfCD2Daa50271Ca"

    # Seed contract attestation
    # Columns below are the store's actual NOT NULL set, read from
    # PRAGMA table_info rather than assumed:
    #   attestations: chain_id, address, block_hash, policy_version,
    #                 attestation_status, created_at
    #   pool_registry: chain_id, protocol, pool_key, attestation_status,
    #                  discovered_at
    insert_row(conn, "rh_contract_attestations", {
        "chain_id": 4663,
        "address": addr_lower,
        "block_hash": "0x" + "ab" * 32,
        "policy_version": "v1",
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "created_at": "2026-09-08T00:00:00Z",
    })
    insert_row(conn, "rh_pool_registry", {
        "chain_id": 4663,
        "protocol": "v3",
        "pool_key": addr_lower,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "discovered_at": "2026-09-08T00:00:00Z",
    })

    # Seed market states
    for i in range(5):
        insert_row(conn, "rh_market_states", {
            "asset_address": addr_lower,
            "sample_time": f"2026-09-08T00:0{i}:00Z",
            "chain_id": 4663,
            "health_flags_json": "[]",
            "reference_mid": "2484.5",
            "multiplier_human": "1.0",
            "session": "REGULAR",
            "fee_growth_global_0": "1000",
            "fee_growth_global_1": "2000",
        })

    # 1. fetch_asset_sample_times
    res_lower = fetch_asset_sample_times(conn, asset_address=addr_lower)
    res_upper = fetch_asset_sample_times(conn, asset_address=addr_upper)
    res_check = fetch_asset_sample_times(conn, asset_address=addr_checksum)
    assert len(res_lower) == 5
    assert res_lower == res_upper == res_check

    # 2. coverage_for_asset
    cov_lower = coverage_for_asset(conn, asset_address=addr_lower, expected_interval_secs=60)
    cov_upper = coverage_for_asset(conn, asset_address=addr_upper, expected_interval_secs=60)
    cov_check = coverage_for_asset(conn, asset_address=addr_checksum, expected_interval_secs=60)
    assert cov_lower["has_data"] is True
    # coverage_for_asset returns analysis/coverage_ratio/status/verdict; there
    # is no sample_count key.  Assert on what it actually returns.
    assert cov_lower["status"] == "OK"
    assert cov_lower["coverage_ratio"] is not None
    # asset_address echoes the caller's spelling; compare the query results.
    def _no_echo(d):
        return {k: v for k, v in d.items() if k != "asset_address"}
    assert _no_echo(cov_lower) == _no_echo(cov_upper) == _no_echo(cov_check)

    # 3. audit_key_field_health
    kf_lower = audit_key_field_health(conn, asset_address=addr_lower)
    kf_upper = audit_key_field_health(conn, asset_address=addr_upper)
    kf_check = audit_key_field_health(conn, asset_address=addr_checksum)
    assert kf_lower["passed"] is True
    assert _no_echo(kf_lower) == _no_echo(kf_upper) == _no_echo(kf_check)

    # 4. _build_state
    st_lower = _build_state(conn, str(db_file), 60.0, asset_address=addr_lower, synthetic_tests_passed=True)
    st_upper = _build_state(conn, str(db_file), 60.0, asset_address=addr_upper, synthetic_tests_passed=True)
    st_check = _build_state(conn, str(db_file), 60.0, asset_address=addr_checksum, synthetic_tests_passed=True)
    assert st_lower["stage_a"]["actual_samples"] == 5
    assert st_lower["stage_a"]["actual_samples"] == st_upper["stage_a"]["actual_samples"] == st_check["stage_a"]["actual_samples"]
    assert st_lower["stage_a"]["blockers"] == st_upper["stage_a"]["blockers"] == st_check["stage_a"]["blockers"]
    conn.close()


def test_audit_invariant_violations_clean_and_detected(tmp_path):
    """RH-02bd Acceptance 2: audit_invariant_violations and automatic _build_state pipeline."""
    from scripts.lp_rh_readiness_v1_readonly import (
        _build_state,
        audit_invariant_violations,
    )

    db_file = tmp_path / "test_inv.db"
    conn = open_store(str(db_file))
    migrate(conn)

    # 1. Clean DB
    clean_audit = audit_invariant_violations(conn)
    assert clean_audit["passed"] is True
    assert clean_audit["violations_count"] == 0

    # 2. Insert invalid state: negative reference_mid in rh_market_states
    insert_row(conn, "rh_market_states", {
        "asset_address": "0x111",
        "chain_id": 4663,
            "health_flags_json": "[]",
            "sample_time": "2026-09-08T00:00:00Z",
        "reference_mid": "-10.0",
        "multiplier_human": "1.0",
        "session": "REGULAR",
    })
    bad_audit = audit_invariant_violations(conn)
    assert bad_audit["passed"] is False
    assert bad_audit["violations_count"] == 1
    assert any("non_positive_reference_mid" in d for d in bad_audit["details"])

    # 3. Clean DB _build_state does NOT add STAGE_A_INVARIANT_VIOLATIONS
    # Insert valid row for 0x222
    for i in range(10):
        insert_row(conn, "rh_market_states", {
            "asset_address": "0x222",
            "chain_id": 4663,
            "health_flags_json": "[]",
            "sample_time": f"2026-09-08T0{i}:00:00Z",
            "reference_mid": "100.0",
            "multiplier_human": "1.0",
            "session": "REGULAR",
            "fee_growth_global_0": "10",
            "fee_growth_global_1": "20",
        })
    insert_row(conn, "rh_contract_attestations", {
        "chain_id": 4663, "address": "0x222", "block_hash": "0x" + "cd" * 32,
        "policy_version": "v1", "attestation_status": "ATTESTED_SAME_BLOCK",
        "created_at": "2026-09-08T00:00:00Z",
    })
    insert_row(conn, "rh_pool_registry", {
        "chain_id": 4663, "protocol": "v3", "pool_key": "0x222",
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "discovered_at": "2026-09-08T00:00:00Z",
    })
    st = _build_state(conn, str(db_file), 3600.0, asset_address="0x222", synthetic_tests_passed=True)
    # The negative mid on 0x111 was caught:
    assert "STAGE_A_INVARIANT_VIOLATIONS" in st["stage_a"]["blockers"]
    conn.close()


def test_key_field_health_real_db_fee_growth_passes():
    """RH-02bj Acceptance 1: fee_growth_global_0/1 passes with ~99.87% on real scanner.db.

    STAGE_A_KEY_FIELDS_INCOMPLETE disappears from Stage A blockers.
    Remaining blockers (hours, coverage, attestation, synthetic tests) must stay.
    """
    from decimal import Decimal
    from scripts.lp_rh_readiness_v1_readonly import (
        _build_state,
        audit_key_field_health,
        STAGE_A_KEY_FIELDS_INCOMPLETE,
    )

    if not DEFAULT_DB_PATH.exists():
        pytest.skip(f"Real database {DEFAULT_DB_PATH} not found")

    conn = open_store(str(DEFAULT_DB_PATH), read_only=True)
    try:
        core_asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
        res = audit_key_field_health(conn, asset_address=core_asset)
        assert res["passed"] is True, f"audit_key_field_health failed: {res}"

        # Verify fee_growth_global_0 and 1 stats in window
        for fg_col in ("fee_growth_global_0", "fee_growth_global_1"):
            col_stat = res["columns"][fg_col]
            assert col_stat["passed"] is True
            assert col_stat["first_populated_time"] is not None
            assert col_stat["window_rows"] > 0
            assert col_stat["total_rows"] > col_stat["window_rows"]  # historical gap exists
            ratio = col_stat["non_null_ratio"]
            # Only the gate threshold is asserted. An earlier revision also
            # pinned the ratio into [0.998, 0.9995] "because the real value is
            # ~99.87%" -- that is the current *data state*, not behaviour, and
            # it self-invalidated as the collector kept running (global_1 drifted
            # to 0.9978 and the test started failing on healthy data). Assert
            # what the gate promises, never the number the database happens to
            # hold today.
            assert ratio >= Decimal("0.99")

        # Full _build_state check: STAGE_A_KEY_FIELDS_INCOMPLETE is gone
        st = _build_state(conn, str(DEFAULT_DB_PATH), 15.0, asset_address=core_asset)
        blockers = st["stage_a"]["blockers"]
        assert STAGE_A_KEY_FIELDS_INCOMPLETE not in blockers
        # These two are time-based and will stay until the window fills.
        assert "HOURS_COVERED_INSUFFICIENT" in blockers
        assert "COVERAGE_INSUFFICIENT" in blockers
        assert "STAGE_A_SYNTHETIC_TESTS_UNKNOWN" in blockers
        # POOL_NOT_ATTESTED is deliberately not asserted: it depends on whether
        # the backfill has run, and it had not when this test was written.
        # Asserting a blocker that someone is actively working to clear turns
        # fixing the problem into a test failure.
    finally:
        conn.close()


def test_key_field_health_never_populated_column_blocks(tmp_path):
    """RH-02bj Acceptance 2: Column that was never populated (all NULL) MUST block.

    Cannot pass under an empty window (guard against empty-set false greens).
    Reason must identify KEY_FIELD_NEVER_POPULATED and name the column.
    """
    from decimal import Decimal
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_key_field_health,
        stage_a_status,
        KEY_FIELD_NEVER_POPULATED,
        STAGE_A_KEY_FIELDS_INCOMPLETE,
    )

    db_file = tmp_path / "never_pop.db"
    conn = open_store(str(db_file))
    migrate(conn)

    asset = "0xaaaa111122223333444455556666777788889999"
    # Insert 10 rows with fee_growth_global_0 completely NULL
    for i in range(10):
        insert_row(conn, "rh_market_states", {
            "asset_address": asset,
            "chain_id": 4663,
            "health_flags_json": "[]",
            "session": "REGULAR",
            "sample_time": f"2026-09-08T0{i}:00:00Z",
            "reference_mid": "2500.0",
            "fee_growth_global_0": None,  # NEVER POPULATED
            "fee_growth_global_1": "12345",
        })

    res = audit_key_field_health(conn, asset_address=asset)
    assert res["passed"] is False
    assert KEY_FIELD_NEVER_POPULATED in res.get("reason", "")
    assert res.get("code") == KEY_FIELD_NEVER_POPULATED

    col_stat = res["columns"]["fee_growth_global_0"]
    assert col_stat["passed"] is False
    assert col_stat["first_populated_time"] is None
    assert col_stat["window_rows"] == 0
    assert col_stat["non_null_count"] == 0
    assert col_stat["non_null_ratio"] == Decimal("0")
    assert col_stat["code"] == KEY_FIELD_NEVER_POPULATED
    assert "fee_growth_global_0" in col_stat["reason"]

    # In Stage A status, this must block graduation
    st_a = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True,
        key_field_health=res,
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
    )
    assert st_a["passed"] is False
    assert STAGE_A_KEY_FIELDS_INCOMPLETE in st_a["blockers"]
    conn.close()


def test_key_field_health_window_boundary_and_non_null_calculation(tmp_path):
    """RH-02bj Acceptance 3: Pre-deployment NULLs excluded; window NULLs calculated accurately."""
    from decimal import Decimal
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_key_field_health,
        KEY_FIELD_INCOMPLETE,
    )

    db_file = tmp_path / "window_bound.db"
    conn = open_store(str(db_file))
    migrate(conn)

    asset = "0xbbbb111122223333444455556666777788889999"
    # 1. 5 pre-deployment rows (fee_growth_global_0 is NULL)
    for i in range(5):
        insert_row(conn, "rh_market_states", {
            "asset_address": asset,
            "chain_id": 4663,
            "health_flags_json": "[]",
            "session": "REGULAR",
            "sample_time": f"2026-09-08T00:0{i}:00Z",
            "reference_mid": "2500.0",
            "fee_growth_global_0": None,
            "fee_growth_global_1": "1000",
        })

    # 2. 100 rows in the deployment window: 99 non-null, 1 NULL (at minute 50)
    for i in range(100):
        m = i % 60
        h = i // 60
        fg0_val = None if i == 50 else str(1000 + i)
        insert_row(conn, "rh_market_states", {
            "asset_address": asset,
            "chain_id": 4663,
            "health_flags_json": "[]",
            "session": "REGULAR",
            "sample_time": f"2026-09-09T{h:02d}:{m:02d}:00Z",
            "reference_mid": "2500.0",
            "fee_growth_global_0": fg0_val,
            "fee_growth_global_1": "2000",
        })

    # Total rows = 105. Window starts at 2026-09-09T00:00:00Z.
    # Window rows = 100. Non-null = 99. Ratio = 0.99 -> PASS.
    res = audit_key_field_health(conn, asset_address=asset)
    assert res["passed"] is True
    fg0 = res["columns"]["fee_growth_global_0"]
    assert fg0["passed"] is True
    assert fg0["first_populated_time"] == "2026-09-09T00:00:00Z"
    assert fg0["total_rows"] == 105
    assert fg0["window_rows"] == 100
    assert fg0["non_null_count"] == 99
    assert fg0["non_null_ratio"] == Decimal("0.99")

    # 3. Add one more NULL row in the window: 99 / 101 ≈ 0.9802 < 0.99 -> FAIL
    insert_row(conn, "rh_market_states", {
        "asset_address": asset,
        "chain_id": 4663,
        "health_flags_json": "[]",
        "session": "REGULAR",
        "sample_time": "2026-09-09T02:00:00Z",
        "reference_mid": "2500.0",
        "fee_growth_global_0": None,
        "fee_growth_global_1": "2000",
    })
    res2 = audit_key_field_health(conn, asset_address=asset)
    assert res2["passed"] is False
    fg0_2 = res2["columns"]["fee_growth_global_0"]
    assert fg0_2["passed"] is False
    assert fg0_2["window_rows"] == 101
    assert fg0_2["non_null_count"] == 99
    assert KEY_FIELD_INCOMPLETE in fg0_2["reason"]
    conn.close()


def test_key_field_health_anti_regression_all_populated(tmp_path):
    """RH-02bj Acceptance 4: A database with all columns 100% non-null behaves identically to baseline."""
    from decimal import Decimal
    from scripts.lp_rh_readiness_v1_readonly import (
        STAGE_A_KEY_COLUMNS,
        audit_key_field_health,
    )

    db_file = tmp_path / "all_pop.db"
    conn = open_store(str(db_file))
    migrate(conn)

    asset = "0xcccc111122223333444455556666777788889999"
    for i in range(10):
        insert_row(conn, "rh_market_states", {
            "asset_address": asset,
            "chain_id": 4663,
            "health_flags_json": "[]",
            "session": "REGULAR",
            "sample_time": f"2026-09-08T0{i}:00:00Z",
            "reference_mid": "2500.0",
            "fee_growth_global_0": "1000",
            "fee_growth_global_1": "2000",
        })

    res = audit_key_field_health(conn, asset_address=asset)
    assert res["passed"] is True
    assert res["total_rows"] == 10
    for col in STAGE_A_KEY_COLUMNS:
        c = res["columns"][col]
        assert c["passed"] is True
        assert c["total_rows"] == 10
        assert c["window_rows"] == 10
        assert c["non_null_count"] == 10
        assert c["non_null_ratio"] == Decimal("1")
    conn.close()


def test_render_dashboard_key_field_window_visible():
    """RH-02bj Acceptance Requirement 2: Dashboard clearly displays key field window info."""
    from decimal import Decimal
    from scripts.lp_rh_readiness_v1_readonly import render_dashboard

    state = {
        "stage_a": {
            "hours_covered": 48.0,
            "coverage_ratio": Decimal("0.995"),
            "passed": False,
            "blockers": ["HOURS_COVERED_INSUFFICIENT"],
            "key_field_health": {
                "passed": True,
                "columns": {
                    "fee_growth_global_0": {
                        "first_populated_time": "2026-09-09T16:05:55Z",
                        "window_rows": 2254,
                        "total_rows": 10311,
                        "non_null_ratio": Decimal("0.9987"),
                        "passed": True,
                    }
                }
            }
        },
        "stage_b": {"passed": False},
        "live_gate": {"live_allowed": False, "blockers": ["SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE"]},
    }
    rendered = render_dashboard(state)
    assert "key_fields:" in rendered
    assert "fee_growth_global_0" in rendered
    assert "2026-09-09T16:05:55Z" in rendered
    assert "2254/10311" in rendered


# --- RH-02bm & RH-02bm-2 tests ---
import sqlite3
from datetime import datetime, timedelta, timezone

from scripts.lp_rh_readiness_v1_readonly import (
    audit_missed_risk_events,
    audit_unexplained_ledger_diffs,
    audit_weekends_covered,
)


def test_audit_unexplained_ledger_diffs_missing_table():
    """1. rh_journal table does not exist -> count is None, blockers include UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE."""
    conn = sqlite3.connect(":memory:")
    res = audit_unexplained_ledger_diffs(conn)
    assert res["count"] is None
    assert res["reason"] == "NO_JOURNAL_EVIDENCE"
    status = stage_b_status(days_covered=14, weekends_covered=2,
                            unexplained_ledger_diffs=res["count"],
                            invariant_violations=0, missed_risk_events=0)
    assert "UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE" in status["blockers"]
    conn.close()


def test_audit_unexplained_ledger_diffs_empty_table():
    """2. rh_journal exists but 0 rows -> count is None (unknown, not zero diffs)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_journal (
        event_id TEXT, idempotency_key TEXT, account_debit TEXT, account_credit TEXT,
        asset TEXT, amount_raw TEXT, is_external_flow INTEGER, ref_json TEXT, booked_at TEXT
    )""")
    res = audit_unexplained_ledger_diffs(conn)
    assert res["count"] is None
    assert res["reason"] == "NO_JOURNAL_EVIDENCE"
    status = stage_b_status(days_covered=14, weekends_covered=2,
                            unexplained_ledger_diffs=res["count"],
                            invariant_violations=0, missed_risk_events=0)
    assert "UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE" in status["blockers"]
    conn.close()


def test_audit_unexplained_ledger_diffs_unbalanced_entry():
    """3. rh_journal has an unbalanced entry -> count == 1, blockers include UNEXPLAINED_LEDGER_DIFFS."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_journal (
        event_id TEXT, idempotency_key TEXT, account_debit TEXT, account_credit TEXT,
        asset TEXT, amount_raw TEXT, is_external_flow INTEGER, ref_json TEXT, booked_at TEXT
    )""")
    conn.execute(
        "INSERT INTO rh_journal (event_id, idempotency_key, account_debit, account_credit, "
        "asset, amount_raw, is_external_flow, ref_json, booked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("evt_1", "idem_1", "VAULT_ETH", "", "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca",
         "1000000000000000000", 0, "{}", "2026-09-08T00:00:00Z")
    )
    res = audit_unexplained_ledger_diffs(conn)
    assert res["count"] == 1
    assert res["reason"] == "UNBALANCED_ENTRIES"
    status = stage_b_status(days_covered=14, weekends_covered=2,
                            unexplained_ledger_diffs=res["count"],
                            invariant_violations=0, missed_risk_events=0)
    assert "UNEXPLAINED_LEDGER_DIFFS" in status["blockers"]
    conn.close()


def test_audit_missed_risk_events_empty_table():
    """4. rh_gate_decisions has 0 rows -> count is None, blockers include MISSED_RISK_EVENTS_UNAVAILABLE."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_gate_decisions (
        decision_id TEXT, candidate_key TEXT, target_mode TEXT, primary_status TEXT,
        terminal_bits_json TEXT, dominant_blocker TEXT, reasons_json TEXT, snapshot_ids_json TEXT,
        decided_at TEXT, derived_block_hash TEXT, derived_block_number INTEGER
    )""")
    res = audit_missed_risk_events(conn)
    assert res["count"] is None
    assert res["reason"] == "NO_GATE_DECISION_EVIDENCE"
    status = stage_b_status(days_covered=14, weekends_covered=2,
                            unexplained_ledger_diffs=0, invariant_violations=0,
                            missed_risk_events=res["count"])
    assert "MISSED_RISK_EVENTS_UNAVAILABLE" in status["blockers"]
    conn.close()


def test_audit_missed_risk_events_computed_pass_with_degraded_market():
    """5. A primary_status='COMPUTED_PASS' decision + contemporary health_flags_json='[\"CHAIN_DEGRADED\"]' -> count >= 1."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_gate_decisions (
        decision_id TEXT, candidate_key TEXT, target_mode TEXT, primary_status TEXT,
        terminal_bits_json TEXT, dominant_blocker TEXT, reasons_json TEXT, snapshot_ids_json TEXT,
        decided_at TEXT, derived_block_hash TEXT, derived_block_number INTEGER
    )""")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT, health_flags_json TEXT
    )""")
    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time, health_flags_json) "
        "VALUES (?, ?, ?)",
        ("0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca", "2026-09-08T12:00:00Z", '["CHAIN_DEGRADED"]')
    )
    conn.execute(
        "INSERT INTO rh_gate_decisions (decision_id, candidate_key, target_mode, primary_status, "
        "terminal_bits_json, dominant_blocker, reasons_json, snapshot_ids_json, decided_at, "
        "derived_block_hash, derived_block_number) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("dec_1", "cand_1", "LIVE", "COMPUTED_PASS", "{}", None, "[]", "[]",
         "2026-09-08T12:00:05Z", "0xabc", 100)
    )
    res = audit_missed_risk_events(conn)
    assert res["count"] is not None and res["count"] >= 1
    assert "rh_gate_decisions:dec_1:COMPUTED_PASS_with_health_flags:['CHAIN_DEGRADED']" in res["details"][0]
    status = stage_b_status(days_covered=14, weekends_covered=2,
                            unexplained_ledger_diffs=0, invariant_violations=0,
                            missed_risk_events=res["count"])
    assert "MISSED_RISK_EVENTS" in status["blockers"]
    conn.close()


def test_audit_weekends_covered_full_saturday_and_sunday():
    """6. Complete Saturday + Sunday samples (each >= 90% density, interval 15s) -> weekends_covered == 2."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT
    )""")
    asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    start_ts = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(11520):
        t = start_ts + timedelta(seconds=i * 15)
        rows.append((asset, t.isoformat().replace("+00:00", "Z")))
    conn.executemany("INSERT INTO rh_market_states (asset_address, sample_time) VALUES (?, ?)", rows)
    res = audit_weekends_covered(conn, asset_address=asset, interval_secs=15)
    assert res["weekends_covered"] == 2
    assert res["reason"] == "OK"
    assert len(res["days"]) == 2
    assert res["days"][0]["complete"] is True
    assert res["days"][1]["complete"] is True
    conn.close()


def test_audit_weekends_covered_saturday_sparse_excluded():
    """7. Saturday has only 10 samples -> that day is not counted."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT
    )""")
    asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    start_ts = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(10):
        t = start_ts + timedelta(hours=i)
        rows.append((asset, t.isoformat().replace("+00:00", "Z")))
    conn.executemany("INSERT INTO rh_market_states (asset_address, sample_time) VALUES (?, ?)", rows)
    res = audit_weekends_covered(conn, asset_address=asset, interval_secs=15)
    assert res["weekends_covered"] == 0
    assert res["reason"] == "OK"
    assert res["days"][0]["complete"] is False
    conn.close()


def test_audit_weekends_covered_partial_day_prorating_branches_no_crash():
    """8. First/last partial day prorating branches are truly executed (Saturday 12:00 to Sunday 12:00).
    Verifies weekends_covered has a concrete integer value and reason does not start with audit_exception:.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT
    )""")
    asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    start_ts = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    end_ts = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    curr = start_ts
    while curr <= end_ts:
        rows.append((asset, curr.isoformat().replace("+00:00", "Z")))
        curr += timedelta(seconds=15)
    conn.executemany("INSERT INTO rh_market_states (asset_address, sample_time) VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address=asset, interval_secs=15)
    assert not res["reason"].startswith("audit_exception:")
    assert res["reason"] == "OK"
    assert isinstance(res["weekends_covered"], int)
    assert res["weekends_covered"] == 2
    assert len(res["days"]) == 2
    assert res["days"][0]["complete"] is True
    assert res["days"][1]["complete"] is True
    conn.close()


def test_audit_weekends_covered_case_insensitive_eip55_address():
    """9. Asset address passed as mixed-case EIP-55 still matches lowercase stored rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT
    )""")
    lower_asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    mixed_asset = "0x52E65b17Fb6e5BA00ed806f37afcd2dAa50271Ca"
    start_ts = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(10):
        t = start_ts + timedelta(seconds=i * 15)
        rows.append((lower_asset, t.isoformat().replace("+00:00", "Z")))
    conn.executemany("INSERT INTO rh_market_states (asset_address, sample_time) VALUES (?, ?)", rows)

    res = audit_weekends_covered(conn, asset_address=mixed_asset, interval_secs=15)
    assert res["reason"] == "OK"
    assert res["checks_performed"] == ["rh_market_states:weekend_coverage"]
    assert len(res["days"]) == 1
    assert res["days"][0]["actual"] == 10
    conn.close()

