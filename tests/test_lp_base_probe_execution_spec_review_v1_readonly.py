"""Tests for the Base 10/20U probe execution SPEC review (read-only).

This stage is spec-only: no executor, no signer, no transaction. This suite
asserts that the spec artifacts are shape-correct and safety-locked so the
spec can never silently turn into execution.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "reports" / "lp_base_probe_execution_spec_review" / "20260602_133221"


def _read(rel: str) -> dict | None:
    p = RUN_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
    "LP_BASE_10_20U_PROBE_EXECUTION_SPEC_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ------------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "previous_stage", "previous_run_id",
        "candidate_chain", "candidate_pool", "candidate_pair", "candidate_fee_tier",
        "wallet", "recommended_first_notional_usd", "max_notional_usd",
        "recommended_first_hold_window",
        "execution_runbook_ready", "stop_conditions_ready",
        "telemetry_spec_ready", "execution_script_boundary_ready",
        "approval_template_ready", "risk_acceptance_ready",
        "execution_script_allowed_next", "executor_built_this_round",
        "executor_will_run_this_round",
        "can_run_probe_now", "edge_proven", "tiny_canary_allowed",
        "actual_fee_ready", "token_id_available",
        "manual_approval_required_for_execution",
        "approval_phrase_effective_this_round", "approval_phrase_template",
        "approval_phrase_regex",
        "wallet_or_tx_touched",
        "recommended_next_stage", "spec_phase_artifact_counts",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_status_pass() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["status"] == "PASS"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["wallet_or_tx_touched"] is False
    assert fv["can_run_probe_now"] is False
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["executor_built_this_round"] is False
    assert fv["executor_will_run_this_round"] is False
    assert fv["approval_phrase_effective_this_round"] is False
    assert fv["manual_approval_required_for_execution"] is True


def test_executor_not_built_and_will_not_run() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["executor_built_this_round"] is False
    assert fv["executor_will_run_this_round"] is False


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_recommended_next_stage_is_build_not_execute() -> None:
    fv = _read("FINAL_VERDICT.json")
    bad = {"LP_BASE_10U_LP_PROBE_EXECUTE", "probe_execution",
           "canary", "live", "paper", "GO", "SHIP_IT",
           "LP_BASE_10U_LP_PROBE_EXECUTE_NOW"}
    assert fv["recommended_next_stage"] not in bad


def test_wallet_address_is_public_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet"]
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    fv_str = json.dumps(fv)
    for token in ["private_key", "privateKey", "mnemonic", "seed", "keystore"]:
        assert token.lower() not in fv_str.lower(), f"FINAL_VERDICT must not mention {token}"


# --- Candidate freeze ---------------------------------------------------

def test_candidate_freeze_consistent_with_final_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    cf = _read("base_probe_execution_candidate_freeze.json")
    assert cf is not None
    assert cf["frozen"] is True
    assert cf["pool"]["address"] == fv["candidate_pool"]
    assert cf["pool"]["fee_tier"] == fv["candidate_fee_tier"]
    assert cf["wallet"]["address"] == fv["wallet"]
    assert cf["notional"]["recommended_first_notional_usd"] == fv["recommended_first_notional_usd"]
    assert cf["execution_authorization"]["authorized_this_round"] is False


# --- Execution runbook --------------------------------------------------

def test_runbook_has_5_steps() -> None:
    rb = _read("base_probe_execution_runbook.json")
    assert rb is not None
    steps = rb
    for k in ("step_0_pre_execution_sanity", "step_1_approve_exact_only_if_needed",
              "step_2_mint_or_increaseLiquidity", "step_3_hold_monitoring",
              "step_4_exit_decrease_collect", "step_5_post_exit_cleanup"):
        assert k in steps, f"missing runbook step {k}"


def test_runbook_no_swap_back() -> None:
    rb = _read("base_probe_execution_runbook.json")
    assert rb is not None
    assert rb["no_swap_back"] is True
    assert rb["no_auto_repeat"] is True
    assert rb["no_multi_pool"] is True
    assert rb["no_bridge"] is True


def test_runbook_uses_approve_exact_not_approve_max() -> None:
    rb = _read("base_probe_execution_runbook.json")
    s1 = rb["step_1_approve_exact_only_if_needed"]
    # Find the action that BUILDS the approve tx (not the compute-amount action)
    found_invariant = False
    for action in s1["actions"]:
        a = action.get("action", "").lower()
        if "build" in a and "approve" in a and "erc20" in a:
            invariant = action.get("invariant", "")
            assert "uint256.max" in invariant or "ApproveExact" in invariant
            found_invariant = True
            break
    assert found_invariant, "no action that builds ERC20.approve with invariant found"


# --- Stop conditions ----------------------------------------------------

def test_stop_conditions_have_handling_for_each() -> None:
    sc = _read("base_probe_stop_conditions.json")
    assert sc is not None
    # stop_count is a doc-declared number; check the list size matches the actual list
    assert sc["stop_count"] == len(sc["stop_conditions"]), (
        f"declared stop_count={sc['stop_count']} but list has {len(sc['stop_conditions'])} entries"
    )
    for cond in sc["stop_conditions"]:
        assert "id" in cond
        assert "condition" in cond
        assert "handling" in cond
        assert cond["handling"] in {"abort_before_entry", "exit_immediately", "manual_intervention_required"}


def test_no_auto_retry_policy() -> None:
    sc = _read("base_probe_stop_conditions.json")
    assert sc["no_auto_retry"] is True


# --- Telemetry spec -----------------------------------------------------

def test_telemetry_spec_has_6_schemas() -> None:
    ts = _read("base_probe_actual_telemetry_spec.json")
    assert ts is not None
    schemas = [
        "entry_telemetry_schema",
        "hold_telemetry_schema",
        "fee_trace_telemetry_schema",
        "exit_telemetry_schema",
        "post_exit_telemetry_schema",
        "actual_pnl_telemetry_schema",
    ]
    for s in schemas:
        assert s in ts, f"missing telemetry schema {s}"


def test_telemetry_no_production_writes() -> None:
    ts = _read("base_probe_actual_telemetry_spec.json")
    assert ts["wrote_to_production_tables"] is False
    assert "not_in_production_tables" in ts["summary_persistence"]


# --- Execution script boundary -----------------------------------------

def test_script_boundary_has_allowed_and_forbidden() -> None:
    esb = _read("base_probe_execution_script_boundary.json")
    assert esb is not None
    assert len(esb["boundary_summary"]["allowed"]) >= 5
    assert len(esb["boundary_summary"]["forbidden"]) >= 10


def test_script_boundary_approval_phrase_non_effective() -> None:
    esb = _read("base_probe_execution_script_boundary.json")
    assert esb["future_approval_phrase_template"]["this_round_non_effective"] is True
    assert esb["future_approval_phrase_template"]["this_round_executor_must_reject_even_if_typed"] is True


def test_script_boundary_regex_works() -> None:
    esb = _read("base_probe_execution_script_boundary.json")
    rgx = re.compile(esb["future_approval_phrase_template"]["regex"])
    wallet = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
    pool = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
    valid = f"APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet={wallet} pool={pool} notional=10 hold=15m"
    assert rgx.match(valid)
    # Invalid: notional 20
    bad = f"APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet={wallet} pool={pool} notional=20 hold=15m"
    assert not rgx.match(bad)
    # Invalid: hold 30m
    bad = f"APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet={wallet} pool={pool} notional=10 hold=30m"
    assert not rgx.match(bad)
    # Invalid: placeholder wallet
    bad = f"APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xUSER_PROVIDED_WALLET_ADDRESS pool={pool} notional=10 hold=15m"
    assert not rgx.match(bad)
    # Invalid: bad prefix
    bad = f"APPROVE_BASE_10U_LP_PROBE_EXECUTE wallet={wallet} pool={pool} notional=10 hold=15m"
    assert not rgx.match(bad)


# --- Approval template --------------------------------------------------

def test_approval_template_phrase_matches_boundary() -> None:
    esb = _read("base_probe_execution_script_boundary.json")
    at = _read("base_probe_execution_approval_template.json")
    assert esb["future_approval_phrase_template"]["phrase"] == at["approval_phrase_template"]["phrase"]
    assert esb["future_approval_phrase_template"]["regex"] == at["approval_phrase_template"]["regex"]


def test_approval_template_20u_rejected() -> None:
    at = _read("base_probe_execution_approval_template.json")
    assert at["first_round_recommendation"]["recommended_notional"] == 10
    assert at["first_round_recommendation"]["recommended_hold_window"] == "15m"
    assert at["this_round_status"]["effective_this_round"] is False
    # 20U and 30m should be in rejected list
    rejected = at["rejected_alternative_phrases"]
    assert any("notional=20" in p for p in rejected)
    assert any("hold=30m" in p for p in rejected)


# --- Risk acceptance ----------------------------------------------------

def test_risk_acceptance_ev_not_positive() -> None:
    ra = _read("base_probe_risk_acceptance.json")
    assert ra["realistic_ev_is_not_positive"] is True
    assert ra["this_is_not_a_profit_strategy_validation"] is True
    # Should mention not a profit strategy
    text = json.dumps(ra).lower()
    assert "not" in text and "profit" in text
    assert "negative" in text


def test_risk_acceptance_states_loss_potential() -> None:
    ra = _read("base_probe_risk_acceptance.json")
    lp = ra["loss_potential"]
    assert "expected_realistic_loss_usd" in lp
    assert "worst_case_loss_usd" in lp


# --- Input audit --------------------------------------------------------

def test_input_audit_proceed() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["proceed_to_phase_C"] is True
    assert ia["this_round_scope"] == "base_10u_lp_probe_execution_spec_review_only"
    must_not = "\n".join(ia["this_round_must_not"]).lower()
    for needle in ["private key", "signer", "eth_sendtransaction", "eth_sendrawtransaction",
                   "approve", "mint", "live", "canary", "paper", "auto-bridge", "auto-swap"]:
        assert needle in must_not, f"input_audit must_not missing: {needle!r}"


def test_input_audit_gates_aligned() -> None:
    ia = _read("input_evidence_audit.json")
    g = ia["gates_from_previous_stage"]
    assert g["status"] == "PASS"
    assert g["can_run_probe_now"] is False
    assert g["wallet_loaded"] is False
    assert g["signer_created"] is False
    assert g["transaction_sent"] is False
    assert g["recommended_next_stage_per_upstream"] == "LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1"


# --- No new scripts this round -----------------------------------------

def test_no_new_executable_scripts_in_this_stage() -> None:
    """This stage is spec-only; no scripts/ runner should be added."""
    bad = list((REPO_ROOT / "scripts").glob("lp_base_probe_execution_spec_review*"))
    bad += list((REPO_ROOT / "scripts").glob("lp_base_execution_spec_*"))
    bad += list((REPO_ROOT / "scripts").glob("lp_base_10u_lp_probe*"))
    assert not bad, f"this stage should not add scripts; found: {bad}"


# --- Cross-doc consistency ---------------------------------------------

def test_previous_stage_links_to_dry_run_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["previous_stage"] == "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1"
    assert fv["previous_run_id"] == "20260602_112400"


def test_all_spec_flags_in_final_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    flags = ["execution_runbook_ready", "stop_conditions_ready",
             "telemetry_spec_ready", "execution_script_boundary_ready",
             "approval_template_ready", "risk_acceptance_ready"]
    for f in flags:
        assert fv[f] is True, f"{f} must be True for next-stage build to be allowed"


def test_execution_script_allowed_next_only_when_all_specs_ready() -> None:
    fv = _read("FINAL_VERDICT.json")
    if fv["execution_script_allowed_next"]:
        for f in ["execution_runbook_ready", "stop_conditions_ready",
                  "telemetry_spec_ready", "execution_script_boundary_ready",
                  "approval_template_ready", "risk_acceptance_ready"]:
            assert fv[f] is True
