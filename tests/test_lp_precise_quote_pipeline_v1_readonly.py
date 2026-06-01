from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
SCRIPT = REPO_ROOT / "scripts" / "lp_precise_quote_pipeline_v1_readonly.py"
REPORT_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"


def test_no_wallet_or_tx_symbols_in_script() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction",
        "sendtransaction(",
        "signtransaction(",
        "private_key",
        "mnemonic",
        "--canary-mint",
    ]
    for token in banned:
        assert token not in text


def test_no_swap_mint_burn_collect_execution_symbols() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for token in [" swap(", " mint(", " burn(", " collect("]:
        assert token not in text


def test_notionals_and_schema_fields_present() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for n in ["20", "100", "500", "1000", "2000"]:
        assert n in text
    schema = json.loads((REPORT_DIR / "precise_quote_schema.json").read_text(encoding="utf-8"))
    required = {
        "run_id", "pool_id", "quote_method", "quote_side", "virtual_notional_usd",
        "amount_in_raw", "amount_out_raw", "estimated_slippage_pct", "gas_estimate",
        "quote_success", "confidence", "invalid_reason", "read_only_safe", "wallet_or_tx_touched",
    }
    assert required.issubset(set(schema["required_fields"]))


def test_invalid_quotes_have_invalid_reason_and_comparison_fields_exist() -> None:
    results = (REPORT_DIR / "precise_quote_results.csv").read_text(encoding="utf-8")
    assert "invalid_reason" in results
    compare = (REPORT_DIR / "precise_quote_vs_depth_v2_comparison.csv").read_text(encoding="utf-8")
    for field in ["prior_slippage_pct", "precise_slippage_pct", "delta_slippage", "direction"]:
        assert field in compare


def test_final_verdict_never_allows_probe_or_canary() -> None:
    verdict = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text(encoding="utf-8"))
    assert verdict["stage"] == "LP_PRECISE_QUOTE_PIPELINE_V1"
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
