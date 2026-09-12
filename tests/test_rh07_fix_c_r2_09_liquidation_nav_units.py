from decimal import Decimal
import pytest

from scripts.lp_rh_pnl_v1_readonly import compute_liquidation_nav
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position


def test_liquidation_nav_scales_raw_liquidity():
    """R2-09: Verify compute_liquidation_nav scales raw liquidity to human units for position valuation."""
    inv = inventory_for_position(
        position_usd=Decimal("1000"),
        entry_price=Decimal("2000"),
        range_pct=Decimal("10"),
        dec0=18,
        dec1=6,
        quote_usd_per_token1=Decimal("1"),
    )

    out = compute_liquidation_nav(
        l_pos=inv.liquidity_raw,
        price=Decimal("2000"),
        range=(Decimal("1800"), Decimal("2200")),
        fee_growth_0=Decimal("0"),
        fee_growth_1=Decimal("0"),
        decimals=(18, 6),
        slippage_bps_max=Decimal("0"),
        entry_cost_usd=Decimal("0"),
        exit_cost_usd=Decimal("0"),
        gas_usd=Decimal("0"),
        quote_usd_per_token1=Decimal("1"),
    )

    assert out.reason is None
    assert out.nav is not None
    # NAV should match reconstructed USD of ~$1000 within $0.01
    assert abs(out.nav - inv.reconstructed_usd) <= Decimal("0.01")


def test_liquidation_nav_missing_inputs_returns_none():
    """R2-09 Control: Missing required inputs fails close and returns LIQUIDATION_NAV_INPUT_MISSING."""
    out = compute_liquidation_nav(
        l_pos=None,
        price=Decimal("2000"),
        range=(Decimal("1800"), Decimal("2200")),
    )
    assert out.nav is None
    assert out.reason == "LIQUIDATION_NAV_INPUT_MISSING"
