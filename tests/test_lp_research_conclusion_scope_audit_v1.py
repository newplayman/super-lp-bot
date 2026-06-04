"""Tests for LP Research Conclusion Scope Audit (LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1).

These tests verify:
1. The final freeze + scope audit verdict fields are locked
2. The 6-stage R0-R5 reopen plan exists and is structured
3. The 6 model limitation dimensions are documented
4. Market regime bias is acknowledged
5. Scope addendum distinguishes what current conclusion can/cannot prove
6. Long-form CN docs contain the required scope language
7. README + LPBOT_RESEARCH_STATUS_CN.md reflect the scope addendum
8. No private key / keypair / signer / tx / bridge / live / paper / canary touchpoints
   are introduced by the scope audit reports

This is a read-only assertion test. It does NOT touch chain / wallet / signer / RPC.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_research_conclusion_scope_audit" / "20260604_060659"
FINAL_FREEZE_VERDICT = (
    REPO_ROOT / "reports" / "lp_research_final_freeze" / "20260604_051254" / "FINAL_VERDICT.json"
)
FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
SCOPE_JSON = REPORT_DIR / "current_conclusion_scope.json"
MODEL_JSON = REPORT_DIR / "model_limitation_audit.json"
REGIME_JSON = REPORT_DIR / "market_regime_bias_audit.json"
REOPEN_JSON = REPORT_DIR / "long_horizon_reopen_plan.json"
SCOPE_CN = REPORT_DIR / "CURRENT_CONCLUSION_SCOPE_CN.md"
MODEL_CN = REPORT_DIR / "MODEL_LIMITATION_AUDIT_CN.md"
REGIME_CN = REPORT_DIR / "MARKET_REGIME_BIAS_AUDIT_CN.md"
REOPEN_CN = REPORT_DIR / "LONG_HORIZON_REOPEN_PLAN_CN.md"
INPUT_EVIDENCE_CN = REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md"
ONEPAGE_CN = REPORT_DIR / "ONEPAGE_CN.md"
ARTIFACT_INDEX = REPORT_DIR / "ARTIFACT_INDEX.md"
STATUS_DOC = REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md"
README = REPO_ROOT / "README.md"

PROTOCOL_VERDICTS = [
    REPO_ROOT / "reports" / "lp_meteora_dlmm_targeted_top_pool_feed" / "20260604_021913" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_orca_whirlpool_readonly_connector" / "20260604_025414" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_raydium_clmm_readonly_connector" / "20260604_034503" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_raydium_cpmm_readonly_connector" / "20260604_040952" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_solana_stable_pool_research" / "20260604_044118" / "FINAL_VERDICT.json",
]


# ---------------------------------------------------------------------------
# 1. final freeze is intact + scope audit verdict
# ---------------------------------------------------------------------------

def test_final_freeze_verdict_exists_and_locked():
    assert FINAL_FREEZE_VERDICT.exists(), f"missing {FINAL_FREEZE_VERDICT}"
    verdict = json.loads(FINAL_FREEZE_VERDICT.read_text(encoding="utf-8"))
    assert verdict["research_freeze_complete"] is True
    assert verdict["overall_recommendation"] == "STOP_LP_RESEARCH_NOW"
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["edge_proven"] == "no"
    assert verdict["reopen_conditions_documented"] is True
    assert verdict["docs_updated"] is True
    assert verdict["wallet_or_tx_touched"] is False
    assert verdict["solana_wallet_or_keypair_touched"] is False
    assert verdict["transaction_sent"] is False
    assert verdict["send_hard_disable_still_active"] is True
    assert len(verdict["protocols_frozen"]) == 5


@pytest.mark.parametrize("path", PROTOCOL_VERDICTS, ids=lambda p: p.parent.name)
def test_each_protocol_verdict_rejects(path: Path):
    assert path.exists(), f"missing {path}"
    verdict = json.loads(path.read_text(encoding="utf-8"))
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["edge_proven"] == "no"
    assert verdict["positive_realistic_count"] == 0
    assert verdict["positive_optimistic_count"] == 0
    assert verdict["positive_conservative_count"] == 0
    assert verdict["transaction_sent"] is False
    assert verdict["wallet_or_tx_touched"] is False
    assert verdict["solana_wallet_or_keypair_touched"] is False
    # The 5th protocol explicitly recommended STOP_LP_RESEARCH_NOW; the others recommended a
    # follow-on connector, but the final freeze rollup locks all 5 as REJECT.
    assert "STOP_LP_RESEARCH_NOW" in verdict.get("allowed_next_stages", [])


def test_scope_audit_final_verdict_fields():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    verdict = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert verdict["stage"] == "LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1"
    assert verdict["status"] in {"PASS", "WARN"}
    assert verdict["current_probe_allowed"] is False
    assert verdict["global_lp_rejected"] is False
    assert verdict["current_model_rejects_auto_probe"] is True
    assert verdict["conclusion_scope"] == "current_data_current_model_short_window"
    assert verdict["long_term_lp_value_judged"] is False
    assert verdict["needs_longer_horizon_validation"] is True
    assert verdict["needs_actual_fee_accrual"] is True
    assert verdict["needs_market_regime_split"] is True
    assert verdict["market_downtrend_bias_acknowledged"] is True
    assert verdict["docs_updated"] is True
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["edge_proven"] == "no"
    assert "PAUSE" in verdict["recommended_next_stage"] or "STOP" in verdict["recommended_next_stage"]


# ---------------------------------------------------------------------------
# 2. input evidence audit passes
# ---------------------------------------------------------------------------

def test_input_evidence_audit_invariants():
    assert INPUT_EVIDENCE.exists()
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    inv = audit["required_invariants"]
    assert inv["final_freeze_exists"] is True
    assert inv["stop_lp_research_now_written"] is True
    assert inv["reopen_conditions_documented"] is True
    assert inv["can_run_probe_now"] is False
    assert inv["tiny_canary_allowed"] == "no"
    assert inv["all_5_protocols_realistic_positive_zero"] is True
    assert inv["all_5_protocols_optimistic_positive_zero"] is True
    assert inv["all_5_protocols_conservative_positive_zero"] is True
    assert inv["cumulative_cells_28560"] is True
    assert inv["no_transaction_sent"] is True
    assert inv["no_solana_wallet_or_keypair_touched"] is True
    assert inv["no_wallet_or_tx_touched"] is True
    assert inv["send_hard_disable_still_active"] is True
    assert inv["edge_proven"] == "no"
    assert audit["scope_audit_inputs_locked"] is True


# ---------------------------------------------------------------------------
# 3. scope fields
# ---------------------------------------------------------------------------

def test_scope_json_in_scope_and_out_of_scope():
    assert SCOPE_JSON.exists()
    scope = json.loads(SCOPE_JSON.read_text(encoding="utf-8"))
    assert scope["global_lp_rejected"] is False
    assert scope["long_term_lp_value_judged"] is False
    assert scope["conclusion_scope"] == "current_data_current_model_short_window"
    assert scope["current_probe_allowed"] is False
    assert len(scope["what_current_conclusion_can_prove"]) >= 5
    assert len(scope["what_current_conclusion_cannot_prove"]) >= 6
    assert len(scope["out_of_scope_domains"]) >= 5
    assert scope["freeze_lock"]["can_run_probe_now"] is False
    assert scope["freeze_lock"]["tiny_canary_allowed"] == "no"
    assert scope["freeze_lock"]["edge_proven"] == "no"


# ---------------------------------------------------------------------------
# 4. model limitation
# ---------------------------------------------------------------------------

def test_model_limitation_audit_fields():
    assert MODEL_JSON.exists()
    m = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    assert m["limitation_count"] == 6
    assert len(m["high_impact_limitations"]) == 4
    assert len(m["medium_impact_limitations"]) == 2
    for dim in [
        "data_window", "fee_data", "cost_data", "il_lvr", "pool_selection", "capital_scale"
    ]:
        assert dim in m["dimensions"]
    assert m["conclusion_confidence"]["current_model_current_data"] == "high"
    assert m["conclusion_confidence"]["long_horizon"] == "low"


# ---------------------------------------------------------------------------
# 5. regime bias
# ---------------------------------------------------------------------------

def test_regime_bias_audit_fields():
    assert REGIME_JSON.exists()
    r = json.loads(REGIME_JSON.read_text(encoding="utf-8"))
    assert r["bias_acknowledged"]["market_downtrend_bias_acknowledged"] is True
    assert r["user_question"]
    assert r["direct_answer"]
    regimes = {reg["regime"] for reg in r["future_regime_classification"]}
    assert {
        "uptrend", "downtrend", "sideways", "high_volume_sideways",
        "high_volatility_trend", "incentive_period", "low_volatility_stable"
    }.issubset(regimes)
    assert r["locked_conclusions"]["can_run_probe_now"] is False
    assert r["locked_conclusions"]["tiny_canary_allowed"] == "no"
    assert r["locked_conclusions"]["edge_proven"] == "no"
    assert r["locked_conclusions"]["long_term_lp_value_judged"] is False


# ---------------------------------------------------------------------------
# 6. long horizon reopen plan
# ---------------------------------------------------------------------------

def test_reopen_plan_phases_R0_through_R5():
    assert REOPEN_JSON.exists()
    p = json.loads(REOPEN_JSON.read_text(encoding="utf-8"))
    phase_ids = {phase["phase_id"] for phase in p["phases"]}
    expected = {
        "PHASE_R0_LONG_READONLY_DATA",
        "PHASE_R1_REAL_FEE_ACCRUAL_DESIGN",
        "PHASE_R2_MARKET_REGIME_SPLIT",
        "PHASE_R3_REOPEN_CANDIDATE_REVIEW",
        "PHASE_R4_10U_TOKENID_PROBE_PREFLIGHT",
        "PHASE_R5_MANUAL_PROBE_ONLY",
    }
    assert expected.issubset(phase_ids)
    assert p["stop_exit_at_each_phase"] is True
    assert p["skip_phases_forbidden"] is True
    assert "no new research runner" in " ".join(p["hard_prohibitions_all_phases"]).lower()
    assert "can_run_probe_now must stay false" in p["hard_prohibitions_all_phases"]


# ---------------------------------------------------------------------------
# 7. CN doc content
# ---------------------------------------------------------------------------

CN_DOCS = [
    SCOPE_CN, MODEL_CN, REGIME_CN, REOPEN_CN, INPUT_EVIDENCE_CN, ONEPAGE_CN, ARTIFACT_INDEX
]


@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_documents_exist(path: Path):
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path}"


def test_scope_cn_contains_key_phrases():
    text = SCOPE_CN.read_text(encoding="utf-8")
    for phrase in [
        "current_data_current_model_short_window",
        "global_lp_rejected",
        "long_term_lp_value_judged",
        "5/5 reject",
        "不能证明",
        "retail 10-20U 2000 USD",
        "不在结论范围",
        "conclusion_scope",
    ]:
        assert phrase in text, f"missing phrase {phrase!r} in scope CN doc"


def test_model_cn_contains_six_dimensions():
    text = MODEL_CN.read_text(encoding="utf-8")
    for dim in ["数据窗口", "fee", "成本", "IL / LVR", "池选择", "资金规模"]:
        assert dim in text, f"missing dimension {dim!r} in model CN doc"


def test_regime_cn_acknowledges_downtrend_bias():
    text = REGIME_CN.read_text(encoding="utf-8")
    assert "downtrend" in text.lower()
    assert "短窗口" in text
    assert "结论偏负" in text
    for regime in ["uptrend", "downtrend", "sideways", "high volume sideways",
                   "high volatility trend", "incentive period", "low volatility stable"]:
        assert regime in text, f"missing regime {regime!r}"


def test_reopen_cn_has_R0_through_R5():
    text = REOPEN_CN.read_text(encoding="utf-8")
    for ph in ["PHASE_R0", "PHASE_R1", "PHASE_R2", "PHASE_R3", "PHASE_R4", "PHASE_R5"]:
        assert ph in text, f"missing phase {ph!r}"


def test_onepage_cn_contains_essential_fields():
    text = ONEPAGE_CN.read_text(encoding="utf-8")
    for phrase in [
        "STOP_LP_RESEARCH_NOW",
        "global_lp_rejected",
        "long_term_lp_value_judged",
        "current_data_current_model_short_window",
        "needs_longer_horizon_validation",
        "needs_actual_fee_accrual",
        "needs_market_regime_split",
        "market_downtrend_bias_acknowledged",
        "can_run_probe_now",
        "tiny_canary_allowed",
        "edge_proven",
        "R0",
        "R5",
    ]:
        assert phrase in text, f"missing phrase {phrase!r} in one-pager"


# ---------------------------------------------------------------------------
# 8. docs updated
# ---------------------------------------------------------------------------

def test_status_doc_contains_scope_addendum():
    text = STATUS_DOC.read_text(encoding="utf-8")
    for phrase in [
        "LP Research Conclusion Scope Audit",
        "20260604_060659",
        "global_lp_rejected",
        "long_term_lp_value_judged",
        "current_data_current_model_short_window",
        "market_downtrend_bias_acknowledged",
        "needs_longer_horizon_validation",
        "needs_actual_fee_accrual",
        "needs_market_regime_split",
        "R0",
        "R5",
    ]:
        assert phrase in text, f"missing phrase {phrase!r} in status doc"


def test_readme_contains_scope_addendum():
    text = README.read_text(encoding="utf-8")
    for phrase in [
        "Conclusion Scope Audit",
        "20260604_060659",
        "global_lp_rejected = false",
        "long_term_lp_value_judged = false",
        "conclusion_scope = current_data_current_model_short_window",
        "market_downtrend_bias_acknowledged",
        "needs_longer_horizon_validation = true",
        "needs_actual_fee_accrual = true",
        "needs_market_regime_split = true",
        "R0-R5 6 阶段",
    ]:
        assert phrase in text, f"missing phrase {phrase!r} in README"


# ---------------------------------------------------------------------------
# 9. no trading / wallet / keypair / signer / tx / bridge touchpoints
# ---------------------------------------------------------------------------

BANNED_TOKENS_IN_REPORTS = [
    'method":"eth_sendrawtransaction',
    'method":"eth_sendtransaction',
    '"private_key"',
    '"mnemonic"',
    '"seed_phrase"',
    "Keypair.from_secret_key",
    "fromSecretKey(",
    "new Signer(",
    "signTransaction(",
    "signAndSendTransaction(",
    "wallet_adapter.connect",
    '"bridge":',
    '"swap"',
    '"open_position"',
    '"close_position"',
    '"collect_fee"',
    '"sendTransaction"',
]


@pytest.mark.parametrize("path", CN_DOCS + [FINAL_VERDICT, INPUT_EVIDENCE, SCOPE_JSON, MODEL_JSON, REGIME_JSON, REOPEN_JSON], ids=lambda p: p.name)
def test_no_banned_token_in_report(path: Path):
    text = path.read_text(encoding="utf-8").lower()
    for token in BANNED_TOKENS_IN_REPORTS:
        assert token.lower() not in text, f"banned token {token!r} found in {path.name}"


def test_no_touched_trading_path_in_final_verdict():
    verdict = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    safety = verdict["safety"]
    assert safety["touched_trading_path"] is False
    assert safety["touched_wallet_tx_bridge_live_paper"] is False
    assert safety["wallet_or_tx_touched"] is False
    assert safety["solana_wallet_or_keypair_touched"] is False
    assert safety["transaction_sent"] is False
    assert safety["send_hard_disable_still_active"] is True
    assert safety["no_protocol_re_run"] is True
    assert safety["no_heuristic_modification"] is True
    assert safety["no_paid_rpc_integration"] is True
    assert safety["no_new_research_runner_started"] is True


# ---------------------------------------------------------------------------
# 10. expected run_id consistency
# ---------------------------------------------------------------------------

def test_run_id_consistent_across_artifacts():
    expected = "20260604_060659"
    for path in [
        FINAL_VERDICT, INPUT_EVIDENCE, SCOPE_JSON, MODEL_JSON, REGIME_JSON, REOPEN_JSON,
        SCOPE_CN, MODEL_CN, REGIME_CN, REOPEN_CN, INPUT_EVIDENCE_CN, ONEPAGE_CN,
        ARTIFACT_INDEX, STATUS_DOC, README,
    ]:
        text = path.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {path.name}"
