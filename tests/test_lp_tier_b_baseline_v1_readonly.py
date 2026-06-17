import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_tier_b_baseline_v1_readonly import (  # noqa: E402
    fee_apr_pct,
    classify_tier,
    realized_24h_net,
)


def test_fee_apr_pct_matches_expected_band():
    value = fee_apr_pct(5, 133_263_196, 8_481_774)
    assert 280 < value < 295


def test_fee_apr_pct_zero_tvl_is_zero():
    assert fee_apr_pct(5, 100, 0) == 0.0


def test_classify_tier_boundaries():
    assert classify_tier(20) == "sub"
    assert classify_tier(50) == "A"
    assert classify_tier(287) == "B"
    assert classify_tier(900) == "C"
    assert classify_tier(80) == "B"
    assert classify_tier(800) == "C"


def test_realized_24h_net_in_range_capture_and_signs():
    result = realized_24h_net(size_usd=200, range_pct=10, fee_apr=286.5, price_change_pct_h24=2)
    assert result["capture"] == 1.0
    assert result["il_usd"] <= 0
    assert result["fee_usd"] > 0


def test_realized_24h_net_exit_range_lower_capture_and_exact_net():
    result = realized_24h_net(size_usd=200, range_pct=5, fee_apr=286.5, price_change_pct_h24=20)
    assert result["capture"] == 0.25
    assert result["il_usd"] < 0
    assert result["net_usd_24h"] == result["fee_usd"] + result["il_usd"]
