"""Tests for the Base 10U probe executor review re-run (20260602_150957).

The re-run uses fresh chain state and a new RUN_ID. The tests assert
the same review dimensions pass and detect the preflight WARN delta
(tick drift crossing 200-tick threshold).

The original test file (test_lp_base_10u_probe_executor_review_v1.py)
is keyed to the 20260602_144843 RUN_DIR; this re-run file is keyed
to the 20260602_150957 RUN_DIR.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_execution_script_review" / "20260602_150957"
SCRIPT = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v1.py"


def _read(rel: str) -> dict | None:
    p = RUN_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1",
    "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ----------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "re_run_note",
        "executor_script_reviewed",
        "static_security_pass", "mode_behavior_pass",
        "preflight_output_reviewed", "unsigned_package_reviewed",
        "approval_parser_reviewed", "execution_stubs_reviewed",
        "telemetry_schema_reviewed",
        "candidate_chain", "candidate_pool", "candidate_pair", "wallet",
        "notional_usd", "hold_window",
        "can_run_probe_now", "can_execute_with_current_script",
        "execution_implementation_allowed_next",
        "manual_approval_required_for_future_execution",
        "edge_proven", "actual_fee_ready", "token_id_available",
        "tiny_canary_allowed", "wallet_or_tx_touched",
        "recommended_next_stage", "review_dimensions_passed",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_status_pass() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["status"] == "PASS"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["can_execute_with_current_script"] is False
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["executor_will_run_this_round"] is False
    assert fv["approval_phrase_effective_this_round"] is False
    assert fv["manual_approval_required_for_future_execution"] is True


def test_execution_implementation_allowed_next_true() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["execution_implementation_allowed_next"] is True


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_wallet_address_is_public_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet"]
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    fv_str = json.dumps(fv)
    key_shape = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not key_shape, f"FINAL_VERDICT contains 64-hex (private-key shape): {key_shape.group(0) if key_shape else ''}"


# --- Review dimension checks ------------------------------------------

def test_static_security_pass() -> None:
    sr = _read("static_security_review.json")
    assert sr is not None
    assert sr["overall"] == "PASS"
    assert sr["any_dangerous_match"] is False
    assert sr["checks"]["private_key_loading"]["matches"] == 0
    assert sr["checks"]["eth_send_transaction"]["matches"] == 0
    assert sr["checks"]["approve_mint_etc_execution"]["matches"] == 0
    assert sr["checks"]["private_key_env_lookup"]["matches"] == 0
    assert sr["checks"]["mode_execute_rejected"]["result"] == "PASS"
    assert sr["checks"]["execution_stubs_disabled"]["result"] == "PASS"


def test_mode_behavior_pass() -> None:
    mb = _read("mode_behavior_review.json")
    assert mb is not None
    assert mb["summary"]["all_11_cases_pass"] is True
    assert mb["summary"]["execute_rejected_at_argparse"] is True
    assert mb["summary"]["execute_disabled_exits_nonzero"] is True
    assert mb["summary"]["approved_phrase_does_not_authorize_execution"] is True
    assert mb["summary"]["stop_condition_engine_correctly_detected_tick_drift"] is True


def test_preflight_output_reviewed_with_warn() -> None:
    po = _read("preflight_output_review.json")
    assert po is not None
    # The re-run observed WARN (vs previous PASS); this is correct behavior
    assert po["checks"]["preflight_status"]["value"] == "WARN"
    assert po["checks"]["stops_triggered_count"]["value"] == 1
    assert po["checks"]["current_tick_observed"]["triggered_stop"] == "stop_tick_moved_outside_planned_range_before_entry"
    assert po["checks"]["current_tick_observed"]["drift_ticks"] > 200
    assert po["checks"]["current_tick_observed"]["result"] == "WARN_TRIGGERED"
    assert po["useful_for_future_execution_stage"] is True
    assert po["checks"]["no_signer_constructed"]["result"] == "PASS"
    assert po["checks"]["no_tx_sent"]["result"] == "PASS"
    assert po["checks"]["no_approve"]["result"] == "PASS"
    assert po["checks"]["no_mint"]["result"] == "PASS"
    assert po["checks"]["no_send"]["result"] == "PASS"


def test_unsigned_package_reviewed() -> None:
    up = _read("unsigned_package_review.json")
    assert up is not None
    assert up["checks"]["unsigned_only"]["value"] is True
    assert up["checks"]["no_signature"]["value"] is True
    assert up["checks"]["no_send"]["value"] is True
    assert up["checks"]["execution_not_authorized"]["value"] is True
    assert up["checks"]["candidate_matches_freeze"]["result"] == "PASS"
    assert up["checks"]["wallet_address_correct"]["result"] == "PASS"
    assert up["checks"]["no_approvemax"]["result"] == "PASS"
    assert up["checks"]["no_full_executable_tx_bytes"]["result"] == "PASS"
    assert up["checks"]["no_private_data"]["result"] == "PASS"


def test_approval_parser_reviewed() -> None:
    ap = _read("approval_parser_review.json")
    assert ap is not None
    assert ap["summary"]["all_9_test_cases_pass"] is True
    assert ap["summary"]["valid_phrase_does_not_authorize_execution"] is True
    assert ap["checks"]["accepted_phrase_does_not_execute"]["result"] == "PASS"
    assert ap["checks"]["approval_phrase_effective_this_round"]["value"] is False


def test_execution_stubs_reviewed() -> None:
    es = _read("execution_stubs_review.json")
    assert es is not None
    assert es["stub_count"] == 7
    assert es["all_stubs_disabled"] is True
    assert es["all_stubs_raise_ExecutionDisabledInBuildStage"] is True
    assert es["no_stub_sends_tx"] is True
    assert es["no_stub_creates_signer"] is True
    assert es["no_stub_reads_key"] is True


def test_telemetry_schema_reviewed() -> None:
    ts = _read("telemetry_schema_review.json")
    assert ts is not None
    assert ts["checks"]["writes_only_to_reports_dir"]["result"] == "PASS"
    assert ts["checks"]["no_writes_to_production_db"]["result"] == "PASS"
    assert ts["checks"]["no_writes_to_shadow_tables"]["result"] == "PASS"
    assert ts["checks"]["no_writes_to_positions"]["result"] == "PASS"
    assert ts["checks"]["no_sensitive_data_leaked"]["result"] == "PASS"
    assert ts["schema_files_designed"]  # has the 5 file list


# --- Re-run delta check -----------------------------------------------

def test_re_run_note_present() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert "re_run" in fv.get("re_run_note", "").lower() or "re-verification" in fv.get("re_run_note", "").lower()


def test_previous_review_commit_linked() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert "596b411" in fv.get("previous_review_commit", "")


def test_delta_documented() -> None:
    fv = _read("FINAL_VERDICT.json")
    # The delta (preflight_status PASS -> WARN) must be documented
    deviations = fv.get("deviations_observed", {})
    assert "preflight_status_PASS_to_WARN" in deviations
    assert "stop_tick_moved_outside_planned_range_before_entry" in deviations["preflight_status_PASS_to_WARN"]


def test_tick_drift_correctly_above_threshold() -> None:
    po = _read("preflight_output_review.json")
    drift = po["checks"]["current_tick_observed"]["drift_ticks"]
    assert drift > 200, f"expected drift > 200 ticks, got {drift}"


# --- Review-stage does not modify the build script -----------------

def test_review_did_not_modify_executor_script() -> None:
    src = SCRIPT.read_text()
    assert "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1" in src
    assert "REVIEW STAGE MODIFICATION" not in src
    assert "ExecutionDisabledInBuildStage" in src


# --- Cross-doc consistency -------------------------------------------

def test_candidate_freeze_consistent_with_build_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    build_fv_path = (REPO_ROOT / "reports" / "lp_base_10u_probe_execution_script_build"
                     / "20260602_135824" / "FINAL_VERDICT.json")
    if not build_fv_path.is_file():
        pytest.skip("build stage FINAL_VERDICT not present")
    build_fv = json.loads(build_fv_path.read_text())
    assert fv["candidate_pool"] == build_fv["candidate_pool"]
    assert fv["notional_usd"] == build_fv["notional_usd"]
    assert fv["hold_window"] == build_fv["hold_window"]
    assert fv["wallet"] == build_fv["wallet"]


def test_input_audit_proceed() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["proceed_to_phase_C"] is True


# --- Subprocess sanity (defense-in-depth) -----------------------------

def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def test_subprocess_execute_rejected() -> None:
    r = _run("--mode", "execute")
    assert r.returncode != 0


def test_subprocess_execute_disabled_nonzero() -> None:
    r = _run("--mode", "execute-disabled")
    assert r.returncode != 0
    d = json.loads(r.stdout)
    assert d["execution_disabled_in_build_stage"] is True
