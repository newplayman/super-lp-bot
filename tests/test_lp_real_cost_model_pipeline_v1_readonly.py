from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/Users/bendu/lp-bot/v3")
SCRIPT = ROOT / "scripts" / "lp_real_cost_model_pipeline_v1_readonly.py"
REPORT_DIR = ROOT / "reports" / "lp_real_cost_model" / "20260601_141103"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_wallet_private_key_or_signer_usage() -> None:
    text = script_text().lower()
    for token in [
        "from_key(",
        "signtransaction(",
        "eth_account",
        "mnemonic=",
        "private_key=",
    ]:
        assert token not in text


def test_no_tx_submit_symbols() -> None:
    text = script_text().lower()
    for token in ["eth_sendtransaction(", "eth_sendrawtransaction(", "sendrawtransaction(", "sendtransaction("]:
        assert token not in text


def test_no_swap_mint_burn_collect_or_approve_execution() -> None:
    text = script_text()
    assert '"swap_called": False' in text
    assert '"mint_called": False' in text
    assert '"burn_called": False' in text
    assert '"collect_called": False' in text
    assert '"approve_called": False' in text


def test_estimate_gas_never_submits_tx() -> None:
    text = script_text()
    assert '"estimate_gas_only": True' in text
    assert '"eth_sendTransaction_called": False' in text
    assert '"eth_sendRawTransaction_called": False' in text


def test_cost_scenarios_include_low_mid_high() -> None:
    text = script_text()
    assert '"diagnostic_low"' in text
    assert '"realistic_mid"' in text
    assert '"conservative_high"' in text


def test_output_schema_required_fields_present() -> None:
    text = script_text()
    for token in [
        '"run_id"',
        '"pool_id"',
        '"cost_scenario"',
        '"virtual_notional_usd"',
        '"quote_gas_estimate"',
        '"entry_swap_cost_usd"',
        '"exit_swap_cost_usd"',
        '"lp_add_fixed_cost_usd"',
        '"lp_remove_fixed_cost_usd"',
        '"collect_fixed_cost_usd"',
        '"total_fixed_cost_usd"',
        '"proportional_slippage_cost_usd"',
        '"future_probe_only_fields"',
        '"wallet_or_tx_touched"',
    ]:
        assert token in text


def test_future_probe_only_does_not_enable_probe() -> None:
    text = script_text()
    assert '"manual_approval_required_for_probe": True' in text
    assert '"can_run_probe_now": False' in text
    assert '"tiny_canary_allowed": "no"' in text


def test_positive_preview_cannot_set_edge_proven() -> None:
    text = script_text()
    assert '"edge_proven": "no"' in text


def test_final_verdict_never_allows_probe_or_canary() -> None:
    verdict = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text(encoding="utf-8"))
    assert verdict["stage"] == "LP_REAL_COST_MODEL_PIPELINE_V1"
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["recommended_next_stage"] in {
        "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
        "LP_REAL_COST_MODEL_PIPELINE_FIX_REPEAT",
        "LP_REAL_DATA_PIPELINE_DESIGN_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }
