"""PRD v2.1 section 2.1 capital-tier mapping contracts."""
import pytest

from scripts.lp_capital_tiers_v1_readonly import (
    CAPITAL_TIER_CONFIGURED_MAX_USD,
    CAPITAL_TIER_TVL_MIN_USD,
    DEFAULT_CAPITAL_TIER,
    coarse_tvl_min_usd,
)
from scripts.lp_scanner_daemon_v1_readonly import DefaultStages, _parser
from scripts.lp_universe_screener_v1_readonly import DEFAULTS


def test_prd_v21_four_tier_constants_and_m1_default_are_explicit():
    assert CAPITAL_TIER_TVL_MIN_USD == {
        "M1": 150_000.0,
        "M2": 200_000.0,
        "M3": 500_000.0,
        "M4": 1_000_000.0,
    }
    assert CAPITAL_TIER_CONFIGURED_MAX_USD == {
        "M1": 60.0,
        "M2": 75.0,
        "M3": 200.0,
        "M4": 500.0,
    }
    assert DEFAULT_CAPITAL_TIER == "M1"
    assert DEFAULTS["min_tvl"] == 150_000.0
    assert _parser().parse_args([]).capital_tier == "M1"


@pytest.mark.parametrize(
    ("tier", "floor", "tier_max"),
    [("M1", 150_000.0, 60.0), ("M2", 200_000.0, 75.0),
     ("M3", 500_000.0, 200.0), ("M4", 1_000_000.0, 500.0)],
)
def test_scanner_uses_selected_capital_tier(tier, floor, tier_max):
    stages = DefaultStages(capital_tier=tier, rpc_pool=object())
    assert stages.min_tvl == floor
    assert stages.tier_configured_max_usd == tier_max


def test_min_tvl_override_can_only_tighten_selected_tier():
    assert coarse_tvl_min_usd("M1", 100_000.0) == 150_000.0
    assert coarse_tvl_min_usd("M1", 175_000.0) == 175_000.0
    assert DefaultStages(min_tvl=100_000.0, rpc_pool=object()).min_tvl == 150_000.0
