"""Tests for the Base 10U probe OPERATOR EXECUTION REQUEST stage.

Properties asserted:
  * decision menu contains exactly A/B/C
  * no "direct execute" option in this stage
  * armed-build approval phrase is distinct from one-shot execution phrase
  * risk warning says EV is not proven
  * final verdict cannot set can_run_probe_now = true
  * recommended_next_stage defaults to WAIT_FOR_OPERATOR_DECISION
  * no wallet/private-key/signer/tx string sneaked into artifacts
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REQ_RUN_ID = "20260602_190720"
REQ_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_operator_execution_request" / REQ_RUN_ID

ALLOWED_NEXT_STAGES = {
    "WAIT_FOR_OPERATOR_DECISION",
    "LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1",
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
    "LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1",
}

ARMED_BUILD_PHRASE = (
    "APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER "
    "wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 "
    "pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 "
    "notional=10 hold=15m"
)
ONE_SHOT_PHRASE = (
    "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
    "wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 "
    "pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 "
    "notional=10 hold=15m"
)


def _read_json(rel: str) -> dict | None:
    p = REQ_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["status"] == "PASS"
    assert fv["stage"] == "LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1"


def test_final_verdict_readiness_true() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["operator_request_ready"] is True
    assert fv["decision_menu_ready"] is True
    assert fv["approval_phrase_ready"] is True
    assert fv["risk_warning_ready"] is True
    assert fv["next_stage_spec_ready"] is True


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["hard_disable_still_active"] is True
    assert fv["manual_approval_required"] is True
    assert fv["wallet_or_tx_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["this_stage_did_not_execute"] is True
    assert fv["this_stage_did_not_send_any_tx"] is True
    assert fv["this_stage_did_not_construct_signer"] is True
    assert fv["this_stage_did_not_load_private_key"] is True
    assert fv["this_stage_did_not_unseal_hard_disable"] is True
    assert fv["this_stage_did_not_call_executor_subprocess"] is True
    assert fv["this_stage_only_assembled_request_documentation"] is True
    assert fv["operator_choice_recorded_this_run"] is False


def test_recommended_next_stage_defaults_wait_for_operator_decision() -> None:
    """Without operator A/B/C, default must be WAIT_FOR_OPERATOR_DECISION."""
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] == "WAIT_FOR_OPERATOR_DECISION"


def test_recommended_next_stage_in_allowed_only() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_recommended_next_stage_is_not_execution() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    bad_substrings = ["EXECUTE_NOW", "LIVE", "CANARY", "PAPER",
                       "MINT_NOW", "SEND_NOW", "FIRST_EXECUTION_RUN"]
    for sub in bad_substrings:
        assert sub not in rns, f"recommended_next_stage {rns!r} contains forbidden substring {sub!r}"


def test_no_64hex_private_key_shape_in_verdict() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    m = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not m, f"FINAL_VERDICT contains 64-hex (private-key shape): {m.group(0) if m else ''}"


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "OPERATOR_EXECUTION_REQUEST_SUMMARY_CN.md", "operator_execution_request_summary.json",
    "OPERATOR_DECISION_MENU_CN.md", "operator_decision_menu.json",
    "FINAL_OPERATOR_APPROVAL_PHRASE_CN.md", "final_operator_approval_phrase.json",
    "FINAL_RISK_WARNING_FOR_OPERATOR_CN.md", "final_risk_warning_for_operator.json",
    "NEXT_STAGE_ARMED_RUNNER_BUILD_SPEC_CN.md", "next_stage_armed_runner_build_spec.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REQ_DIR / name
    assert p.is_file(), f"missing artifact: {p}"
    assert p.stat().st_size > 0


# --- Decision menu: A/B/C only, no direct-execute --------------------

def test_decision_menu_has_three_options() -> None:
    menu = _read_json("operator_decision_menu.json")
    assert menu is not None
    assert menu["total_options"] == 3
    keys = [o["key"] for o in menu["options"]]
    assert sorted(keys) == ["A", "B", "C"]


def test_decision_menu_no_direct_execute_option() -> None:
    menu = _read_json("operator_decision_menu.json")
    assert menu["direct_execute_option_present"] is False
    assert menu["direct_execute_option_explicitly_forbidden"] is True
    for opt in menu["options"]:
        assert opt["is_execution_authorization"] is False


def test_decision_menu_routes_to_legal_next_stages() -> None:
    menu = _read_json("operator_decision_menu.json")
    routes = {o["key"]: o["next_stage"] for o in menu["options"]}
    assert routes["A"] == "LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1"
    assert routes["B"] == "LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT"
    assert routes["C"] == "STOP_LP_RESEARCH_NOW"


def test_decision_menu_matrix_says_send_now_not_allowed() -> None:
    menu = _read_json("operator_decision_menu.json")
    assert menu["decision_matrix"]["want_to_send_tx_now"] == "NOT_ALLOWED_IN_THIS_STAGE"


# --- Approval phrases: build distinct from one-shot ------------------

def test_armed_build_phrase_exact() -> None:
    pdoc = _read_json("final_operator_approval_phrase.json")
    assert pdoc["phrases"]["armed_runner_build_phrase"]["value"] == ARMED_BUILD_PHRASE


def test_one_shot_phrase_exact() -> None:
    pdoc = _read_json("final_operator_approval_phrase.json")
    assert pdoc["phrases"]["one_shot_execution_phrase"]["value"] == ONE_SHOT_PHRASE


def test_armed_build_phrase_distinct_from_one_shot() -> None:
    pdoc = _read_json("final_operator_approval_phrase.json")
    armed = pdoc["phrases"]["armed_runner_build_phrase"]["value"]
    one = pdoc["phrases"]["one_shot_execution_phrase"]["value"]
    assert armed != one
    # The prefixes must differ to distinguish authorization scope
    armed_prefix = armed.split(" wallet=")[0]
    one_prefix = one.split(" wallet=")[0]
    assert armed_prefix != one_prefix
    assert armed_prefix == "APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER"
    assert one_prefix == "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT"


def test_this_stage_accepts_no_phrase() -> None:
    pdoc = _read_json("final_operator_approval_phrase.json")
    flags = pdoc["this_stage_accepts_no_phrase"]
    assert flags["approves_phrase_for_execution"] is False
    assert flags["approves_phrase_for_build"] is False
    assert flags["validates_any_phrase_input"] is False
    assert flags["writes_chain_state"] is False


def test_verdict_says_neither_phrase_effective_this_round() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["armed_build_phrase_effective_this_round"] is False
    assert fv["one_shot_phrase_effective_this_round"] is False


# --- Risk warning: EV not proven --------------------------------------

def test_risk_warning_says_ev_not_proven() -> None:
    rw = _read_json("final_risk_warning_for_operator.json")
    warnings = {w["id"]: w for w in rw["warnings"]}
    assert "ev_not_proven" in warnings
    assert "EV is NOT proven positive" in warnings["ev_not_proven"]["headline"]


def test_risk_warning_acknowledges_real_money() -> None:
    rw = _read_json("final_risk_warning_for_operator.json")
    warnings = {w["id"]: w for w in rw["warnings"]}
    rm = warnings.get("on_chain_real_money")
    assert rm is not None
    assert rm["not_testnet"] is True
    assert rm["not_simulation"] is True
    assert rm["irreversible"] is True


def test_risk_warning_default_when_no_choice_is_stop() -> None:
    rw = _read_json("final_risk_warning_for_operator.json")
    assert "C" in rw["default_when_no_choice"]


# --- Armed runner build spec is doc-only -----------------------------

def test_armed_runner_build_spec_is_doc_only() -> None:
    sp = _read_json("next_stage_armed_runner_build_spec.json")
    assert sp is not None
    assert sp["this_is_a_documentation_spec_only"] is True
    assert sp["this_stage_does_not_create_runner"] is True
    assert sp["this_stage_constraints"]["creates_armed_runner_file"] is False
    assert sp["this_stage_constraints"]["unseals_send_hard_disable"] is False


def test_armed_runner_build_spec_requires_separate_unseal_commit() -> None:
    sp = _read_json("next_stage_armed_runner_build_spec.json")
    cc = sp["commit_convention"]
    assert cc["minimum_commits"] >= 2
    assert cc["commit_1_unseal"]["message_prefix"] == "unseal:"
    assert cc["unseal_commit_independently_revertable"] is True


def test_armed_runner_build_spec_default_no_send() -> None:
    sp = _read_json("next_stage_armed_runner_build_spec.json")
    ids = [o["id"] for o in sp["objectives"]]
    assert "default_no_send" in ids
    must_not = sp["must_not_do"]
    assert any("send any tx" in m for m in must_not)
    assert any("dry-run-only" in m for m in must_not)


# --- Sweep: safety invariants stay false everywhere -----------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REQ_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REQ_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_wallet_or_tx_touched_false_everywhere() -> None:
    for jf in REQ_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "wallet_or_tx_touched" in data:
            assert data["wallet_or_tx_touched"] is False, (
                f"{jf.name} has wallet_or_tx_touched={data['wallet_or_tx_touched']!r}"
            )


def test_execution_allowed_now_false_everywhere() -> None:
    for jf in REQ_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "execution_allowed_now" in data:
            assert data["execution_allowed_now"] is False, (
                f"{jf.name} has execution_allowed_now={data['execution_allowed_now']!r}"
            )


def test_hard_disable_still_active_everywhere() -> None:
    for jf in REQ_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "hard_disable_still_active" in data:
            assert data["hard_disable_still_active"] is True, (
                f"{jf.name} has hard_disable_still_active={data['hard_disable_still_active']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    pat = re.compile(r"0x[0-9a-fA-F]{64}")
    for f in REQ_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        m = pat.search(txt)
        assert not m, f"{f.name} contains 64-hex (private-key shape): {m.group(0) if m else ''}"


def test_no_signer_construction_strings() -> None:
    """Sanity: artifacts should not contain call sites suggesting we constructed a signer."""
    bad_calls = ["Account.from_key(", "LocalAccount(", "from_mnemonic(", "load_keystore(",
                 "HTTPProvider(", "Web3(", "send_raw_transaction(", "sign_transaction(",
                 "eth.send_transaction("]
    for f in REQ_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for c in bad_calls:
            assert c not in txt, f"{f.name} contains suspicious call site: {c!r}"
