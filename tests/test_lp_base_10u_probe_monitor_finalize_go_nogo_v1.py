"""Tests for LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1 stage.

Properties asserted:
  * no private key / signer / tx send anywhere
  * monitor finalize reads only files (no RPC, no send)
  * GO requires all gates; with NO-GO triggers, must NOT be GO
  * tick drift > threshold produces REFRESH_REQUIRED or NO_GO (never GO)
  * latest market_safe=False cannot GO
  * FINAL_VERDICT allowed next stages only (4 of them)
  * can_run_probe_now / execution_allowed_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_040018"
REPORT_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_monitor_finalize" / RUN_ID
SOURCE_MONITOR_DIR = (
    REPO_ROOT
    / "reports"
    / "lp_base_10u_probe_overnight_armed_runner"
    / "20260602_193517"
    / "monitor"
)
V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
MONITOR_V1 = REPO_ROOT / "scripts" / "lp_base_10u_probe_readiness_monitor_v1.py"

ALLOWED_NEXT_STAGES = {
    "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1",
    "LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION",  # missing _REVIEW_V1
    "WAIT_FOR_MONITOR_COMPLETION",  # not allowed in this stage
}


def _read_json(rel: str) -> dict | None:
    p = REPORT_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["stage"] == "LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["hard_disable_still_active"] is True
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True


def test_final_verdict_no_tx() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in [
        "this_stage_did_not_execute",
        "this_stage_did_not_send_any_tx",
        "this_stage_did_not_construct_signer",
        "this_stage_did_not_load_private_key",
        "this_stage_did_not_unseal_hard_disable",
        "this_stage_did_not_call_subprocess",
    ]:
        assert fv[k] is True, f"final_verdict {k} is not True: {fv[k]!r}"


def test_final_verdict_monitor_state() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["source_monitor_run_id"] == "20260602_193517"
    assert fv["monitor_finalized"] is True
    assert fv["monitor_was_active"] is False
    assert fv["monitor_stopped_by_this_task"] is False
    assert fv["source_monitor_stopped_reason"] == "max_hours_reached"
    assert fv["checkpoint_count"] == 47
    assert fv["success_checkpoints"] == 47
    assert fv["failed_checkpoints"] == 0


def test_final_verdict_latest_data() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["latest_market_safe"] is False
    assert fv["latest_tick"] == -201165
    assert fv["latest_tick_drift"] == -722
    assert fv["latest_tick_inside_range"] is True
    assert fv["latest_fresh_approval_required"] is True
    assert fv["latest_usdc_allowance_raw"] == 5000000
    assert fv["latest_usdc_balance_raw"] == 21774783


def test_final_verdict_go_nogo_no_go() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["go_nogo"] in ("GO", "NO_GO", "REFRESH_REQUIRED")
    # With 0/47 market_safe + drift -722, must be NO_GO or REFRESH_REQUIRED, not GO
    assert fv["go_nogo"] != "GO", (
        f"go_nogo=GO is forbidden given market_safe_count=0 and drift=-722. "
        f"primary_reason={fv.get('primary_reason')!r}"
    )
    assert fv["go_fail_count"] >= 1
    assert fv["no_go_trigger_count"] >= 1


def test_final_verdict_blocking_conditions_non_empty() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert isinstance(fv["blocking_conditions"], list)
    assert len(fv["blocking_conditions"]) >= 1


def test_final_verdict_recommended_next_stage_in_allowed_only() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES


def test_final_verdict_no_64hex_private_key_shape() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    # exclude known-safe uint256 RPC fields
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for m in pat.finditer(fv_str):
        hex_val = m.group(1)
        start = fv_str.rfind("\n", 0, m.start()) + 1
        end = fv_str.find("\n", m.end())
        if end < 0:
            end = len(fv_str)
        line = fv_str[start:end]
        if any(fld in line for fld in safe_uint256_fields):
            continue
        assert False, f"FINAL_VERDICT contains 64-hex NOT in safe uint256 field: {line!r}"


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "STAGE_A_WORKSPACE_SAFETY.md",
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "MONITOR_PROCESS_STATUS_CN.md", "monitor_process_status.json",
    "MONITOR_ARTIFACT_AUDIT_CN.md", "monitor_artifact_audit.json",
    "MONITOR_FINALIZE_RESULT_CN.md", "monitor_finalize_result.json",
    "BASE_10U_PROBE_GO_NOGO_REVIEW_CN.md", "base_10u_probe_go_nogo_review.json",
    "NEXT_STAGE_DECISION_CN.md", "next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- GO/NO-GO reasoning ----------------------------------------------

def test_go_nogo_review_no_go_with_drift_and_unsafe_market() -> None:
    """With 0/47 market_safe and -722 drift, GO must fail."""
    j = _read_json("base_10u_probe_go_nogo_review.json")
    assert j is not None
    assert j["go_nogo"] == "NO_GO"
    # blocking conditions must include at least market_safe and drift
    assert any("market_safe" in b or "tick" in b or "stop" in b
               for b in j["blocking_conditions"])


def test_go_nogo_review_go_conditions_have_3_fails() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    assert j["go_fail_count"] >= 3
    fails = j["go_conditions_evaluation"]
    assert fails["1_market_safe_ratio_ge_80pct"]["pass"] is False
    assert fails["2_no_hard_stop_in_latest"]["pass"] is False
    assert fails["4_drift_within_threshold_or_fresh_approval_satisfiable"]["pass"] is False


def test_go_nogo_review_gas_sane() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    fv = _read_json("FINAL_VERDICT.json")
    assert j["go_conditions_evaluation"]["7_gas_sane"]["pass"] is True
    assert fv["gas_sane_latest"] is True


def test_go_nogo_review_balance_sufficient() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    assert j["go_conditions_evaluation"]["8_eth_balance_sufficient"]["pass"] is True
    assert j["go_conditions_evaluation"]["9_usdc_balance_sufficient"]["pass"] is True


def test_go_nogo_review_allowance_plan_clear() -> None:
    """Allowance plan is clear (5->10 USDC via ApproveExact) but needs fresh approval."""
    j = _read_json("base_10u_probe_go_nogo_review.json")
    fv = _read_json("FINAL_VERDICT.json")
    assert j["go_conditions_evaluation"]["10_allowance_plan_clear"]["pass"] is True
    assert fv["allowance_plan_clear"] is True
    assert "ApproveExact" in fv["allowance_plan_actual_required"]


def test_go_nogo_review_no_signer_wallet_tx_touched() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    assert j["go_conditions_evaluation"]["12_no_signer_wallet_tx_touched"]["pass"] is True
    assert j["wallet_or_tx_touched"] is False


def test_go_nogo_review_hard_disable_still_active() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    fv = _read_json("FINAL_VERDICT.json")
    assert j["go_conditions_evaluation"]["13_hard_disable_still_active"]["pass"] is True
    assert fv["hard_disable_still_active"] is True
    assert fv["send_hard_disable_still_active"] is True


def test_go_nogo_review_drift_trajectory_worsening() -> None:
    j = _read_json("base_10u_probe_go_nogo_review.json")
    fv = _read_json("FINAL_VERDICT.json")
    traj = j["drift_trajectory"]
    assert traj["iter_47_drift"] < traj["iter_1_drift"]  # worsened
    assert fv["drift_trajectory_pattern"] == "monotonically_worsening_after_iter_18"


# --- next stage decision ---------------------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("next_stage_decision.json")
    fv = _read_json("FINAL_VERDICT.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES
    assert fv["recommended_next_stage"] == j["recommended_next_stage"]


def test_next_stage_decision_not_FINAL_OPERATOR_AUTHORIZATION_REVIEW() -> None:
    """With NO_GO verdict, must not pick FINAL_OPERATOR_AUTHORIZATION_REVIEW."""
    j = _read_json("next_stage_decision.json")
    fv = _read_json("FINAL_VERDICT.json")
    assert j["recommended_next_stage"] != "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1"
    assert fv["recommended_next_stage"] != "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1"


def test_next_stage_decision_safety_constraints() -> None:
    j = _read_json("next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe", "send any tx", "construct signer",
        "unseal v2 hard-disable", "accept one-shot execution phrase",
        "load private key"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


# --- monitor process status ------------------------------------------

def test_monitor_process_status_self_exited() -> None:
    j = _read_json("monitor_process_status.json")
    assert j["tmux_session_active"] is False
    assert j["runner_process_active"] is False
    assert j["monitor_was_active"] is False
    assert j["monitor_stopped_by_this_task"] is False
    assert j["monitor_auto_exited_reason"] == "max_hours_reached"


# --- Sweep: safety invariants stay false everywhere -----------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_wallet_or_tx_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "wallet_or_tx_touched" in data:
            assert data["wallet_or_tx_touched"] is False, (
                f"{jf.name} has wallet_or_tx_touched={data['wallet_or_tx_touched']!r}"
            )


def test_execution_allowed_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "execution_allowed_now" in data:
            assert data["execution_allowed_now"] is False, (
                f"{jf.name} has execution_allowed_now={data['execution_allowed_now']!r}"
            )


def test_hard_disable_still_active_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "hard_disable_still_active" in data:
            assert data["hard_disable_still_active"] is True, (
                f"{jf.name} has hard_disable_still_active={data['hard_disable_still_active']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            hex_val = m.group(1)
            start = txt.rfind("\n", 0, m.start()) + 1
            end = txt.find("\n", m.end())
            if end < 0:
                end = len(txt)
            line = txt[start:end]
            if any(fld in line for fld in safe_uint256_fields):
                continue
            assert False, (
                f"{f.name} contains 64-hex NOT in safe uint256 field. "
                f"line={line.strip()!r}"
            )


def test_no_signer_construction_strings() -> None:
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction("]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- monitor v1 still does not send, still rejects wrong params -----

def test_monitor_v1_rejects_wrong_wallet() -> None:
    proc = subprocess.run(
        [sys.executable, str(MONITOR_V1),
         "--run-id", RUN_ID,
         "--wallet", "0x0000000000000000000000000000000000000001",
         "--pool", "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
         "--notional", "10",
         "--hold", "15m",
         "--output-dir", "/tmp/__monitor_reject_test_go_nogo"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "REJECTED: wallet" in proc.stderr


def test_monitor_v1_no_signer_call() -> None:
    src = MONITOR_V1.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "sign_transaction(",
           "send_raw_transaction(", "send_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction"]
    for b in bad:
        assert b not in src, f"monitor_v1 contains suspicious token: {b!r}"


# --- v2 line count 992 unchanged ------------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- source monitor artifacts still readable (sanity) ---------------

def test_source_monitor_checkpoints_47_files() -> None:
    ckpts = sorted(SOURCE_MONITOR_DIR.glob("checkpoints/checkpoint_*.json"))
    assert len(ckpts) == 47


def test_source_monitor_finalize_summary_present() -> None:
    f = SOURCE_MONITOR_DIR / "final_monitor_summary.json"
    assert f.is_file()
    j = json.loads(f.read_text())
    assert j["total_checkpoints"] == 47
    assert j["market_safe_count"] == 0
    assert j["recommended_operator_action"] == "DO_NOT_EXECUTE_MARKET_UNSAFE"


def test_source_monitor_state_json_stopped_reason() -> None:
    f = SOURCE_MONITOR_DIR / "state.json"
    assert f.is_file()
    j = json.loads(f.read_text())
    assert j["stopped_reason"] == "max_hours_reached"
    assert j["degraded"] is False
    assert j["consecutive_rpc_failures"] == 0
