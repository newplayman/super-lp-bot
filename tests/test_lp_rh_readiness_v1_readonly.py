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



def _market_row(**over):
    """One rh_market_states row with every NOT NULL column filled in.

    Four workers in a row hand-wrote this dict and hit
    `NOT NULL constraint failed`, because insert_row() silently drops names the
    table does not have -- one of them passed twelve keys of which nine were
    invented (pool_address, block_number, price, spread, depth_bid, ...), so the
    only signal was a NOT NULL failure on a column they *had* omitted.

    Real columns:
      NOT NULL: asset_address, sample_time, chain_id, session, health_flags_json
      nullable: source_payload_hash, reference_bid, reference_ask, reference_mid,
                reference_age_secs, multiplier_human, oracle_paused,
                derived_block_hash, derived_block_number, source_event_time,
                fee_growth_global_0, fee_growth_global_1
    """
    row = {
        "asset_address": "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca",
        "sample_time": "2026-09-08T00:00:00Z",
        "chain_id": 4663,
        "session": "RTH",
        "health_flags_json": "[]",
        "reference_mid": "2400",
    }
    row.update(over)
    return row


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

    # Evidence False -> blocked (RH-02bw: STAGE_A_SYNTHETIC_TESTS_FAILED)
    a_false = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=False, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=0, unknown_state_positions=0,
    )
    assert a_false["passed"] is False
    assert "STAGE_A_SYNTHETIC_TESTS_FAILED" in a_false["blockers"]
    assert "STAGE_A_SYNTHETIC_TESTS_UNKNOWN" not in a_false["blockers"]


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
    from scripts.lp_rh_readiness_v1_readonly import (
        STAGE_A_INVARIANT_VIOLATIONS,
        STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE,
    )
    # None
    a_none = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=None, unknown_state_positions=0,
    )
    assert a_none["passed"] is False
    assert STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE in a_none["blockers"]
    assert STAGE_A_INVARIANT_VIOLATIONS not in a_none["blockers"]

    # > 0
    a_viol = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=2, unknown_state_positions=0,
    )
    assert a_viol["passed"] is False
    assert STAGE_A_INVARIANT_VIOLATIONS in a_viol["blockers"]
    assert STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE not in a_viol["blockers"]


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
        # Assert structural properties, never the number the database happens
        # to hold. An earlier revision pinned this to approx(0.9678) -- the live
        # ratio at the time -- and it broke twice: once as the collector kept
        # running, and again when RH-02bn moved the judgment to a window.
        assert st_a["coverage_ratio"] is not None
        assert 0 < float(st_a["coverage_ratio"]) <= 1
        assert st_a["cumulative_coverage_ratio"] is not None
        assert 0 < float(st_a["cumulative_coverage_ratio"]) <= 1
        # The judgment window is a suffix of the full span, so it can never
        # cover more hours than the cumulative view.
        assert st_a["judgment_window_start"] is not None
        assert float(st_a["hours_covered"]) <= float(st_a["cumulative_hours"])
        assert st_a["passed"] is False
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
    #
    # judgment_window_start is pinned here on purpose. Without it, RH-02bn
    # resolves the window from the repo's own git history (the last commit
    # touching the collector), which has nothing to do with a tmp_path fixture:
    # every constructed sample would fall before the window and the state would
    # come back empty. This test is about address case, so the window is fixed
    # to a point before the fixture's samples.
    _WIN = "2026-09-01T00:00:00Z"
    st_lower = _build_state(conn, str(db_file), 60.0, asset_address=addr_lower, synthetic_tests_passed=True, judgment_window_start=_WIN)
    st_upper = _build_state(conn, str(db_file), 60.0, asset_address=addr_upper, synthetic_tests_passed=True, judgment_window_start=_WIN)
    st_check = _build_state(conn, str(db_file), 60.0, asset_address=addr_checksum, synthetic_tests_passed=True, judgment_window_start=_WIN)
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

    # 1. Clean DB (all 4 tables have valid rows)
    insert_row(conn, "rh_gate_decisions", {
        "decision_id": "dec_1",
        "candidate_key": "cand_1",
        "target_mode": "SHADOW",
        "decided_at": "2026-09-08T00:00:00Z",
        "primary_status": "COMPUTED_PASS",
        "dominant_blocker": "",
        "terminal_bits_json": json.dumps({"bit1": True}),
    })
    insert_row(conn, "rh_position_marks", {
        "position_id": "pos_1",
        "mark_time": "2026-09-08T00:00:00Z",
        "reference_nav": "100.0",
    })
    insert_row(conn, "rh_journal", {
        "event_id": "evt_1",
        "idempotency_key": "id_1",
        "account_debit": "VAULT_ETH",
        "account_credit": "USER_CASH",
        "asset": "0x111",
        "amount_raw": "1000",
        "is_external_flow": 0,
        "ref_json": "{}",
        "booked_at": "2026-09-08T00:00:00Z",
    })
    insert_row(conn, "rh_market_states", {
        "asset_address": "0x111",
        "chain_id": 4663,
        "health_flags_json": "[]",
        "sample_time": "2026-09-08T00:00:00Z",
        "reference_mid": "10.0",
        "multiplier_human": "1.0",
        "session": "REGULAR",
    })
    clean_audit = audit_invariant_violations(conn)
    assert clean_audit["passed"] is True
    assert clean_audit["violations_count"] == 0

    # 2. Insert invalid state: negative reference_mid in rh_market_states
    insert_row(conn, "rh_market_states", {
        "asset_address": "0x111",
        "chain_id": 4663,
        "health_flags_json": "[]",
        "sample_time": "2026-09-08T00:00:01Z",
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


def test_key_field_health_real_db_window_mechanism():
    """RH-02bj: on the real scanner.db, key-field health is measured from when
    each column started existing, not over the whole table.

    This asserts the *mechanism*, never the health of today's data. Two earlier
    revisions asserted the latter and both broke on healthy code:

      1. pinned the ratio to approx(0.9987) -- drifted as the collector ran
      2. asserted res["passed"] is True -- on 2026-09-10 a single upstream RPC
         outage pushed fee_growth non-null down to 0.9887 and the suite went red
         over a real infrastructure incident, which is not what a unit test is for

    The gate's own behaviour is covered by the constructed-fixture tests above;
    what only the real database can show is that the window is actually narrower
    than the table.
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

        # fee_growth was added to the schema on 2026-09-09T16:05:55, long after
        # collection began, so its window must be a strict subset of the table.
        # That is the whole point of RH-02bj: without the window these columns
        # would need ~159 days of perfect collection to dilute the pre-existing
        # NULLs above the threshold.
        for fg_col in ("fee_growth_global_0", "fee_growth_global_1"):
            col_stat = res["columns"][fg_col]
            assert col_stat["first_populated_time"] is not None
            assert col_stat["window_rows"] > 0
            assert col_stat["total_rows"] > col_stat["window_rows"]
            ratio = col_stat["non_null_ratio"]
            assert Decimal(0) <= ratio <= Decimal(1)

        # Columns that were present from the first sample get the full table as
        # their window -- the mechanism must not shrink those.
        for base_col in ("sample_time", "session"):
            col_stat = res["columns"][base_col]
            assert col_stat["window_rows"] == col_stat["total_rows"]

        # _build_state must assemble without raising on real data and produce a
        # blocker list. Which blockers are present depends on collection health
        # at this instant (an RPC outage adds KEY_FIELDS/COVERAGE, time removes
        # HOURS) and is deliberately not asserted here.
        st = _build_state(conn, str(DEFAULT_DB_PATH), 15.0, asset_address=core_asset)
        assert isinstance(st["stage_a"]["blockers"], list)
        assert st["stage_a"]["passed"] is False
        # COVERAGE_INSUFFICIENT is deliberately not asserted here. This test is
        # about key-field health; coverage now depends on the RH-02bn judgment
        # window, and pinning it would make an unrelated test fail whenever the
        # window moves. The windowed cases in the RH-02bn block cover it.
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


# --- RH-02bo: Empty evidence is not zero invariant violations ---
import json
from decimal import Decimal

from scripts.lp_rh_readiness_v1_readonly import (
    STAGE_A_INVARIANT_VIOLATIONS,
    STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE,
    audit_invariant_violations,
)


def test_rh02bo_1_all_tables_missing():
    """1. 四张相关表全部不存在 -> violations_count is None, unavailable_checks 含全部四项。"""
    conn = sqlite3.connect(":memory:")
    res = audit_invariant_violations(conn)
    assert res["violations_count"] is None
    assert res["passed"] is False
    expected = {
        "rh_gate_decisions:conjunction_consistency",
        "rh_market_states:price_positivity_and_spread",
        "rh_position_marks:nav_non_negative",
        "rh_journal:accounts_and_amounts",
    }
    assert set(res["unavailable_checks"]) == expected
    assert res["checks_performed"] == []
    conn.close()


def test_rh02bo_2_all_tables_exist_but_empty():
    """2. 四张表都存在但都是 0 行 -> violations_count is None (空表 != 零违反)。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_gate_decisions (decision_id TEXT, primary_status TEXT, terminal_bits_json TEXT, dominant_blocker TEXT)")
    conn.execute("CREATE TABLE rh_market_states (reference_mid TEXT, reference_bid TEXT, reference_ask TEXT)")
    conn.execute("CREATE TABLE rh_position_marks (reference_nav TEXT)")
    conn.execute("CREATE TABLE rh_journal (account_debit TEXT, account_credit TEXT, amount_raw TEXT)")
    res = audit_invariant_violations(conn)
    assert res["violations_count"] is None
    assert res["passed"] is False
    expected = {
        "rh_gate_decisions:conjunction_consistency",
        "rh_market_states:price_positivity_and_spread",
        "rh_position_marks:nav_non_negative",
        "rh_journal:accounts_and_amounts",
    }
    assert set(res["unavailable_checks"]) == expected
    assert res["checks_performed"] == []
    conn.close()


def test_rh02bo_3_one_table_has_rows_others_empty():
    """3. rh_market_states 有正常行、其余三张为空 -> violations_count is None, checks_performed 含市场那项、unavailable_checks 含其余三项。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_gate_decisions (decision_id TEXT, primary_status TEXT, terminal_bits_json TEXT, dominant_blocker TEXT)")
    conn.execute("CREATE TABLE rh_market_states (reference_mid TEXT, reference_bid TEXT, reference_ask TEXT)")
    conn.execute("CREATE TABLE rh_position_marks (reference_nav TEXT)")
    conn.execute("CREATE TABLE rh_journal (account_debit TEXT, account_credit TEXT, amount_raw TEXT)")
    conn.execute("INSERT INTO rh_market_states VALUES ('100.0', '99.0', '101.0')")
    res = audit_invariant_violations(conn)
    assert res["violations_count"] is None
    assert res["passed"] is False
    assert res["checks_performed"] == ["rh_market_states:price_positivity_and_spread"]
    expected_unavail = {
        "rh_gate_decisions:conjunction_consistency",
        "rh_position_marks:nav_non_negative",
        "rh_journal:accounts_and_amounts",
    }
    assert set(res["unavailable_checks"]) == expected_unavail
    conn.close()


def test_rh02bo_4_all_tables_have_rows_and_clean():
    """4. 四张表都有行且都干净 -> violations_count == 0, unavailable_checks == [], passed is True。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_gate_decisions (decision_id TEXT, primary_status TEXT, terminal_bits_json TEXT, dominant_blocker TEXT)")
    conn.execute("CREATE TABLE rh_market_states (reference_mid TEXT, reference_bid TEXT, reference_ask TEXT)")
    conn.execute("CREATE TABLE rh_position_marks (reference_nav TEXT)")
    conn.execute("CREATE TABLE rh_journal (account_debit TEXT, account_credit TEXT, amount_raw TEXT)")
    conn.execute("INSERT INTO rh_gate_decisions VALUES ('dec_1', 'COMPUTED_PASS', '{\"b\": true}', NULL)")
    conn.execute("INSERT INTO rh_market_states VALUES ('100.0', '99.0', '101.0')")
    conn.execute("INSERT INTO rh_position_marks VALUES ('50.0')")
    conn.execute("INSERT INTO rh_journal VALUES ('ACC_A', 'ACC_B', '100')")
    res = audit_invariant_violations(conn)
    assert res["violations_count"] == 0
    assert res["unavailable_checks"] == []
    assert res["passed"] is True
    assert len(res["checks_performed"]) == 4
    conn.close()


def test_rh02bo_5_all_tables_have_rows_with_violation():
    """5. 四张表都有行、其中 rh_journal 有一条借贷账户为空的行 -> violations_count >= 1。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_gate_decisions (decision_id TEXT, primary_status TEXT, terminal_bits_json TEXT, dominant_blocker TEXT)")
    conn.execute("CREATE TABLE rh_market_states (reference_mid TEXT, reference_bid TEXT, reference_ask TEXT)")
    conn.execute("CREATE TABLE rh_position_marks (reference_nav TEXT)")
    conn.execute("CREATE TABLE rh_journal (account_debit TEXT, account_credit TEXT, amount_raw TEXT)")
    conn.execute("INSERT INTO rh_gate_decisions VALUES ('dec_1', 'COMPUTED_PASS', '{\"b\": true}', NULL)")
    conn.execute("INSERT INTO rh_market_states VALUES ('100.0', '99.0', '101.0')")
    conn.execute("INSERT INTO rh_position_marks VALUES ('50.0')")
    conn.execute("INSERT INTO rh_journal VALUES ('', 'ACC_B', '100')")
    res = audit_invariant_violations(conn)
    assert res["violations_count"] is not None
    assert res["violations_count"] >= 1
    assert res["passed"] is False
    assert res["unavailable_checks"] == []
    conn.close()


def test_rh02bo_6_stage_a_status_none_invariant():
    """6. stage_a_status(invariant_violations=None, ...) -> blockers 含 STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE 且不含 STAGE_A_INVARIANT_VIOLATIONS。"""
    res = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=None, unknown_state_positions=0,
    )
    assert STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE in res["blockers"]
    assert STAGE_A_INVARIANT_VIOLATIONS not in res["blockers"]
    assert res["passed"] is False


def test_rh02bo_7_stage_a_status_positive_invariant():
    """7. stage_a_status(invariant_violations=3, ...) -> blockers 含 STAGE_A_INVARIANT_VIOLATIONS 且不含 ..._UNAVAILABLE。"""
    res = stage_a_status(
        first_sample="2026-09-08T00:00:00Z", last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15, actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True, key_field_health={"passed": True},
        pool_attestation_status={"passed": True}, budget=BUDGET_OK,
        invariant_violations=3, unknown_state_positions=0,
    )
    assert STAGE_A_INVARIANT_VIOLATIONS in res["blockers"]
    assert STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE not in res["blockers"]
    assert res["passed"] is False


def test_rh02bo_render_dashboard_unavailable_checks():
    """RH-02bo Markdown 报告显示未执行的检查。"""
    state = {
        "stage_a": {
            "hours_covered": 72.0,
            "coverage_ratio": Decimal("0.995"),
            "passed": False,
            "blockers": [STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE],
        },
        "stage_b": {"passed": False},
        "live_gate": {"live_allowed": False},
        "invariant_violations_audit": {
            "violations_count": None,
            "unavailable_checks": [
                "rh_journal:accounts_and_amounts",
                "rh_gate_decisions:conjunction_consistency",
                "rh_position_marks:nav_non_negative",
            ],
        },
    }
    rendered = render_dashboard(state)
    assert "invariant: NOT_MEASURED (未执行的检查: rh_journal:accounts_and_amounts, rh_gate_decisions:conjunction_consistency, rh_position_marks:nav_non_negative)" in rendered


# --- RH-02bn: Judgment Window Tests ---

def test_rh02bn_1_resolve_judgment_window_non_git_dir(tmp_path):
    """1. resolve_judgment_window 指向非 git 目录 (tmp_path) -> window_start is None 且 reason 非空。"""
    from scripts.lp_rh_readiness_v1_readonly import resolve_judgment_window
    res = resolve_judgment_window(str(tmp_path))
    assert res["window_start"] is None
    assert res["code_version"] is None
    assert res["reason"] is not None and len(res["reason"]) > 0


def test_rh02bn_2_stage_a_status_unresolved_judgment_window():
    """2. 承 1：stage_a_status 拿到 window_start is None 结果 -> blockers 含 JUDGMENT_WINDOW_UNRESOLVED, passed is False。"""
    from scripts.lp_rh_readiness_v1_readonly import JUDGMENT_WINDOW_UNRESOLVED
    unresolved_window = {
        "window_start": None,
        "code_version": None,
        "source": "git log",
        "reason": "non-git repo",
    }
    res = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True,
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
        judgment_window=unresolved_window,
    )
    assert res["passed"] is False
    assert JUDGMENT_WINDOW_UNRESOLVED in res["blockers"]


def test_rh02bn_3_and_4_windowed_coverage_and_hours(tmp_path):
    """3 & 4. 构造库：窗口前有大量缺口、窗口后满格。
    -> 窗口内 coverage_ratio >= 0.99 且 blockers 不含 COVERAGE_INSUFFICIENT；
    同一份数据的 cumulative_coverage_ratio < 0.99；
    hours_covered 用的是窗口内跨度，明显小于 cumulative_hours。"""
    from scripts.lp_rh_readiness_v1_readonly import _build_state
    db_file = tmp_path / "test_window.db"
    conn = open_store(str(db_file))
    migrate(conn)

    asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"

    # Attestation.  Real columns only -- rh_contract_attestations has
    # address/chain_id/block_hash/policy_version/attestation_status/created_at,
    # and insert_row silently drops names that do not exist, so a guessed schema
    # only surfaces later as a NOT NULL failure.
    insert_row(conn, "rh_contract_attestations", {
        "chain_id": 4663,
        "address": asset,
        "block_hash": "0x" + "cd" * 32,
        "policy_version": "v1",
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "created_at": "2026-09-09T00:00:00Z",
    })

    # Pre-window: 100 hours total span (from 2026-09-05T00:00:00Z to 2026-09-09T04:00:00Z)
    # but only 10 samples (massive gaps)
    t_start = datetime(2026, 9, 5, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(10):
        st = (t_start + timedelta(hours=i * 10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO rh_market_states "
            "(asset_address, sample_time, chain_id, session, health_flags_json, reference_mid, fee_growth_global_0, fee_growth_global_1) "
            "VALUES (?, ?, 'base', 'REGULAR', '[]', '100', '1', '1')",
            (asset, st),
        )

    # Window start
    win_start_dt = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
    win_start_iso = win_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Post-window: 73 hours of perfect cadence (interval=60s)
    # 73 * 60 = 4380 samples
    samples_in_window = 73 * 60
    for i in range(samples_in_window):
        st = (win_start_dt + timedelta(seconds=i * 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO rh_market_states "
            "(asset_address, sample_time, chain_id, session, health_flags_json, reference_mid, fee_growth_global_0, fee_growth_global_1) "
            "VALUES (?, ?, 'base', 'REGULAR', '[]', '100', '1', '1')",
            (asset, st),
        )
    conn.commit()

    state = _build_state(
        conn,
        str(db_file),
        interval_secs=60.0,
        asset_address=asset,
        synthetic_tests_passed=True,
        invariant_violations=0,
        judgment_window_start=win_start_iso,
    )
    conn.close()

    st_a = state["stage_a"]
    assert "COVERAGE_INSUFFICIENT" not in st_a["blockers"]
    assert Decimal(str(st_a["coverage_ratio"])) >= Decimal("0.99")
    assert Decimal(str(st_a["cumulative_coverage_ratio"])) < Decimal("0.99")
    # Hours covered is window span (72.98 ~ 73.0), cumulative is ~180.98 hours
    assert st_a["hours_covered"] < st_a["cumulative_hours"]
    assert st_a["hours_covered"] >= 72.0
    assert st_a["cumulative_hours"] > 100.0


def test_rh02bn_5_thresholds_unmodified():
    """5. 阈值没被动过：窗口内 hours=71.9 -> 仍有 HOURS_COVERED_INSUFFICIENT；窗口内 coverage=0.9899 -> 仍有 COVERAGE_INSUFFICIENT。"""
    jw_ok = {"window_start": "2026-09-08T00:00:00Z", "code_version": "test1234", "source": "git", "reason": "OK"}
    # 71.9 hours, 100% coverage
    res_hours = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-10T23:54:00Z",  # 71.9 hours = 258840s
        expected_interval_secs=60,
        actual_samples=258840 // 60,
        synthetic_tests_passed=True,
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
        judgment_window=jw_ok,
    )
    assert "HOURS_COVERED_INSUFFICIENT" in res_hours["blockers"]
    assert res_hours["passed"] is False

    # 72.0 hours, 0.9899 coverage
    expected = 72 * 3600 // 60
    res_cov = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=60,
        actual_samples=int(expected * 0.9899),
        coverage_ratio=Decimal("0.9899"),
        synthetic_tests_passed=True,
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
        judgment_window=jw_ok,
    )
    assert "COVERAGE_INSUFFICIENT" in res_cov["blockers"]
    assert res_cov["passed"] is False


def test_rh02bn_6_judgment_window_override_cli_and_state(tmp_path):
    """6. --judgment-window-start 覆盖生效，且 code_version == 'OVERRIDE'。"""
    from scripts.lp_rh_readiness_v1_readonly import _build_state
    db_file = tmp_path / "test_override.db"
    conn = open_store(str(db_file))
    migrate(conn)

    asset = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    conn.execute(
        "INSERT INTO rh_market_states "
        "(asset_address, sample_time, chain_id, session, health_flags_json, reference_mid, fee_growth_global_0, fee_growth_global_1) "
        "VALUES (?, '2026-09-09T16:10:00Z', 'base', 'REGULAR', '[]', '100', '1', '1')",
        (asset,),
    )
    conn.commit()

    override_ts = "2026-09-09T16:05:41Z"
    state = _build_state(
        conn,
        str(db_file),
        interval_secs=15.0,
        asset_address=asset,
        judgment_window_start=override_ts,
    )
    conn.close()

    jw = state["judgment_window"]
    assert jw["window_start"] == override_ts
    assert jw["code_version"] == "OVERRIDE"
    assert state["stage_a"]["judgment_window_start"] == override_ts
    assert state["stage_a"]["judgment_code_version"] == "OVERRIDE"


def test_rh02bn_7_eip55_case_insensitivity_with_window(tmp_path):
    """7. 地址用 EIP-55 混合大小写传入仍能匹配小写存储的行（带 since 窗口）。"""
    from scripts.lp_rh_readiness_v1_readonly import coverage_for_asset
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE rh_market_states (
        asset_address TEXT, sample_time TEXT
    )""")
    stored_addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    mixed_addr = "0x52E65b17Fb6e5BA00ed806f37afcd2dAa50271Ca"
    upper_addr = "0X52E65B17FB6E5BA00ED806F37AFCD2DAA50271CA"

    conn.execute("INSERT INTO rh_market_states VALUES (?, ?)", (stored_addr, "2026-09-09T10:00:00Z"))
    conn.execute("INSERT INTO rh_market_states VALUES (?, ?)", (stored_addr, "2026-09-09T10:01:00Z"))
    conn.execute("INSERT INTO rh_market_states VALUES (?, ?)", (stored_addr, "2026-09-09T10:02:00Z"))

    cov_mixed = coverage_for_asset(conn, asset_address=mixed_addr, expected_interval_secs=60, since="2026-09-09T10:00:30Z")
    cov_upper = coverage_for_asset(conn, asset_address=upper_addr, expected_interval_secs=60, since="2026-09-09T10:00:30Z")
    cov_lower = coverage_for_asset(conn, asset_address=stored_addr, expected_interval_secs=60, since="2026-09-09T10:00:30Z")

    assert cov_mixed["has_data"] is True
    assert cov_mixed["analysis"]["total_samples"] == 2
    assert cov_upper["analysis"]["total_samples"] == 2
    assert cov_lower["analysis"]["total_samples"] == 2
    conn.close()


def test_rh02bn_8_reference_metrics_do_not_affect_blockers():
    """8. recent_72h_coverage_ratio 与 cumulative_coverage_ratio 都出现在返回 dict 里，且都不影响 blockers。"""
    jw_ok = {"window_start": "2026-09-08T00:00:00Z", "code_version": "test1234", "source": "git", "reason": "OK"}
    bad_cumulative = {"hours_covered": 100.0, "coverage_ratio": Decimal("0.50"), "actual_samples": 500, "expected_samples": 1000}
    bad_recent_72h = {"coverage_ratio": Decimal("0.20")}

    # Windowed is good (72h, >=0.99 coverage)
    res = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=True,
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
        judgment_window=jw_ok,
        cumulative=bad_cumulative,
        recent_72h=bad_recent_72h,
    )
    assert res["passed"] is True
    assert res["blockers"] == []
    assert res["cumulative_coverage_ratio"] == Decimal("0.50")
    assert res["recent_72h_coverage_ratio"] == Decimal("0.20")





def test_rh02bn_window_with_no_samples_fails_closed(tmp_path):
    """RH-02bn: samples all older than the window means no data under the current
    collector, which must fail closed rather than measure the old data.

    This pins behaviour that is currently implicit: coverage/hours come back None
    (never 0.0, never a stale figure from before the code changed) and Stage A
    blocks on OBSERVATION_WINDOW_UNAVAILABLE.
    """
    from scripts.lp_rh_readiness_v1_readonly import _build_state

    db_file = tmp_path / "no_window_data.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    for i in range(5):
        insert_row(conn, "rh_market_states", {
            "asset_address": addr, "chain_id": 4663, "session": "RTH",
            "health_flags_json": "[]", "sample_time": f"2026-09-08T00:0{i}:00Z",
            "reference_mid": "2400",
        })
    conn.commit()

    st = _build_state(conn, str(db_file), 15.0, asset_address=addr,
                      judgment_window_start="2026-09-09T16:05:41Z")
    a = st["stage_a"]
    assert a["actual_samples"] == 0
    assert a["hours_covered"] is None
    assert a["coverage_ratio"] is None
    assert a["passed"] is False
    assert "OBSERVATION_WINDOW_UNAVAILABLE" in a["blockers"]
    conn.close()


# --- RH-02bv: Attestation Status and Expiry Tests ---

def _setup_rh02bv_pool(conn, asset_address: str):
    insert_row(conn, "rh_pool_registry", {
        "chain_id": 4663,
        "protocol": "v3",
        "pool_key": asset_address,
        "pool_address": asset_address,
        "token0": "0x4200000000000000000000000000000000000006",
        "token1": asset_address,
        "fee": "3000",
        "tick_spacing": 60,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "discovered_at": "2026-09-08T00:00:00Z",
    })


def test_rh02bv_1_attested_same_block_and_null_expiry_passes(tmp_path):
    """1. 状态 ATTESTED_SAME_BLOCK、expires_at 为 NULL -> passed is True (不误伤生产)."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv1.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", None, "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr)
    assert res["passed"] is True
    assert res["has_contract_attestation"] is True
    assert res["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert res["attestation_expires_at"] is None
    assert res["attestation_checked_at"] is not None
    assert res["missing"] == []
    conn.close()


def test_rh02bv_2_status_failed_blocks(tmp_path):
    """2. 状态 FAILED -> passed is False，missing 里能看到实际状态值."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv2.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "FAILED", None, "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr)
    assert res["passed"] is False
    assert res["has_contract_attestation"] is True
    assert res["attestation_status"] == "FAILED"
    assert "attestation_status=FAILED" in res["missing"]
    conn.close()


def test_rh02bv_3_status_mismatch_blocks(tmp_path):
    """3. 状态 MISMATCH -> passed is False，missing 里能看到实际状态值."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv3.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "MISMATCH", None, "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr)
    assert res["passed"] is False
    assert res["has_contract_attestation"] is True
    assert res["attestation_status"] == "MISMATCH"
    assert "attestation_status=MISMATCH" in res["missing"]
    conn.close()


def test_rh02bv_4_status_null_or_empty_blocks(tmp_path):
    """4. 状态为 NULL/空串 -> missing 含 attestation_status_unknown."""
    import sqlite3
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv4.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "", None, "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res_empty = audit_pool_attestation(conn, asset_address=addr)
    assert res_empty["passed"] is False
    assert "attestation_status_unknown" in res_empty["missing"]
    conn.close()

    conn_mem = sqlite3.connect(":memory:")
    conn_mem.execute("CREATE TABLE rh_contract_attestations (address TEXT, attestation_status TEXT, expires_at TEXT, created_at TEXT)")
    conn_mem.execute("CREATE TABLE rh_pool_registry (pool_address TEXT, token0 TEXT, token1 TEXT, fee TEXT, tick_spacing INT)")
    conn_mem.execute("INSERT INTO rh_pool_registry VALUES (?, '0xt0', '0xt1', '3000', 60)", (addr,))
    conn_mem.execute("INSERT INTO rh_contract_attestations VALUES (?, NULL, NULL, '2026-09-08T00:00:00Z')", (addr,))
    res_null = audit_pool_attestation(conn_mem, asset_address=addr)
    assert res_null["passed"] is False
    assert "attestation_status_unknown" in res_null["missing"]
    conn_mem.close()


def test_rh02bv_5_expired_attestation_blocks(tmp_path):
    """5. expires_at 早于注入的 now -> missing 含 attestation_expired."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv5.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", "2026-09-08T12:00:00Z", "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr, now="2026-09-09T00:00:00Z")
    assert res["passed"] is False
    assert res["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert res["attestation_expires_at"] == "2026-09-08T12:00:00Z"
    assert "attestation_expired" in res["missing"]
    conn.close()


def test_rh02bv_6_future_expiry_passes(tmp_path):
    """6. expires_at 晚于注入的 now -> 不算过期，passed is True."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv6.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", "2026-09-12T00:00:00Z", "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr, now="2026-09-09T00:00:00Z")
    assert res["passed"] is True
    assert res["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert res["attestation_expires_at"] == "2026-09-12T00:00:00Z"
    assert "attestation_expired" not in res["missing"]
    conn.close()


def test_rh02bv_7_unparseable_expiry_fails_closed(tmp_path):
    """7. expires_at 是无法解析的字符串（如 'soon'）-> missing 含 attestation_expires_at_invalid (fail-close)."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv7.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", "soon", "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr, now="2026-09-09T00:00:00Z")
    assert res["passed"] is False
    assert "attestation_expires_at_invalid" in res["missing"]
    conn.close()


def test_rh02bv_8_latest_row_by_created_at_evaluated(tmp_path):
    """8. 同一地址两行、created_at 不同、旧行 ATTESTED_SAME_BLOCK 新行 FAILED -> 取新行，passed is False."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv8.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    _setup_rh02bv_pool(conn, addr)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", None, "2026-09-07T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr, "0x" + "bb" * 32, "v2", "FAILED", None, "2026-09-09T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr)
    assert res["passed"] is False
    assert res["attestation_status"] == "FAILED"
    assert "attestation_status=FAILED" in res["missing"]
    conn.close()


def test_rh02bv_9_eip55_address_case_insensitivity(tmp_path):
    """9. 地址用 EIP-55 混合大小写传入，仍能匹配小写存储的行."""
    from scripts.lp_rh_readiness_v1_readonly import audit_pool_attestation
    db_file = tmp_path / "bv9.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr_lower = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    addr_eip55 = "0x52E65b17fb6E5bA00ed806f37AfCD2Daa50271Ca"
    _setup_rh02bv_pool(conn, addr_lower)
    conn.execute(
        "INSERT INTO rh_contract_attestations "
        "(chain_id, address, block_hash, policy_version, attestation_status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (4663, addr_lower, "0x" + "aa" * 32, "v1", "ATTESTED_SAME_BLOCK", None, "2026-09-08T00:00:00Z"),
    )
    conn.commit()
    res = audit_pool_attestation(conn, asset_address=addr_eip55)
    assert res["passed"] is True
    assert res["has_contract_attestation"] is True
    assert res["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert res["missing"] == []
    conn.close()


# --- RH-02bw: Synthetic test evidence gate tests ---

def _get_live_repo_head(repo_root=REPO_ROOT) -> str:
    import subprocess
    proc = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_rh02bw_1_synthetic_evidence_missing(tmp_path):
    """1. 文件不存在 -> passed is None, reason SYNTHETIC_EVIDENCE_MISSING, blockers 含 STAGE_A_SYNTHETIC_TESTS_UNKNOWN."""
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_MISSING,
        STAGE_A_SYNTHETIC_TESTS_UNKNOWN,
        stage_a_status,
    )
    missing_file = tmp_path / "does_not_exist.json"
    res = audit_synthetic_tests(missing_file, repo_root=REPO_ROOT)
    assert res["passed"] is None
    assert res["reason"] == SYNTHETIC_EVIDENCE_MISSING
    assert res["code_version"] is None
    assert res["head_version"] is None
    assert res["evidence_path"] == str(missing_file)

    st_a = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=res["passed"],
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
    )
    assert st_a["passed"] is False
    assert STAGE_A_SYNTHETIC_TESTS_UNKNOWN in st_a["blockers"]


def test_rh02bw_2_synthetic_evidence_invalid_json(tmp_path):
    """2. 文件内容不是 JSON -> SYNTHETIC_EVIDENCE_INVALID, passed is None."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_INVALID,
    )
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("not json {{{", encoding="utf-8")
    res = audit_synthetic_tests(corrupt_file, repo_root=REPO_ROOT)
    assert res["passed"] is None
    assert res["reason"] == SYNTHETIC_EVIDENCE_INVALID

    # Also non-object JSON
    non_obj = tmp_path / "array.json"
    non_obj.write_text("[1, 2, 3]", encoding="utf-8")
    res_arr = audit_synthetic_tests(non_obj, repo_root=REPO_ROOT)
    assert res_arr["passed"] is None
    assert res_arr["reason"] == SYNTHETIC_EVIDENCE_INVALID

    # Also invalid generated_at
    bad_date = tmp_path / "bad_date.json"
    bad_date.write_text(json.dumps({
        "schema_version": 1, "code_version": "1234567890ab", "all_passed": True, "generated_at": "not-iso-date"
    }), encoding="utf-8")
    res_date = audit_synthetic_tests(bad_date, repo_root=REPO_ROOT)
    assert res_date["passed"] is None
    assert res_date["reason"] == SYNTHETIC_EVIDENCE_INVALID


def test_rh02bw_3_synthetic_evidence_schema_mismatch(tmp_path):
    """3. schema_version: 2 -> SYNTHETIC_EVIDENCE_SCHEMA_MISMATCH, passed is None."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_SCHEMA_MISMATCH,
    )
    head = _get_live_repo_head(REPO_ROOT)
    ev_file = tmp_path / "schema2.json"
    ev_file.write_text(json.dumps({
        "schema_version": 2,
        "code_version": head,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is None
    assert res["reason"] == SYNTHETIC_EVIDENCE_SCHEMA_MISMATCH


def test_rh02bw_4_synthetic_evidence_incomplete(tmp_path):
    """4. 缺 all_passed 键 / code_version 键 -> SYNTHETIC_EVIDENCE_INCOMPLETE, passed is None."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_INCOMPLETE,
    )
    head = _get_live_repo_head(REPO_ROOT)
    # Missing all_passed
    ev_file = tmp_path / "missing_all_passed.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": head,
        "working_tree_clean": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is None
    assert res["reason"] == SYNTHETIC_EVIDENCE_INCOMPLETE

    # Missing code_version
    ev_file2 = tmp_path / "missing_code_ver.json"
    ev_file2.write_text(json.dumps({
        "schema_version": 1,
        "all_passed": True,
        "working_tree_clean": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res2 = audit_synthetic_tests(ev_file2, repo_root=REPO_ROOT)
    assert res2["passed"] is None
    assert res2["reason"] == SYNTHETIC_EVIDENCE_INCOMPLETE


def test_rh02bw_5_synthetic_evidence_stale_code_version(tmp_path):
    """5. code_version 是一个明显不同的值 -> passed is False, SYNTHETIC_EVIDENCE_STALE_CODE_VERSION."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_STALE_CODE_VERSION,
        STAGE_A_SYNTHETIC_TESTS_FAILED,
        STAGE_A_SYNTHETIC_TESTS_UNKNOWN,
        stage_a_status,
    )
    head = _get_live_repo_head(REPO_ROOT)
    stale_sha = "0000deadbeef" if head != "0000deadbeef" else "1111deadbeef"
    ev_file = tmp_path / "stale.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": stale_sha,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is False
    assert res["reason"] == SYNTHETIC_EVIDENCE_STALE_CODE_VERSION
    assert res["code_version"] == stale_sha
    assert res["head_version"] == head

    st_a = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=res["passed"],
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
    )
    assert st_a["passed"] is False
    assert STAGE_A_SYNTHETIC_TESTS_FAILED in st_a["blockers"]
    assert STAGE_A_SYNTHETIC_TESTS_UNKNOWN not in st_a["blockers"]


def test_rh02bw_6_synthetic_evidence_dirty_working_tree(tmp_path):
    """6. code_version 正确但 working_tree_clean: false -> SYNTHETIC_EVIDENCE_DIRTY_WORKING_TREE, passed is False."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_DIRTY_WORKING_TREE,
    )
    head = _get_live_repo_head(REPO_ROOT)
    ev_file = tmp_path / "dirty.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": head,
        "working_tree_clean": False,
        "all_passed": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is False
    assert res["reason"] == SYNTHETIC_EVIDENCE_DIRTY_WORKING_TREE
    assert res["code_version"] == head
    assert res["head_version"] == head


def test_rh02bw_7_synthetic_evidence_tests_failed(tmp_path):
    """7. code_version 正确、clean、但 all_passed: false -> SYNTHETIC_TESTS_FAILED, passed is False."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_TESTS_FAILED,
        STAGE_A_SYNTHETIC_TESTS_FAILED,
        stage_a_status,
    )
    head = _get_live_repo_head(REPO_ROOT)
    ev_file = tmp_path / "failed.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": head,
        "working_tree_clean": True,
        "all_passed": False,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is False
    assert res["reason"] == SYNTHETIC_TESTS_FAILED

    st_a = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=res["passed"],
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
    )
    assert st_a["passed"] is False
    assert STAGE_A_SYNTHETIC_TESTS_FAILED in st_a["blockers"]


def test_rh02bw_8_synthetic_evidence_clean_pass(tmp_path):
    """8. 全部正确 -> passed is True, reason OK, Stage A blockers 不含任何 STAGE_A_SYNTHETIC_TESTS_*."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        stage_a_status,
        render_dashboard,
    )
    head = _get_live_repo_head(REPO_ROOT)
    ev_file = tmp_path / "ok.json"
    gen_time = "2026-09-10T03:05:00Z"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": head,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": gen_time,
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=REPO_ROOT)
    assert res["passed"] is True
    assert res["reason"] == "OK"
    assert res["code_version"] == head
    assert res["head_version"] == head
    assert res["generated_at"] == gen_time

    st_a = stage_a_status(
        first_sample="2026-09-08T00:00:00Z",
        last_sample="2026-09-11T00:00:00Z",
        expected_interval_secs=15,
        actual_samples=72 * 3600 // 15,
        synthetic_tests_passed=res["passed"],
        key_field_health={"passed": True},
        pool_attestation_status={"passed": True},
        budget=BUDGET_OK,
        invariant_violations=0,
        unknown_state_positions=0,
    )
    assert not any(b.startswith("STAGE_A_SYNTHETIC_TESTS_") for b in st_a["blockers"])
    assert st_a["passed"] is True

    # Also test dashboard rendering
    state = {
        "synthetic_evidence": res,
        "stage_a": st_a,
    }
    rendered = render_dashboard(state)
    assert f"- synthetic: OK (code_version={head}, generated_at={gen_time})" in rendered


def test_rh02bw_9_cli_synthetic_tests_passed_override(tmp_path):
    """9. CLI 显式传 synthetic_tests_passed=True 时，即使证据文件不存在也按 True 走（人工覆盖优先）."""
    from scripts.lp_rh_readiness_v1_readonly import (
        _build_state,
        render_dashboard,
        STAGE_A_SYNTHETIC_TESTS_UNKNOWN,
        STAGE_A_SYNTHETIC_TESTS_FAILED,
    )
    missing_file = str(tmp_path / "non_existent_ev.json")
    db_file = tmp_path / "test.db"
    conn = open_store(str(db_file))
    migrate(conn)
    addr = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
    insert_row(conn, "rh_market_states", _market_row(
        sample_time="2026-09-08T00:00:00Z", asset_address=addr))
    conn.commit()
    try:
        st = _build_state(
            conn, str(db_file), 15.0,
            asset_address=addr,
            synthetic_tests_passed=True,
            synthetic_evidence_path=missing_file,
            repo_root=str(REPO_ROOT),
        )
        assert st["stage_a"]["synthetic_tests_passed"] is True
        blockers = st["stage_a"]["blockers"]
        assert STAGE_A_SYNTHETIC_TESTS_UNKNOWN not in blockers
        assert STAGE_A_SYNTHETIC_TESTS_FAILED not in blockers
        assert st["synthetic_evidence"]["passed"] is True
        assert st["synthetic_evidence"]["reason"] == "CLI_OVERRIDE"

        rendered = render_dashboard(st)
        assert "- synthetic: OK (code_version=OVERRIDE" in rendered
    finally:
        conn.close()


def test_rh02bw_10_synthetic_evidence_head_unresolved(tmp_path):
    """10. 非 git 仓库无法解析 HEAD -> SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED, passed is None."""
    import json
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED,
    )
    empty_dir = tmp_path / "not_git"
    empty_dir.mkdir()
    ev_file = tmp_path / "ev.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": "1234567890ab",
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-10T03:05:00Z",
    }), encoding="utf-8")
    res = audit_synthetic_tests(ev_file, repo_root=empty_dir)
    assert res["passed"] is None
    assert res["reason"] == SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED
