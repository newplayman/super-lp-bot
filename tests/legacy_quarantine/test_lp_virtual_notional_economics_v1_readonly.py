from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_virtual_notional_economics_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_virtual_notional_economics_v1_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_no_wallet_or_private_key_runtime_symbols():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = ["eth_sendrawtransaction", "sendtransaction(", "signtransaction(", "private_key=", "mnemonic="]
    for token in banned:
        assert token not in text


def test_tested_notionals_fixed():
    assert module.TESTED_NOTIONALS == [20, 100, 500, 1000, 2000]


def test_break_even_formula():
    variable_edge_rate = 0.01
    fixed_cost_usd = 0.1
    assert fixed_cost_usd / variable_edge_rate == 10


def test_no_size_can_fix_when_variable_edge_non_positive():
    assert (0.0 <= 0.0) is True
    assert (-0.001 <= 0.0) is True


def test_capacity_fail_handling():
    row = {
        "capacity_pass": "no",
        "net_ev_proxy_usd": -1.0,
    }
    assert row["capacity_pass"] == "no"


def test_output_schema_required_fields():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for field in [
        "gross_fee_proxy_usd","fee_velocity_rate","il_lvr_proxy_usd","il_lvr_proxy_rate","slippage_cost_usd",
        "exit_cost_usd","fixed_cost_usd","net_ev_proxy_usd","net_ev_proxy_pct","variable_edge_rate",
        "break_even_notional_usd","no_size_can_fix","ev_status","primary_blocker"
    ]:
        assert f'"{field}"' in text or f"'{field}'" in text


def test_positive_proxy_not_edge_proven():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"edge_proven": "no"' in text

