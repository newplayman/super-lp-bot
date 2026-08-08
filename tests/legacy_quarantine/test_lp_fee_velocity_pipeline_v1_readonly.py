from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_fee_velocity_pipeline_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_fee_velocity_pipeline_v1_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_no_wallet_or_private_key_usage():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = ["eth_sendrawtransaction", "sendtransaction(", "signtransaction(", "private_key=", "mnemonic="]
    for token in banned:
        assert token not in text


def test_entry_safe_timestamp_rules_present():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "feature_cutoff_time" in text
    assert "entry_safe" in text


def test_fee_source_confidence_classification_present():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"high"' in text or "'high'" in text
    assert '"medium"' in text or "'medium'" in text
    assert '"low"' in text or "'low'" in text


def test_no_future_volume_leakage_wording_present():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "future volume" in text
    assert "same-bucket incomplete volume" in text or "same bucket incomplete volume" in text


def test_output_schema_required_fields():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for field in [
        "fee_source","fee_tier_bps","bucket_start","bucket_end","feature_cutoff_time","volume_usd_proxy",
        "gross_fee_pool_usd_proxy","fee_velocity_rate_15m","fee_velocity_rate_30m","fee_velocity_rate_1h",
        "fee_velocity_rate_2h","fee_apr_proxy","confidence","invalid_reason"
    ]:
        assert f'"{field}"' in text or f"'{field}'" in text


def test_preview_positive_proxy_not_edge_proven():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"edge_proven":"no"' in text.replace(" ", "") or '"edge_proven": "no"' in text


def test_can_run_probe_now_remains_false():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"can_run_probe_now": False' in text or '"can_run_probe_now": false' in text.lower()

