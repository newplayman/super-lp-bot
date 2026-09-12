"""R2-09 + R3 / Package E: liquidation NAV uses the raw-liquidity unit
contract unconditionally — no threshold branch.

Re-audit 04e8a45 / 6fda329 confirmed:
  * The 6fda329 code had ``l_human = l / scale_factor if l >= scale_factor
    else l`` — a threshold branch that silently passed small ``l``
    through as raw, amplifying by ~1e12 for small principals.
  * The original test used ``position_usd=1000``, where ``l_pos`` from
    ``inventory_for_position`` is always >> ``scale_factor``; the
    threshold branch was always true and the bug was never exercised.
  * Reverse-tests showed ``principal=1, price=2000`` returned ~1e12
    instead of ~1.
"""

from decimal import Decimal

import pytest

from scripts.lp_rh_pnl_v1_readonly import compute_liquidation_nav
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position


def _liquidation(position_usd: Decimal, price: Decimal, *, range_pct=Decimal("10"),
                 decimals=(18, 6), slippage_bps=Decimal("0")):
    """Build a position via the inventory module and feed its raw
    liquidity into ``compute_liquidation_nav`` — exactly the contract
    used by run_episode.  Returns (nav, reason)."""
    inv = inventory_for_position(
        position_usd=position_usd,
        entry_price=price,
        range_pct=range_pct,
        dec0=decimals[0],
        dec1=decimals[1],
        quote_usd_per_token1=Decimal("1"),
    )
    p_lower = price * (Decimal(1) - range_pct / Decimal(100))
    p_upper = price * (Decimal(1) + range_pct / Decimal(100))
    out = compute_liquidation_nav(
        l_pos=inv.liquidity_raw,
        price=price,
        range=(p_lower, p_upper),
        fee_growth_0=Decimal("0"),
        fee_growth_1=Decimal("0"),
        decimals=decimals,
        slippage_bps_max=slippage_bps,
        entry_cost_usd=Decimal("0"),
        exit_cost_usd=Decimal("0"),
        gas_usd=Decimal("0"),
        quote_usd_per_token1=Decimal("1"),
    )
    return out, inv


def test_liquidation_nav_scales_raw_liquidity_normal_case():
    """R2-09 control: principal=1000, price=2000, decimals=(18,6).
    Reconstructed USD must match position_usd within $0.01."""
    out, inv = _liquidation(Decimal("1000"), Decimal("2000"))
    assert out.reason is None
    assert out.nav is not None
    assert abs(out.nav - inv.reconstructed_usd) <= Decimal("0.01")


def test_liquidation_nav_does_not_amplify_small_principal(tmp_path=None):
    """R3 / Package E: principal=1, price=2000, decimals=(18,6).
    The 6fda329 threshold branch returned ~1e12; the fix returns ~1."""
    out, inv = _liquidation(Decimal("1"), Decimal("2000"))
    assert out.reason is None
    assert out.nav is not None
    # The bug amplified by ~10^12.  The fix returns a number near the
    # principal itself, allowing for IL within the ±10% range.
    assert out.nav < Decimal("100"), (
        f"small principal must not be amplified to ~1e12; got {out.nav}"
    )
    # And the value must be in a sensible band: within the position_usd
    # principal ± half-range, accounting for IL.
    assert out.nav >= Decimal("0")
    assert abs(out.nav - Decimal("1")) < Decimal("0.5"), (
        f"small principal liquidation nav {out.nav} is far from position_usd=1; "
        "this is the 1e12 amplification regression"
    )


def test_liquidation_nav_does_not_amplify_medium_principal():
    """R3 / Package E: principal=50, price=4000, range=±90% — the
    re-audit example showed ~5e13; the fix returns ~50."""
    out, inv = _liquidation(Decimal("50"), Decimal("4000"), range_pct=Decimal("90"))
    assert out.reason is None
    assert out.nav is not None
    assert out.nav < Decimal("1000"), (
        f"medium principal must not be amplified to ~5e13; got {out.nav}"
    )


def test_liquidation_nav_missing_inputs_returns_none():
    """R2-09 control: missing inputs fail close."""
    out = compute_liquidation_nav(
        l_pos=None,
        price=Decimal("2000"),
        range=(Decimal("1800"), Decimal("2200")),
    )
    assert out.nav is None
    assert out.reason == "LIQUIDATION_NAV_INPUT_MISSING"
