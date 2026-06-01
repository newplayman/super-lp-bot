from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/Users/bendu/lp-bot/v3")
SCRIPT = ROOT / "scripts" / "lp_v3_tick_liquidity_pipeline_v2_readonly.py"
REPORT_DIR = ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_wallet_or_private_key_usage() -> None:
    text = script_text().lower()
    banned = [
        "eth_sendrawtransaction",
        "eth_sendtransaction",
        "signtransaction(",
        "sendtransaction(",
        "private_key",
        "mnemonic",
        "from_key(",
        "--canary-mint",
    ]
    for token in banned:
        assert token not in text


def test_no_swap_mint_burn_collect_execution() -> None:
    text = script_text().lower()
    assert '"swap_called": false' in text
    assert '"mint_called": false' in text
    assert '"burn_called": false' in text
    assert '"collect_called": false' in text
    assert "router" not in text


def test_prevalidation_handles_non_contract_and_slot0_variant() -> None:
    text = script_text()
    assert 'reject_reason = "not_contract"' in text
    assert 'reject_reason = f"unsupported_slot0_len_{slot0_len}"' in text
    assert 'prevalidate_pass = True' in text


def test_method_level_failure_does_not_kill_whole_pool() -> None:
    text = script_text()
    assert 'except Exception:' in text
    assert 'stats["observe_success"] = True' in text
    assert '"confidence": "high" if stats["observe_success"] else "medium"' in text
    assert '"partial_success": not stats["observe_success"]' in text


def test_abi_decode_error_captured() -> None:
    text = script_text()
    assert 'root = "abi_decode_error"' in text
    assert 'method_errors["slot0_decode"] = f"unsupported_slot0_length:{out[\'slot0_len_bytes\']}"' in text


def test_root_cause_required_for_invalid_rows() -> None:
    text = script_text()
    assert '"invalid_reason": stats["root_cause"]' in text
    assert '"root_cause": "method_revert"' in text
    assert '"root_cause": "abi_decode_error"' in text


def test_tick_scan_range_cap_exists() -> None:
    text = script_text()
    assert "MAX_WORDS_PER_SIDE =" in text
    assert "TARGET_INITIALIZED_TICKS =" in text
    assert "for distance in range(0, MAX_WORDS_PER_SIDE + 1):" in text


def test_schema_required_fields_present() -> None:
    text = script_text()
    required = {
        '"run_id"',
        '"pool_id"',
        '"source_pool_selection"',
        '"prevalidate_status"',
        '"partial_success"',
        '"confidence"',
        '"invalid_reason"',
        '"root_cause"',
        '"read_only_safe"',
        '"wallet_or_tx_touched"',
    }
    for token in required:
        assert token in text


def test_final_verdict_never_allows_probe_or_canary() -> None:
    text = script_text()
    assert '"can_run_probe_now": False' in text
    assert '"tiny_canary_allowed": "no"' in text
    assert '"edge_proven": "no"' in text


def test_allowed_next_stage_list_is_restricted() -> None:
    text = script_text()
    for allowed in {
        "LP_REAL_COST_MODEL_PIPELINE_V1",
        "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
        "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }:
        assert allowed in text


def test_report_stage_matches_requested_stage() -> None:
    verdict = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text(encoding="utf-8"))
    assert verdict["stage"] == "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT_V1"
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
