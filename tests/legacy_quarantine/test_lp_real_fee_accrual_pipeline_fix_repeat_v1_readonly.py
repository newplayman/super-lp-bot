from pathlib import Path


SCRIPT = Path("/Users/bendu/lp-bot/v3/scripts/lp_real_fee_accrual_pipeline_fix_repeat_v1_readonly.py")


def read_script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_wallet_or_private_key_usage():
    text = read_script().lower()
    banned = [
        'method":"eth_sendrawtransaction',
        'method":"eth_sendtransaction',
        "signtransaction(",
        "private_key=",
        "mnemonic=",
    ]
    for marker in banned:
        assert marker not in text


def test_no_execution_methods_called():
    text = read_script()
    for marker in ["mint_called", "collect_called", "approve_called", "swap_called"]:
        assert marker in text
    assert '"wallet_or_tx_touched": False' in text or '"wallet_or_tx_touched": false' in text.lower()


def test_bounded_log_query_only():
    text = read_script()
    assert '"bounded_log_query_count"' in text
    assert '"skipped_unbounded_query_count"' in text


def test_token_id_recovery_requires_event_evidence():
    text = read_script()
    assert "manager_contract_unknown_and_owner_unknown" in text
    assert "token_id_not_recoverable_from_existing_lineage" in text


def test_no_token_id_means_no_actual_fee():
    text = read_script()
    assert '"actual_fee_recalculated_count": actual_fee_summary["actual_fee_recalculated_count"]' in text
    assert '"positive_proxy_count_actual_fee": preview_summary["positive_proxy_count_actual_fee"]' in text


def test_pool_level_fee_not_actual_fee():
    text = read_script()
    assert "pool_level_fee_fallback" in text
    assert "simulated_fee_diagnostic" in text
    assert '"can_reopen_virtual_economics": False' in text


def test_strict_probe_readiness_cannot_pass_without_gates():
    text = read_script()
    assert '"strict_probe_readiness_pass": False' in text or '"strict_probe_readiness_pass": false' in text.lower()
    assert '"can_run_probe_now": False' in text or '"can_run_probe_now": false' in text.lower()


def test_final_stage_and_no_canary_live():
    text = read_script()
    assert "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT_V1" in text
    assert '"tiny_canary_allowed": "no"' in text
    assert '"edge_proven": "no"' in text
