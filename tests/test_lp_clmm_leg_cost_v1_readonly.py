"""TP-J FIX-J3 contracts for actual two-leg CLMM conversion notionals."""
from __future__ import annotations

import math

import pytest

from scripts.lp_cost_sensitivity_v1_readonly import _swap_components
from scripts.lp_swap_cost_model_v1_readonly import clmm_token0_value_fraction


class _Pool:
    l_active_raw_historical = 1e24
    price_usd = 100.0
    fee_tier = 0.003
    dec0 = 18
    dec1 = 6


def test_centered_clmm_leg_fraction_is_the_v3_inventory_value_not_full_position():
    # Direct derivation for P±20%: xP / (xP+y), with L and sqrt(P) cancelling.
    expected = (1.0 - 1.0 / math.sqrt(1.2)) / (
        (1.0 - 1.0 / math.sqrt(1.2)) + (1.0 - math.sqrt(0.8))
    )
    actual = clmm_token0_value_fraction(100.0, 20.0)
    assert actual == pytest.approx(expected)
    assert 0.0 < actual < 1.0
    assert actual == pytest.approx(0.5, abs=0.06)


def test_leg_cost_uses_exact_inventory_fraction_and_is_below_full_notional():
    full = _swap_components(1000.0, _Pool())
    fraction = clmm_token0_value_fraction(100.0, 20.0)
    corrected = _swap_components(1000.0, _Pool(), conversion_fraction=fraction)
    assert corrected["entry_cost_usd"] == pytest.approx(1000.0 * fraction * 0.003)
    assert corrected["exit_cost_usd"] == pytest.approx(1000.0 * fraction * 0.003)
    assert corrected["entry_cost_usd"] < full["entry_cost_usd"]
    assert corrected["round_trip_cost_usd"] < full["round_trip_cost_usd"]


def test_missing_range_is_explicit_conservative_upper_bound_for_legacy_artifacts():
    assert _swap_components(1000.0, _Pool())["conversion_fraction"] == 1.0
