from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
SCRIPT = REPO_ROOT / "scripts" / "lp_real_data_reopen_prep_v1_readonly.py"
REPORT_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
ALLOWED_NEXT = {
    "LP_PRECISE_QUOTE_PIPELINE_V1",
    "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    "LP_REAL_COST_MODEL_PIPELINE_V1",
    "REAL_DATA_PIPELINE_DESIGN_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


def test_script_does_not_use_wallet_or_tx_submit_symbols() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = [
        "eth_sendrawtransaction",
        "sendtransaction(",
        "signtransaction(",
        "private_key",
        "mnemonic",
        "--canary-mint",
    ]
    for token in forbidden:
        assert token not in text


def test_inventory_marks_future_probe_only_as_non_readonly() -> None:
    data = json.loads((REPORT_DIR / "real_data_source_inventory.json").read_text(encoding="utf-8"))
    future_probe_rows = [row for row in data["rows"] if row["source_type"] == "future_probe_only"]
    assert future_probe_rows
    for row in future_probe_rows:
        assert row["requires_wallet"] == "yes"
        assert row["requires_signature"] == "yes"
        assert row["requires_transaction"] == "yes"
        assert row["read_only_safe"] == "no"


def test_final_verdict_never_allows_probe_or_canary() -> None:
    verdict = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text(encoding="utf-8"))
    assert verdict["stage"] == "LP_REAL_DATA_REOPEN_PREP_V1"
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["recommended_next_stage"] in ALLOWED_NEXT


def test_readiness_audit_does_not_reopen_probe() -> None:
    audit = (REPORT_DIR / "real_data_readiness_audit.csv").read_text(encoding="utf-8")
    assert "can_reopen_probe_preflight,yes" not in audit
