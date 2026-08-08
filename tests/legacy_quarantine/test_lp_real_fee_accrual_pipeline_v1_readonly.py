from pathlib import Path


SCRIPT = Path("/Users/bendu/lp-bot/v3/scripts/lp_real_fee_accrual_pipeline_v1_readonly.py")


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
    assert '"future_probe_only": True' in text or '"future_probe_only": true' in text.lower()
    assert '"wallet_or_tx_touched": False' in text or '"wallet_or_tx_touched": false' in text.lower()


def test_actual_fee_requires_position_lineage():
    text = read_script()
    assert "usable_if_token_id_exists" in text
    assert "actual_position_fee_unavailable" in text
    assert "simulated_only_no_token_id" in text


def test_pool_level_fee_not_labeled_actual_fee():
    text = read_script()
    assert "pool_level_fee_velocity_proxy" in text
    assert "actual_position_fee_accrual" in text
    assert "pool_level_positive_not_edge" in text


def test_required_research_tables_present():
    text = read_script()
    for marker in [
        "lp_real_fee_accrual_v1",
        "lp_fee_accrual_readiness_v1",
        "lp_virtual_notional_economics_real_fee_preview_v1",
    ]:
        assert marker in text


def test_final_stage_and_no_canary():
    text = read_script()
    assert "LP_REAL_FEE_ACCRUAL_PIPELINE_V1" in text
    assert '"edge_proven": "no"' in text
    assert '"tiny_canary_allowed": "no"' in text
    assert '"can_run_probe_now": False' in text or '"can_run_probe_now": false' in text.lower()


def test_required_outputs_present():
    text = read_script()
    for marker in [
        "POSITION_LINEAGE_INVENTORY_CN.md",
        "FEE_ACCRUAL_CONTRACT_ABI_INVENTORY_CN.md",
        "REAL_FEE_ACCRUAL_METHOD_POLICY_CN.md",
        "FEE_ACCRUAL_READINESS_RESULTS_CN.md",
        "REAL_FEE_ACCRUAL_RESULTS_CN.md",
        "FEE_PROXY_VS_REAL_FEE_COMPARISON_CN.md",
        "REAL_FEE_ECONOMICS_PREVIEW_CN.md",
        "FEE_ACCRUAL_BLOCKER_DIAGNOSIS_CN.md",
        "REAL_FEE_ACCRUAL_SAFETY_AUDIT_CN.md",
        "LP_REAL_FEE_NEXT_STAGE_DECISION_CN.md",
        "FINAL_VERDICT.json",
    ]:
        assert marker in text
