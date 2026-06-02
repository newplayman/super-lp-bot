"""Tests for the Base 10U probe FINAL EXECUTION REVIEW stage.

These tests assert on the FINAL_VERDICT.json + the live source of
scripts/lp_base_10u_probe_executor_v2.py (still hard-disabled this stage).

Properties asserted:
  * static review detects no forbidden functions
  * dynamic tick review requires fresh approval
  * approval gate is exact-phrase only
  * approveMax is forbidden
  * execute-guarded blocks send
  * telemetry only writes to local reports
  * no production / shadow DB writes
  * final verdict can only recommend one of 3 allowed next stages
  * can_run_probe_now remains false
  * recommended_next_stage cannot be a real execution stage
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
REVIEW_RUN_ID = "20260602_182402"
REVIEW_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_final_execution_review" / REVIEW_RUN_ID

ALLOWED_NEXT_STAGES = {
    "LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1",
    "LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}

# Any of these as recommended_next_stage would be a critical error in this
# review — the stage must NEVER recommend going directly to a real send.
FORBIDDEN_NEXT_STAGES = {
    "LP_BASE_10U_PROBE_EXECUTE_NOW",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_SEND",
    "LP_BASE_10U_PROBE_MINT_NOW",
    "EXECUTE_NOW",
}


def _read_json(rel: str) -> dict | None:
    p = REVIEW_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json shape -----------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["status"] == "PASS"
    assert fv["stage"] == "LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1"


def test_final_verdict_required_fields() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    required = {
        "status", "stage", "previous_stage", "previous_run_id",
        "executor_v2_reviewed", "static_security_pass",
        "dynamic_tick_range_pass", "approval_gate_pass",
        "approve_exact_review_pass", "mint_exit_collect_review_pass",
        "runtime_self_check_pass", "execute_guarded_send_blocked",
        "telemetry_review_pass", "final_execution_gate_review_pass",
        "candidate_chain", "candidate_pool", "candidate_pair",
        "wallet", "notional_usd", "hold_window",
        "can_run_probe_now", "can_execute_with_current_script",
        "execution_authorization_package_allowed_next",
        "manual_approval_required_for_execution",
        "edge_proven", "actual_fee_ready", "token_id_available",
        "wallet_or_tx_touched", "tiny_canary_allowed",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["can_execute_with_current_script"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["execute_guarded_send_blocked"] is True
    assert fv["manual_approval_required_for_execution"] is True
    assert fv["this_stage_did_not_execute"] is True
    assert fv["this_stage_did_not_send_any_tx"] is True
    assert fv["this_stage_did_not_construct_signer"] is True
    assert fv["this_stage_did_not_load_private_key"] is True


def test_final_verdict_all_review_phases_pass() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["static_security_pass"] is True
    assert fv["dynamic_tick_range_pass"] is True
    assert fv["approval_gate_pass"] is True
    assert fv["approve_exact_review_pass"] is True
    assert fv["mint_exit_collect_review_pass"] is True
    assert fv["runtime_self_check_pass"] is True
    assert fv["telemetry_review_pass"] is True
    assert fv["final_execution_gate_review_pass"] is True


def test_recommended_next_stage_in_allowed_set_only() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_recommended_next_stage_is_not_execution() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    # Even if a future review uses a different name, certain substrings
    # would indicate a real-send recommendation, which is forbidden.
    bad_substrings = ["EXECUTE_NOW", "LIVE", "CANARY", "PAPER", "MINT_NOW", "SEND_NOW"]
    for sub in bad_substrings:
        assert sub not in rns, f"recommended_next_stage {rns!r} contains forbidden substring {sub!r}"


def test_no_64hex_private_key_shape_in_verdict() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    m = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not m, f"FINAL_VERDICT contains 64-hex (private-key shape): {m.group(0) if m else ''}"


# --- Required review phase artifact files exist ------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "EXECUTOR_V2_STATIC_SECURITY_REVIEW_CN.md", "executor_v2_static_security_review.json",
    "DYNAMIC_TICK_RANGE_FINAL_REVIEW_CN.md", "dynamic_tick_range_final_review.json",
    "APPROVAL_GATE_FINAL_REVIEW_CN.md", "approval_gate_final_review.json",
    "APPROVE_EXACT_FINAL_REVIEW_CN.md", "approve_exact_final_review.json",
    "MINT_EXIT_COLLECT_FINAL_REVIEW_CN.md", "mint_exit_collect_final_review.json",
    "RUNTIME_SELF_CHECK_FINAL_REVIEW_CN.md", "runtime_self_check_final_review.json",
    "TELEMETRY_AND_ARTIFACT_FINAL_REVIEW_CN.md", "telemetry_and_artifact_final_review.json",
    "FINAL_EXECUTION_GATE_REVIEW_CN.md", "final_execution_gate_review.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_review_artifact_exists(name: str) -> None:
    p = REVIEW_DIR / name
    assert p.is_file(), f"missing artifact {p}"
    assert p.stat().st_size > 0


# --- Static review: forbidden functions in v2 source ------------------

def test_static_review_no_signer_construction_in_executable_code() -> None:
    """Scan source code (excluding docstrings/comments) for forbidden symbols."""
    src = SCRIPT.read_text()
    # Strip module docstring (first triple-quoted block) and python comments.
    # Simple sanity: ensure that the only mentions of the forbidden symbols
    # are in docstrings / string literals / the env-pattern self-check list.
    forbidden_callables = [
        "Account.from_key(",
        "LocalAccount(",
        "from_mnemonic(",
        "load_keyfile(",
        "load_keystore(",
        "Web3(",
        "HTTPProvider(",
        "send_raw_transaction(",
        "send_transaction(",
        "eth.send",
        "personal_sign(",
        "sign_transaction(",
    ]
    for sym in forbidden_callables:
        assert sym not in src, f"forbidden call site found: {sym!r}"


def test_static_review_execute_guarded_raises_class() -> None:
    src = SCRIPT.read_text()
    assert "class ExecutionSendDisabledInImplementationBuildStage" in src
    assert "raise ExecutionSendDisabledInImplementationBuildStage" in src


def test_static_review_approve_max_forbidden() -> None:
    src = SCRIPT.read_text()
    assert "UINT256_MAX // 2" in src
    assert "ApproveMax forbidden" in src


def test_static_review_default_no_send_and_dry_run() -> None:
    src = SCRIPT.read_text()
    # argparse defaults
    assert 'default=True, help="(default) dry-run only' in src
    assert 'default=True, help="(default) do not broadcast' in src


def test_static_review_dynamic_tick_range_required() -> None:
    src = SCRIPT.read_text()
    assert "def dynamic_tick_range_recompute" in src
    assert "TICK_DRIFT_FRESH_APPROVAL_THRESHOLD" in src
    assert "fresh_approval_required" in src


def test_dynamic_review_requires_fresh_approval_when_drift_exceeds() -> None:
    r = _read_json("dynamic_tick_range_final_review.json")
    assert r is not None
    obs = r["runtime_observation_this_run"]
    assert obs["abs_drift_ticks"] > obs["drift_threshold_ticks"]
    assert obs["fresh_approval_required"] is True
    assert r["verdict"]["dynamic_tick_range_pass"] is True


def test_approval_gate_exact_only() -> None:
    r = _read_json("approval_gate_final_review.json")
    assert r is not None
    assert r["checks"]["exact_phrase_only"]["result"] == "PASS"
    assert r["checks"]["wrong_wallet_rejected"]["result"] == "PASS"
    assert r["checks"]["wrong_pool_rejected"]["result"] == "PASS"
    assert r["checks"]["notional_20_rejected"]["result"] == "PASS"
    assert r["checks"]["hold_30m_rejected"]["result"] == "PASS"
    assert r["verdict"]["approval_gate_pass"] is True


def test_approve_max_forbidden_in_final_review() -> None:
    r = _read_json("approve_exact_final_review.json")
    assert r is not None
    assert r["checks"]["approvemax_forbidden"]["result"] == "PASS"
    assert r["checks"]["approve_exact_only"]["result"] == "PASS"
    assert r["verdict"]["approve_exact_review_pass"] is True


def test_telemetry_no_production_db() -> None:
    r = _read_json("telemetry_and_artifact_final_review.json")
    assert r is not None
    assert r["static_review"]["writes_only_to_reports_dir"]["result"] == "PASS"
    assert r["static_review"]["writes_to_production_db"]["observed"] is False
    assert r["static_review"]["writes_to_shadow_tables"]["observed"] is False
    assert r["static_review"]["writes_to_positions"]["observed"] is False
    assert r["verdict"]["telemetry_review_pass"] is True


# --- Subprocess sanity ------------------------------------------------

def _run(*args, env_extra=None):
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_subprocess_execute_guarded_still_blocks_send() -> None:
    r = _run(
        "--mode", "execute-guarded",
        "--run-id", "20260602_182402_test",
        "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
        "--notional", "10", "--hold", "15m",
        "--approval", "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m",
        "--dry-run-only", "--no-send",
        "--i-understand-this-sends-real-transactions",
    )
    assert r.returncode == 1
    assert "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE" in r.stderr


def test_subprocess_execute_guarded_blocks_without_i_understand_too() -> None:
    """Even without the second flag, execute-guarded must hard-block in this stage."""
    r = _run(
        "--mode", "execute-guarded",
        "--run-id", "20260602_182402_test",
        "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
        "--notional", "10", "--hold", "15m",
        "--approval", "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m",
        "--dry-run-only", "--no-send",
    )
    assert r.returncode == 1
    assert "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE" in r.stderr


def test_runtime_self_check_pass_in_review() -> None:
    r = _read_json("runtime_self_check_final_review.json")
    assert r is not None
    assert r["verdict"]["execute_guarded_blocked_send_returncode_1"] is True
    assert r["verdict"]["execute_guarded_blocked_send_with_i_understand"] is True
    assert r["verdict"]["any_tx_send_attempted"] is False
    assert r["verdict"]["runtime_self_check_pass"] is True


def test_final_execution_gate_review_pass() -> None:
    r = _read_json("final_execution_gate_review.json")
    assert r is not None
    assert r["final_execution_gate_review_pass"] is True
    assert r["go_no_go_conditions"]["all_pass"] is True
    assert r["decision"]["recommended_next_stage"] == "LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1"


def test_can_run_probe_now_remains_false_everywhere() -> None:
    """Sweep all review JSON artifacts to ensure can_run_probe_now is consistently false."""
    for jf in REVIEW_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_remains_no_everywhere() -> None:
    for jf in REVIEW_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_wallet_or_tx_touched_remains_false_everywhere() -> None:
    for jf in REVIEW_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "wallet_or_tx_touched" in data:
            assert data["wallet_or_tx_touched"] is False, (
                f"{jf.name} has wallet_or_tx_touched={data['wallet_or_tx_touched']!r}"
            )
