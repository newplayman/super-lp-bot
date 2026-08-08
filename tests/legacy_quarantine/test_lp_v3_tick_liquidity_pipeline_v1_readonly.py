from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/Users/bendu/lp-bot/v3")
SCRIPT = ROOT / "scripts" / "lp_v3_tick_liquidity_pipeline_v1_readonly.py"
REPORT_DIR = ROOT / "reports" / "lp_v3_tick_liquidity" / "20260601_130245"


def test_no_wallet_or_private_key_usage() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction",
        "signtransaction(",
        "sendtransaction(",
        "private_key",
        "mnemonic",
        "--canary-mint",
    ]
    for token in banned:
        assert token not in text


def test_no_swap_mint_burn_collect_execution() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in ['"swap_called": false', '"mint_called": false', '"burn_called": false', '"collect_called": false']:
        assert forbidden in text


def test_scan_range_cap_exists() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MAX_WORDS_PER_SIDE = 8" in text
    assert "TARGET_INITIALIZED_TICKS = 50" in text


def test_schema_required_fields_present() -> None:
    schema = json.loads((REPORT_DIR / "v3_tick_liquidity_schema.json").read_text(encoding="utf-8"))
    fields = set(schema["fields"])
    required = {
        "run_id",
        "pool_id",
        "tick_index",
        "liquidity_gross",
        "liquidity_net",
        "scan_method",
        "confidence",
        "invalid_reason",
        "read_only_safe",
        "wallet_or_tx_touched",
    }
    assert required.issubset(fields)


def test_abi_inventory_excludes_state_changing_calls() -> None:
    inventory = json.loads((REPORT_DIR / "v3_pool_state_abi_inventory.json").read_text(encoding="utf-8"))
    forbidden = {row["method"] for row in inventory if not row["read_only_safe"]}
    assert {"mint", "burn", "collect", "swap", "flash"}.issubset(forbidden)


def test_invalid_pool_rows_have_invalid_reason() -> None:
    results = (REPORT_DIR / "v3_tick_liquidity_results.json").read_text(encoding="utf-8")
    assert '"invalid_reason"' in results


def test_final_verdict_never_allows_probe_or_canary() -> None:
    verdict = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text(encoding="utf-8"))
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["recommended_next_stage"] in {
        "LP_REAL_COST_MODEL_PIPELINE_V1",
        "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
        "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }
