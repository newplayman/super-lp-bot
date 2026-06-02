"""Tests for the Base 10U probe EXECUTION AUTHORIZATION PACKAGE stage.

These tests check the authorization-package documents are present, structured,
and reflect the constraints we promised: approval phrase exact-only,
transaction-sequence whitelist, mint-receipt and fee-telemetry schemas
present, risk packet says EV is not proven, command draft is not run,
recommended next stage is one of three allowed values, can_run_probe_now
stays false.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_RUN_ID = "20260602_184806"
PKG_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_execution_authorization_package" / PKG_RUN_ID

ALLOWED_NEXT_STAGES = {
    "LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1",
    "LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "LP_BASE_10U_PROBE_EXECUTE_NOW",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_SEND",
    "LP_BASE_10U_PROBE_MINT_NOW",
    "EXECUTE_NOW",
}

EXPECTED_APPROVAL_PHRASE = (
    "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
    "wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 "
    "pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 "
    "notional=10 hold=15m"
)


def _read_json(rel: str) -> dict | None:
    p = PKG_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def _read_text(rel: str) -> str | None:
    p = PKG_DIR / rel
    if not p.is_file():
        return None
    return p.read_text()


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["status"] == "PASS"
    assert fv["stage"] == "LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1"


def test_final_verdict_all_readiness_true() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["authorization_package_ready"] is True
    assert fv["pre_execution_checklist_ready"] is True
    assert fv["authorized_transaction_sequence_ready"] is True
    assert fv["mint_receipt_tokenid_schema_ready"] is True
    assert fv["actual_fee_telemetry_schema_ready"] is True
    assert fv["human_approval_template_ready"] is True
    assert fv["risk_acceptance_packet_ready"] is True
    assert fv["next_execution_command_draft_ready"] is True


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["hard_disable_still_active"] is True
    assert fv["this_stage_did_not_execute"] is True
    assert fv["this_stage_did_not_send_any_tx"] is True
    assert fv["this_stage_did_not_construct_signer"] is True
    assert fv["this_stage_did_not_load_private_key"] is True
    assert fv["this_stage_did_not_call_subprocess_executor"] is True
    assert fv["this_stage_only_assembled_documentation"] is True
    assert fv["manual_approval_required_for_execution"] is True


def test_recommended_next_stage_in_allowed_only() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_recommended_next_stage_is_not_execution() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    bad_substrings = ["EXECUTE_NOW", "LIVE", "CANARY", "PAPER", "MINT_NOW", "SEND_NOW", "FIRST_EXECUTION"]
    for sub in bad_substrings:
        assert sub not in rns, f"recommended_next_stage {rns!r} contains forbidden substring {sub!r}"


def test_no_64hex_private_key_shape_in_verdict() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    m = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not m, f"FINAL_VERDICT contains 64-hex (private-key shape): {m.group(0) if m else ''}"


# --- All artifact files exist ----------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "BASE_10U_PROBE_AUTHORIZATION_SUMMARY_CN.md", "base_10u_probe_authorization_summary.json",
    "PRE_EXECUTION_FINAL_CHECKLIST_CN.md", "pre_execution_final_checklist.json",
    "AUTHORIZED_TRANSACTION_SEQUENCE_CN.md", "authorized_transaction_sequence.json",
    "MINT_RECEIPT_TOKENID_SCHEMA_CN.md", "mint_receipt_tokenid_schema.json",
    "ACTUAL_FEE_TELEMETRY_SCHEMA_CN.md", "actual_fee_telemetry_schema.json",
    "FINAL_HUMAN_APPROVAL_TEMPLATE_CN.md", "final_human_approval_template.json",
    "FINAL_RISK_ACCEPTANCE_PACKET_CN.md", "final_risk_acceptance_packet.json",
    "NEXT_EXECUTION_COMMAND_DRAFT_CN.md", "next_execution_command_draft.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = PKG_DIR / name
    assert p.is_file(), f"missing artifact: {p}"
    assert p.stat().st_size > 0


# --- Approval phrase exact -------------------------------------------

def test_approval_phrase_exact_in_template() -> None:
    tpl = _read_json("final_human_approval_template.json")
    assert tpl is not None
    assert tpl["future_approval_phrase"] == EXPECTED_APPROVAL_PHRASE


def test_approval_template_says_not_effective_this_round() -> None:
    tpl = _read_json("final_human_approval_template.json")
    assert tpl["this_stage_does_not_accept_phrase"] is True
    assert tpl["this_stage_does_not_validate_phrase"] is True
    assert tpl["this_stage_does_not_trigger_execution"] is True
    assert tpl["approval_phrase_effective_this_round"] is False


def test_approval_template_rejects_dangerous_examples() -> None:
    tpl = _read_json("final_human_approval_template.json")
    rejects = tpl["rejection_examples"]
    bad_phrases = [r["phrase"] for r in rejects]
    assert any("20U" in p for p in bad_phrases)
    assert any("30m" in p for p in bad_phrases)
    assert any("EXECUTE NOW" in p for p in bad_phrases)
    assert any("LIVE" in p for p in bad_phrases)


# --- Transaction sequence whitelist ----------------------------------

def test_authorized_tx_sequence_whitelist_contents() -> None:
    seq = _read_json("authorized_transaction_sequence.json")
    assert seq is not None
    names = [t["name"] for t in seq["allowed_transactions"]]
    assert "optional_usdc_approve_exact" in names
    assert "npm_mint" in names
    assert "npm_decrease_liquidity" in names
    assert "npm_collect" in names
    assert "optional_revoke_usdc_to_zero" in names


def test_authorized_tx_sequence_forbids_dangerous_actions() -> None:
    seq = _read_json("authorized_transaction_sequence.json")
    forbidden = seq["forbidden_transactions"]
    for key in ["ApproveMax", "multi_pool", "notional_over_10",
                "hold_over_15m_without_new_approval", "swap_back",
                "bridge", "auto_repeat", "live_loop", "canary", "paper",
                "any_other_wallet", "any_other_pool", "any_other_chain"]:
        assert key in forbidden, f"forbidden whitelist missing key: {key}"


def test_authorized_tx_sequence_addresses_allowance_skip() -> None:
    seq = _read_json("authorized_transaction_sequence.json")
    landing = seq["skip_approve_if_allowance_sufficient_landing"]
    assert landing["deviation_id"] == "skip_approve_if_allowance_sufficient_not_wired"
    assert landing["required_in_runner"] is True


# --- Mint receipt / tokenId schema -----------------------------------

def test_mint_receipt_schema_present() -> None:
    sc = _read_json("mint_receipt_tokenid_schema.json")
    assert sc is not None
    assert sc["deviation_landed"] == "mint_receipt_schema_not_defined"
    assert sc["this_stage_does_not_execute"] is True
    assert "erc721_transfer" in sc["expected_logs"]
    assert "increase_liquidity" in sc["expected_logs"]
    assert "FAIL_TOKEN_ID_NOT_FOUND" in sc["failure_handling"]


def test_mint_receipt_schema_telemetry_path() -> None:
    sc = _read_json("mint_receipt_tokenid_schema.json")
    art = sc["telemetry_artifact_schema"]
    assert "mint_receipt.json" in art["path"]
    for f in ["tx_hash", "status", "tokenId", "positions_observed", "validation_pass", "failure_id"]:
        assert f in art["required_fields"]


# --- Actual fee telemetry schema -------------------------------------

def test_actual_fee_telemetry_schema_present() -> None:
    sc = _read_json("actual_fee_telemetry_schema.json")
    assert sc is not None
    assert sc["deviation_landed"] == "feeGrowth_tokensOwed_telemetry_mode_not_implemented"
    points = [tp["point"] for tp in sc["time_points"]]
    for required in ["entry_fee_state", "hold_fee_state", "pre_exit_fee_state", "post_collect_fee_state"]:
        assert required in points
    for required in ["feeGrowthInside0LastX128", "feeGrowthInside1LastX128",
                     "tokensOwed0", "tokensOwed1"]:
        assert required in sc["required_reads"]["NFPM_positions_tuple"]


def test_actual_fee_telemetry_no_fabrication() -> None:
    sc = _read_json("actual_fee_telemetry_schema.json")
    forbidden = sc["forbidden"]
    assert any("pool-level feeGrowth as actual_fee_*" in f for f in forbidden)
    assert any("synthetic" in f or "estimated" in f for f in forbidden)


# --- Risk packet says EV not proven ----------------------------------

def test_risk_packet_says_ev_not_proven() -> None:
    rp = _read_json("final_risk_acceptance_packet.json")
    assert rp is not None
    assert rp["ev_not_proven_positive"]["edge_proven"] == "no"
    assert rp["ev_not_proven_positive"]["tiny_canary_allowed"] == "no"
    assert rp["success_does_not_depend_on_profit"] is True
    assert rp["worst_case_acceptance_required_usd"] >= 10


def test_risk_packet_has_eight_operator_confirmations() -> None:
    rp = _read_json("final_risk_acceptance_packet.json")
    assert len(rp["explicit_operator_confirmation_required"]) >= 8


# --- Pre-execution checklist ------------------------------------------

def test_pre_execution_checklist_has_27_gates() -> None:
    cl = _read_json("pre_execution_final_checklist.json")
    assert cl is not None
    total = sum(len(cl[k]) for k in cl if k.startswith("gates_"))
    assert total == cl["total_gates"]
    assert cl["total_gates"] >= 23  # spec listed ~23, we have 27


# --- Command draft not executed --------------------------------------

def test_command_draft_not_run() -> None:
    cd = _read_json("next_execution_command_draft.json")
    assert cd is not None
    assert cd["this_stage_does_not_execute"] is True
    assert cd["this_stage_does_not_call_subprocess"] is True
    assert cd["hard_disable_still_active"] is True
    assert cd["current_commit_does_not_release_hard_disable"] is True
    assert cd["expected_behavior_if_run_today"]["expected_returncode"] == 1
    assert "EXECUTION_SEND_DISABLED" in cd["expected_behavior_if_run_today"]["expected_stderr_contains"]


# --- Sweep: can_run_probe_now must remain false everywhere -----------

def test_can_run_probe_now_remains_false_everywhere() -> None:
    for jf in PKG_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_remains_no_everywhere() -> None:
    for jf in PKG_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_wallet_or_tx_touched_remains_false_everywhere() -> None:
    for jf in PKG_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "wallet_or_tx_touched" in data:
            assert data["wallet_or_tx_touched"] is False, (
                f"{jf.name} has wallet_or_tx_touched={data['wallet_or_tx_touched']!r}"
            )


def test_execution_allowed_now_remains_false_everywhere() -> None:
    for jf in PKG_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "execution_allowed_now" in data:
            assert data["execution_allowed_now"] is False, (
                f"{jf.name} has execution_allowed_now={data['execution_allowed_now']!r}"
            )
