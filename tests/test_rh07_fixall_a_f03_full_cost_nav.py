from __future__ import annotations

from decimal import Decimal
import pytest

from scripts.lp_rh_pnl_v1_readonly import (
    compute_full_cost_nav,
    compute_liquidation_nav,
    compute_nav,
)


def test_full_cost_nav_deducts_frictions():
    """Verify that compute_full_cost_nav properly accounts for all frictions.

    When price is unchanged, fee income is zero, and positive entry_cost is paid,
    NAV must be strictly less than wallet (net loss from friction).
    """
    wallet = Decimal("1000.00")
    lp_principal = Decimal("500.00")
    entry_cost = Decimal("15.50")
    exit_cost = Decimal("5.00")
    gas = Decimal("2.00")
    slippage = Decimal("1.00")

    nav_full = compute_full_cost_nav(
        wallet=wallet,
        lp_principal=lp_principal,
        accrued_fees=Decimal("0"),
        entry_cost_usd=entry_cost,
        exit_cost_usd=exit_cost,
        gas_usd=gas,
        slippage_usd=slippage,
        verified_rewards=Decimal("0"),
        liabilities=Decimal("0"),
    )

    # Total friction = 15.50 + 5.00 + 2.00 + 1.00 = 23.50
    expected = wallet + lp_principal - Decimal("23.50")
    assert nav_full == expected
    # Net return accounting proves friction is deducted
    assert nav_full < (wallet + lp_principal)


def test_full_cost_nav_reverse_validation_defect_simulation():
    """Simulate defect: reverting to reference NAV formula (ignoring costs).

    Under defect: nav = wallet + lp_principal + fees (costs ignored).
    Under fix: nav = wallet + lp_principal - entry_cost ...
    """
    wallet = Decimal("1000.00")
    lp_principal = Decimal("0.00")
    entry_cost = Decimal("25.00")

    # Fixed implementation:
    fixed_nav = compute_full_cost_nav(
        wallet=wallet,
        lp_principal=lp_principal,
        accrued_fees=Decimal("0"),
        entry_cost_usd=entry_cost,
        exit_cost_usd=Decimal("0"),
        gas_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
    )
    assert fixed_nav < wallet
    assert fixed_nav == Decimal("975.00")

    # Defective implementation (old compute_nav behavior):
    def defective_nav_calc(*, wallet, lp_principal, **kwargs):
        return compute_nav(
            wallet=wallet,
            lp_principal=lp_principal,
            accrued_fees=Decimal("0"),
            verified_rewards=Decimal("0"),
            liabilities=Decimal("0"),
        )

    defect_nav = defective_nav_calc(
        wallet=wallet,
        lp_principal=lp_principal,
        entry_cost_usd=entry_cost,
    )
    # Under defect, NAV falsely equals wallet (costs not deducted)
    assert defect_nav == wallet
    assert not (defect_nav < wallet)


def test_liquidation_nav_fail_close_on_missing_fee_growth():
    """compute_liquidation_nav must return None + reason when fee_growth is missing, never report 0."""
    res = compute_liquidation_nav(
        l_pos=Decimal("1000000"),
        price=Decimal("2500"),
        range=(Decimal("2400"), Decimal("2600")),
        fee_growth_0=None,
        fee_growth_1=Decimal("500"),
        decimals=(18, 6),
    )
    assert res.liquidation_nav is None
    assert res.reason == "LIQUIDATION_NAV_INPUT_MISSING"
    assert res[0] is None
    assert res[1] == "LIQUIDATION_NAV_INPUT_MISSING"

    # Also test fee_growth_1 missing
    res2 = compute_liquidation_nav(
        l_pos=Decimal("1000000"),
        price=Decimal("2500"),
        range=(Decimal("2400"), Decimal("2600")),
        fee_growth_0=Decimal("500"),
        fee_growth_1=None,
        decimals=(18, 6),
    )
    assert res2.liquidation_nav is None
    assert res2.reason == "LIQUIDATION_NAV_INPUT_MISSING"


def test_liquidation_nav_valid_calculation():
    """compute_liquidation_nav calculates conservative exit value deducting slippage cap."""
    res = compute_liquidation_nav(
        l_pos=Decimal("1000000"),
        price=Decimal("2500"),
        range=(Decimal("2400"), Decimal("2600")),
        fee_growth_0=Decimal("1000"),
        fee_growth_1=Decimal("2000"),
        decimals=(18, 6),
        slippage_bps_max=Decimal("200"),
        entry_cost_usd=Decimal("5.0"),
        exit_cost_usd=Decimal("5.0"),
    )
    assert res.liquidation_nav is not None
    assert res.liquidation_nav > Decimal("0")
    assert res.reason is None
