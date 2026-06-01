from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_bsc_overnight_realdata_pipeline_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_bsc_overnight_realdata_pipeline_v1_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_script_is_readonly_and_bsc_only() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction(",
        "eth_sendtransaction(",
        "signtransaction(",
        "--canary-mint",
        "private_key =",
        "mnemonic =",
        "approve(",
        "mint(",
        "burn(",
        "collect(",
    ]
    for token in banned:
        assert token not in text
    assert "lp_bsc_pancakeswap_v3_overnight_realdata_pipeline_v1" in text
    assert "tiny_canary_allowed" in text


def test_input_artifact_audit_and_selected_pool_set() -> None:
    rows, summary = module.input_artifact_audit()
    assert summary["quoter_staticcall_success_count"] == 80
    assert summary["fallback_math_used_count"] == 0
    assert summary["bsc_quoter_staticcall_fixed"] is True
    assert summary["can_run_overnight_readonly"] is True
    assert summary["overnight_readonly"] is True
    assert summary["no_probe_no_canary_no_live"] is True
    assert not summary["missing_input_list"]
    assert len(rows) >= 10

    selected_rows = module.read_selected_pool_rows()
    pools, unique_rows = module.freeze_selected_pool_set(selected_rows)
    assert len(selected_rows) == 8
    assert len(pools) == 8
    assert len(unique_rows) == 8
    assert {row["selected_for_tick"] for row in pools} == {"yes"}
    assert {row["selected_for_economics"] for row in pools} == {"yes"}


def test_expected_artifact_names_are_present() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    required = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "INPUT_ARTIFACT_AUDIT_CN.json",
        "BSC_RPC_CONTRACT_READINESS_CN.md",
        "BSC_RPC_CONTRACT_READINESS_CN.json",
        "BSC_SELECTED_POOL_SET_CN.md",
        "BSC_SELECTED_POOL_SET_CN.csv",
        "BSC_SELECTED_POOL_SET_CN.json",
        "BSC_TICK_LIQUIDITY_IMPLEMENTATION_CN.md",
        "BSC_TICK_LIQUIDITY_RESULTS_CN.md",
        "BSC_TICK_LIQUIDITY_RESULTS_CN.csv",
        "BSC_TICK_LIQUIDITY_RESULTS_CN.json",
        "BSC_REAL_COST_MODEL_RESULTS_CN.md",
        "BSC_REAL_COST_MODEL_RESULTS_CN.csv",
        "BSC_REAL_COST_MODEL_RESULTS_CN.json",
        "BSC_FEE_VELOCITY_RESULTS_CN.md",
        "BSC_FEE_VELOCITY_RESULTS_CN.csv",
        "BSC_FEE_VELOCITY_RESULTS_CN.json",
        "BSC_REALDATA_ECONOMICS_PREVIEW_CN.md",
        "BSC_REALDATA_ECONOMICS_PREVIEW_CN.csv",
        "BSC_REALDATA_ECONOMICS_PREVIEW_CN.json",
        "BSC_CANDIDATE_REVIEW_MATRIX_CN.md",
        "BSC_CANDIDATE_REVIEW_MATRIX_CN.csv",
        "BSC_CANDIDATE_REVIEW_MATRIX_CN.json",
        "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.md",
        "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.json",
        "BSC_OVERNIGHT_SAFETY_AUDIT_CN.md",
        "BSC_OVERNIGHT_SAFETY_AUDIT_CN.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
    ]
    for marker in required:
        assert marker in text


def test_stage_and_safety_markers_are_present() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"stage": "LP_BSC_PANCAKESWAP_V3_OVERNIGHT_REALDATA_PIPELINE_V1"' in text
    assert '"tiny_canary_allowed": "no"' in text
    assert '"wallet_or_tx_touched": False' in text
