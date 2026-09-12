import pytest

from scripts.lp_rh_graduation_evidence_v1 import build_verdict


def _make_passing_state():
    return {
        "stage_a": {"passed": True, "blockers": []},
        "stage_b": {"passed": True, "blockers": []},
        "live_gate": {"live_allowed": True, "blockers": []},
    }


def test_verdict_blocks_on_missing_full_test():
    """R2-07: Verify missing full_test prevents SHADOW_VALIDATED and yields OBSERVATION_INCOMPLETE."""
    res = build_verdict(
        state=_make_passing_state(),
        full_test=None,
        fault_injection={"report_present": True, "scenarios_passed": 6, "scenarios_total": 6},
        code_version="04e8a45",
        db_path="test.db",
        generated_at="2026-09-11T12:00:00Z",
        working_tree_clean=True,
    )
    assert res["verdict"] == "OBSERVATION_INCOMPLETE"
    assert "EVIDENCE_UNAVAILABLE:full_test" in res["verdict_reasons"]


def test_verdict_blocks_on_zero_fault_scenarios():
    """R2-07: Verify 0 fault injection scenarios prevents SHADOW_VALIDATED and yields OBSERVATION_INCOMPLETE."""
    res = build_verdict(
        state=_make_passing_state(),
        full_test={"total": 10, "passed": 10, "failed": 0, "exit_code": 0},
        fault_injection={"report_present": True, "scenarios_passed": 0, "scenarios_total": 0},
        code_version="04e8a45",
        db_path="test.db",
        generated_at="2026-09-11T12:00:00Z",
        working_tree_clean=True,
    )
    assert res["verdict"] == "OBSERVATION_INCOMPLETE"
    assert any("FAULT_INJECTION_EMPTY" in r for r in res["verdict_reasons"])


def test_verdict_blocks_on_dirty_working_tree():
    """R2-07: Verify dirty working tree prevents SHADOW_VALIDATED and yields OBSERVATION_INCOMPLETE."""
    res = build_verdict(
        state=_make_passing_state(),
        full_test={"total": 10, "passed": 10, "failed": 0, "exit_code": 0},
        fault_injection={"report_present": True, "scenarios_passed": 6, "scenarios_total": 6},
        code_version="04e8a45",
        db_path="test.db",
        generated_at="2026-09-11T12:00:00Z",
        working_tree_clean=False,
    )
    assert res["verdict"] == "OBSERVATION_INCOMPLETE"
    assert any("WORKING_TREE_DIRTY" in r for r in res["verdict_reasons"])


def test_verdict_skips_tests_yields_observation_not_validated():
    """R2-07: Verify skip_tests=True yields OBSERVATION_NOT_VALIDATED."""
    res = build_verdict(
        state=_make_passing_state(),
        full_test=None,
        fault_injection=None,
        code_version="04e8a45",
        db_path="test.db",
        generated_at="2026-09-11T12:00:00Z",
        working_tree_clean=True,
        skip_tests=True,
    )
    assert res["verdict"] == "OBSERVATION_NOT_VALIDATED"
    assert any("TESTS_SKIPPED" in r for r in res["verdict_reasons"])


def test_verdict_all_passing_yields_shadow_validated_control():
    """R2-07 Control: When all stages and tests pass with clean working tree, yields SHADOW_VALIDATED."""
    res = build_verdict(
        state=_make_passing_state(),
        full_test={"total": 10, "passed": 10, "failed": 0, "exit_code": 0},
        fault_injection={"report_present": True, "scenarios_passed": 6, "scenarios_total": 6},
        code_version="04e8a45",
        db_path="test.db",
        generated_at="2026-09-11T12:00:00Z",
        working_tree_clean=True,
        skip_tests=False,
    )
    assert res["verdict"] == "SHADOW_VALIDATED"
