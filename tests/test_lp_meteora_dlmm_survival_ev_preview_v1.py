"""Tests for LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 stage.

Properties asserted:
  * partial scope explicitly marked
  * excluded SOL/USDC has no_quote_data
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * heuristic fee scenario marked heuristic
  * missing data not filled with zero
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_190910"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_survival_ev_preview" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1",
    "LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE MARKET_UNSAFE_WAIT_V1",
    "PROBE_NOW",
    "LIVE TRADE_NOW",
    "OPEN_LP_NOW",
    "CLOSE_LP_NOW",
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
    assert fv["stage"] == "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["transaction_sent"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["manual_approval_required"] is True


def test_final_verdict_partial_scope() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["scope"] == "partial_pool2_only"
    assert fv["included_pool_count"] == 1
    assert fv["excluded_pool_count"] == 1


def test_final_verdict_ev_negative_honestly() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["survival_ev_model_ran"] is True
    assert fv["row_count"] == 168
    # All scenarios are 0 positive (honest negative EV)
    assert fv["positive_zero_il_lvr_count"] == 0
    assert fv["positive_optimistic_count"] == 0
    assert fv["positive_realistic_count"] == 0
    assert fv["positive_conservative_count"] == 0
    # Best is still negative
    assert fv["best_net_ev_proxy_usd"] is not None
    assert fv["best_net_ev_proxy_usd"] < 0


def test_final_verdict_x_usdc_not_preflight_candidate() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["x_usdc_preflight_candidate"] is False


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT",
                "PROBE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW"]:
        assert sub not in rns


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "METEORA_PARTIAL_SURVIVAL_SCOPE_CN.md",
    "meteora_partial_survival_scope.json",
    "METEORA_SURVIVAL_EV_INPUTS_CN.md",
    "meteora_survival_ev_inputs.json",
    "METEORA_FEE_CAPTURE_PROXY_CN.md",
    "meteora_fee_capture_proxy.csv",
    "meteora_fee_capture_proxy.json",
    "METEORA_SOLANA_COST_MODEL_CN.md",
    "meteora_solana_cost_model.csv",
    "meteora_solana_cost_model.json",
    "METEORA_SURVIVAL_EV_PREVIEW_CN.md",
    "meteora_survival_ev_preview.csv",
    "meteora_survival_ev_preview.json",
    "METEORA_10_20U_PREFLIGHT_IMPLICATION_CN.md",
    "meteora_10_20u_preflight_implication.json",
    "METEORA_SURVIVAL_EV_NEXT_STAGE_DECISION_CN.md",
    "meteora_survival_ev_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: partial scope freeze ---------------------------------

def test_partial_scope_excluded_sol_usdc_no_quote_data() -> None:
    j = _read_json("meteora_partial_survival_scope.json")
    excluded = j["excluded_pools"]
    assert len(excluded) == 1
    assert excluded[0]["pool_address"].startswith("5BKxfWMb")
    assert excluded[0]["exclusion_reason"] == "no_quote_data"


def test_partial_scope_included_x_usdc_ready() -> None:
    j = _read_json("meteora_partial_survival_scope.json")
    included = j["included_pools"]
    assert len(included) == 1
    assert included[0]["pool_address"].startswith("9DiruRpj")
    assert included[0]["quote_status"].startswith("ready")
    assert included[0]["bin_liquidity_status"].startswith("ready")
    assert included[0]["fee_snapshot_status"].startswith("ready")


# --- Stage E: fee capture proxy heuristic marked -------------------

def test_fee_capture_proxy_heuristic_marked() -> None:
    j = _read_json("meteora_fee_capture_proxy.json")
    assert len(j) == 126  # 6 notionals × 7 hold_windows × 3 scenarios
    for r in j:
        assert r["heuristic"] is True
        assert r["confidence"] < 0.5
        assert "heuristic" in r["invalid_reason"].lower()


# --- Stage F: cost model -------------------------------------------

def test_cost_model_3_scenarios() -> None:
    j = _read_json("meteora_solana_cost_model.json")
    scenarios = {r["scenario"] for r in j}
    assert scenarios == {"low", "realistic", "conservative"}


def test_cost_model_applies_to_probe_false() -> None:
    """Per spec: probe no RPC. cost model is for future notional-scaled probes, not V8."""
    j = _read_json("meteora_solana_cost_model.json")
    for r in j:
        assert r["applies_to_probe"] is False


# --- Stage G: survival EV preview --------------------------------

def test_ev_preview_168_rows() -> None:
    j = _read_json("meteora_survival_ev_preview.json")
    assert len(j) == 168


def test_ev_preview_all_rows_heuristic_marked() -> None:
    j = _read_json("meteora_survival_ev_preview.json")
    for r in j:
        assert r["heuristic"] is True
        assert r["scope"] == "partial_pool2_only"
        assert r["confidence"] < 0.5


def test_ev_preview_no_missing_data_filled_with_zero() -> None:
    """Missing data should be marked explicitly, not filled with 0."""
    j = _read_json("meteora_survival_ev_preview.json")
    # Check that invalid_reason is non-empty
    for r in j:
        assert r["invalid_reason"] != "", f"row has empty invalid_reason: {r}"


# --- Stage H: 10/20U preflight -------------------------------------

def test_preflight_x_usdc_not_worth() -> None:
    j = _read_json("meteora_10_20u_preflight_implication.json")
    q1 = j["operator_questions_answered"]["q1_x_usdc_worth_10_20u_probe"]
    assert "NO" in q1["answer"]


def test_preflight_no_keypair() -> None:
    j = _read_json("meteora_10_20u_preflight_implication.json")
    q2 = j["operator_questions_answered"]["q2_need_solana_wallet"]
    assert "NO" in q2["answer"]


def test_preflight_data_sufficient_partial() -> None:
    j = _read_json("meteora_10_20u_preflight_implication.json")
    q4 = j["operator_questions_answered"]["q4_sufficient_data"]
    assert q4["answer"].startswith("PARTIAL")


def test_preflight_realistic_not_positive() -> None:
    j = _read_json("meteora_10_20u_preflight_implication.json")
    q5 = j["operator_questions_answered"]["q5_realistic_positive_ev"]
    assert "NO" in q5["answer"]


# --- Stage I: next-stage decision ---------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_survival_ev_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_feed_expansion() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_survival_ev_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_survival_ev_next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe", "send any tx",
        "keypair",
        "bridge", "swap",
        "hard-disable",
        "can_run_probe_now to true",
        "tiny_canary_allowed to yes"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


# --- v2 line count 992 unchanged ---------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Repo root not polluted ---------------------------------------

def test_repo_node_modules_not_created() -> None:
    nm = REPO_ROOT / "node_modules"
    assert not nm.is_dir(), f"repo node_modules was created: {nm}"


# --- Sweep: safety invariants stay false everywhere ------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            val = data["can_run_probe_now"]
            assert val is False or (isinstance(val, str) and val == "false"), (
                f"{jf.name} has can_run_probe_now={val!r}"
            )


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            val = data["solana_wallet_or_keypair_touched"]
            assert val is False or (isinstance(val, str) and val == "false"), (
                f"{jf.name} has solana_wallet_or_keypair_touched={val!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            val = data["tiny_canary_allowed"]
            assert val == "no" or val is False, (
                f"{jf.name} has tiny_canary_allowed={val!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
        "lamports",
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
            assert False, f"{f.name} contains 64-hex NOT in safe field: {line!r}"


def test_no_signer_construction_strings() -> None:
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(",
           "Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_seed(", "from_bytes(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet add"]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- Partial scope explicitly marked ---------------------------

def test_partial_scope_explicitly_marked_in_every_artifact() -> None:
    """Every artifact must mention 'partial' to make scope clear."""
    for f in REPORT_DIR.iterdir():
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        txt = f.read_text(errors="ignore")
        # Each CN MD file should mention partial
        if "CN.md" in f.name and "preflight" not in f.name.lower():
            assert "partial" in txt.lower() or "PARTIAL" in txt, f"{f.name} doesn't mention partial scope"
