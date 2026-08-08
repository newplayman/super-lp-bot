from pathlib import Path


SCRIPT = Path("/Users/bendu/lp-bot/v3/scripts/lp_fee_velocity_pipeline_fix_repeat_v1_readonly.py")


def read_script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_wallet_or_private_key_usage():
    text = read_script().lower()
    banned = ["eth_sendrawtransaction", "sendtransaction(", "signtransaction(", "private_key=", "mnemonic="]
    for marker in banned:
        assert marker not in text


def test_fixed_cost_scenarios_present():
    text = read_script()
    for marker in ["0.0", "0.02", "0.05", "0.10", "0.20", "0.50"]:
        assert marker in text


def test_entry_safe_fee_rules_present():
    text = read_script()
    assert "previous_fully_closed_bucket" in text
    assert "same_bucket_features_banned" in text
    assert "entry_safe" in text


def test_positive_proxy_does_not_imply_edge():
    text = read_script()
    assert '"edge_proven": "no"' in text
    assert '"tiny_canary_allowed": "no"' in text


def test_optimistic_diagnostic_cannot_allow_probe():
    text = read_script()
    assert "optimistic_diagnostic" in text
    assert '"can_run_probe_now": False' in text or '"can_run_probe_now": false' in text.lower()


def test_final_stage_and_required_outputs_present():
    text = read_script()
    assert "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1" in text
    for marker in [
        "FEE_COVERAGE_GAP_DIAGNOSIS_CN.md",
        "FIXED_COST_MODEL_AUDIT_CN.md",
        "FEE_VELOCITY_V2_RESULTS_CN.md",
        "FIXED_COST_SENSITIVITY_ECONOMICS_CN.md",
        "EV_SCENARIO_COMPARISON_CN.md",
        "LP_FEE_FIX_REPEAT_NEXT_STAGE_DECISION_CN.md",
        "FINAL_VERDICT.json",
    ]:
        assert marker in text


def test_output_schema_required_fields_present():
    text = read_script()
    for marker in [
        '"fee_velocity_v2_built"',
        '"fee_ready_pool_count_v1"',
        '"fee_ready_pool_count_v2"',
        '"upgraded_pool_count"',
        '"fixed_cost_audit_complete"',
        '"fixed_cost_now_main_confirmed"',
        '"fixed_cost_maybe_overconservative"',
        '"sensitivity_ran"',
        '"positive_proxy_count_fixed_cost_0"',
        '"positive_proxy_count_realistic"',
        '"best_realistic_net_ev_proxy_usd"',
        '"best_realistic_net_ev_proxy_pct"',
        '"main_remaining_blocker"',
        '"recommended_next_stage"',
    ]:
        assert marker in text
