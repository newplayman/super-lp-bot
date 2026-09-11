from __future__ import annotations

import pytest

from scripts.lp_rh_graduation_evidence_v1 import build_verdict


def test_test_failure_hard_blocks_verdict():
    """F08: Any failed test in full_test must hard-block verdict to OBSERVATION_INCOMPLETE."""
    state = {
        "stage_a": {"passed": True, "blockers": []},
        "stage_b": {"passed": True, "blockers": []},
        "live_gate": {"live_allowed": False, "blockers": ["CAPITAL_POLICY_NOT_APPROVED"]},
    }
    full_test = {"passed": 97, "failed": 3, "exit_code": 1}
    fault_injection = {"report_present": True, "scenarios_passed": 6, "scenarios_total": 6}

    verdict = build_verdict(
        state=state,
        full_test=full_test,
        fault_injection=fault_injection,
        code_version="c2fb020a1ad3",
        working_tree_clean=True,
        db_path=":memory:",
        generated_at="2026-09-11T12:00:00Z",
    )

    assert verdict["verdict"] == "OBSERVATION_INCOMPLETE"
    assert "manual_override_blocked" in verdict
    assert verdict["manual_override_blocked"] is False


def test_fault_injection_failure_hard_blocks_verdict():
    """F08: Fault injection failure (< 1.0 pass rate) must hard-block verdict to OBSERVATION_INCOMPLETE."""
    state = {
        "stage_a": {"passed": True, "blockers": []},
        "stage_b": {"passed": True, "blockers": []},
        "live_gate": {"live_allowed": False, "blockers": []},
    }
    full_test = {"passed": 100, "failed": 0, "exit_code": 0}
    fault_injection = {"report_present": True, "scenarios_passed": 5, "scenarios_total": 6}

    verdict = build_verdict(
        state=state,
        full_test=full_test,
        fault_injection=fault_injection,
        code_version="c2fb020a1ad3",
        working_tree_clean=True,
        db_path=":memory:",
        generated_at="2026-09-11T12:00:00Z",
    )

    assert verdict["verdict"] == "OBSERVATION_INCOMPLETE"


def test_clean_execution_yields_shadow_validated():
    """F08: All tests passing with clean stages yields SHADOW_VALIDATED."""
    state = {
        "stage_a": {"passed": True, "blockers": []},
        "stage_b": {"passed": True, "blockers": []},
        "live_gate": {"live_allowed": False, "blockers": []},
    }
    full_test = {"passed": 100, "failed": 0, "exit_code": 0}
    fault_injection = {"report_present": True, "scenarios_passed": 6, "scenarios_total": 6}

    verdict = build_verdict(
        state=state,
        full_test=full_test,
        fault_injection=fault_injection,
        code_version="c2fb020a1ad3",
        working_tree_clean=True,
        db_path=":memory:",
        generated_at="2026-09-11T12:00:00Z",
    )

    assert verdict["verdict"] == "SHADOW_VALIDATED"


def test_verdict_reverse_validation_defect_simulation():
    """Reverse validation: Old logic returned SHADOW_COMPLETE even when tests failed."""
    state = {
        "stage_a": {"passed": True, "blockers": []},
        "stage_b": {"passed": True, "blockers": []},
    }
    full_test = {"passed": 0, "failed": 3, "exit_code": 1}
    fault_injection = {"report_present": True, "scenarios_passed": 0, "scenarios_total": 6}

    # Defective logic: only checked stage_a and stage_b
    def defective_verdict(st, ft, fi):
        if st.get("stage_a", {}).get("passed") and st.get("stage_b", {}).get("passed"):
            return "SHADOW_COMPLETE"
        return "NOT_GRADUATED"

    # Defect yields SHADOW_COMPLETE despite failing tests!
    assert defective_verdict(state, full_test, fault_injection) == "SHADOW_COMPLETE"

    # Fixed logic hard-blocks to OBSERVATION_INCOMPLETE
    fixed_verdict = build_verdict(
        state=state,
        full_test=full_test,
        fault_injection=fault_injection,
        code_version="head",
        working_tree_clean=True,
        db_path=":memory:",
        generated_at="2026-09-11T12:00:00Z",
    )
    assert fixed_verdict["verdict"] == "OBSERVATION_INCOMPLETE"
    assert fixed_verdict["verdict"] != "SHADOW_COMPLETE"
