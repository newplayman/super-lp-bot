from pathlib import Path


SCRIPT = Path("/Users/bendu/lp-bot/v3/scripts/lp_il_lvr_pipeline_v1_readonly.py")


def read_script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_wallet_or_private_key_usage():
    text = read_script().lower()
    banned = ["eth_sendrawtransaction", "sendtransaction(", "signtransaction(", "private_key=", "mnemonic="]
    for marker in banned:
        assert marker not in text


def test_entry_safe_il_lvr_rules_present():
    text = read_script()
    assert "previous_fully_closed_bucket" in text
    assert "same_bucket_features_banned" in text
    assert "feature_cutoff_time" in text


def test_il_lvr_scenarios_present():
    text = read_script()
    for marker in ["zero_il_lvr", "optimistic", "realistic", "conservative"]:
        assert marker in text


def test_positive_proxy_does_not_imply_edge():
    text = read_script()
    assert '"edge_proven": "no"' in text
    assert '"tiny_canary_allowed": "no"' in text


def test_output_schema_required_fields_present():
    text = read_script()
    for marker in [
        '"il_lvr_proxy_built"',
        '"il_lvr_ready_pool_count"',
        '"positive_proxy_count_zero_il_lvr"',
        '"positive_proxy_count_optimistic"',
        '"positive_proxy_count_realistic"',
        '"best_realistic_net_ev_proxy_usd"',
        '"best_realistic_net_ev_proxy_pct"',
        '"main_remaining_blocker"',
        '"recommended_next_stage"',
    ]:
        assert marker in text
