"""
tests/test_lp_swap_cost_model_v1_readonly.py
---------------------------------------------
Pure property-based tests for lp_swap_cost_model_v1_readonly.
No network, no wallet.  Tests assert PROPERTIES, not magic magnitudes.
"""

import math
import sys
import os
import pytest

# Make sure the repo root is on sys.path so the `scripts` package resolves.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.lp_swap_cost_model_v1_readonly import (
    human_liquidity,
    swap_new_sqrt_price,
    price_impact_frac,
    slippage_bps_for_swap,
    effective_fee_share,
    exit_conversion_cost_usd,
    roundtrip_cost_usd,
)

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

DEC0_ETH = 18
DEC1_USDC = 6
DEC0_ETH2 = 18
DEC1_ETH2 = 18   # 18/18 pool (the case that caught the old decimal bug)

PRICE = 3000.0    # USDC per ETH
FEE_TIER = 5e-4   # 0.05 %
RANGE_PCT = 5.0

L_SCALE_18_6  = 10 ** ((18 + 6)  / 2)   # = 10**12
L_SCALE_18_18 = 10 ** ((18 + 18) / 2)   # = 10**18

def _pool_l_raw(pool_usd, price, dec0, dec1):
    """Rough L_raw for a balanced pool of size pool_usd."""
    scale = 10 ** ((dec0 + dec1) / 2)
    l_h = pool_usd / (2 * math.sqrt(price))
    return l_h * scale


L_RAW_1M  = _pool_l_raw(1_000_000,  PRICE, DEC0_ETH, DEC1_USDC)
L_RAW_10M = _pool_l_raw(10_000_000, PRICE, DEC0_ETH, DEC1_USDC)


# ---------------------------------------------------------------------------
# human_liquidity
# ---------------------------------------------------------------------------

class TestHumanLiquidity:
    def test_scale_18_6(self):
        """human_liquidity(l_raw, 18, 6) == l_raw / 10**12"""
        l_raw = 1_234_567_890_123.0
        expected = l_raw / L_SCALE_18_6
        assert math.isclose(human_liquidity(l_raw, 18, 6), expected, rel_tol=1e-12)

    def test_scale_18_18(self):
        """human_liquidity(l_raw, 18, 18) == l_raw / 10**18"""
        l_raw = 1e24
        expected = l_raw / L_SCALE_18_18
        assert math.isclose(human_liquidity(l_raw, 18, 18), expected, rel_tol=1e-12)

    def test_zero_returns_zero(self):
        assert human_liquidity(0.0, 18, 6) == 0.0

    def test_negative_returns_zero(self):
        assert human_liquidity(-1.0, 18, 6) == 0.0

    def test_not_dec0_minus_dec1_convention(self):
        """Smoke: 18/18 scale is NOT the same as 18/6 scale."""
        l_raw = 1e18
        h18_6  = human_liquidity(l_raw, 18, 6)
        h18_18 = human_liquidity(l_raw, 18, 18)
        assert h18_6 != pytest.approx(h18_18)
        # 18/6 scale is 10**12; 18/18 is 10**18 → 10**6 ratio
        assert math.isclose(h18_6 / h18_18, 1e6, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# swap_new_sqrt_price
# ---------------------------------------------------------------------------

class TestSwapNewSqrtPrice:
    def test_buy_base_raises_sqrt_price(self):
        sqrt_before = math.sqrt(PRICE)
        sqrt_after = swap_new_sqrt_price(1000.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base")
        assert sqrt_after > sqrt_before

    def test_sell_base_lowers_sqrt_price(self):
        sqrt_before = math.sqrt(PRICE)
        sqrt_after = swap_new_sqrt_price(1000.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
        assert sqrt_after < sqrt_before

    def test_zero_notional_unchanged(self):
        sqrt_before = math.sqrt(PRICE)
        # 0 notional → no price change
        result = swap_new_sqrt_price(0.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base")
        assert math.isclose(result, sqrt_before, rel_tol=1e-9)

    def test_bad_side_raises(self):
        with pytest.raises(ValueError):
            swap_new_sqrt_price(1000.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "bad_side")

    def test_result_positive(self):
        """sqrt(P') must remain positive even for a large sell."""
        result = swap_new_sqrt_price(1e12, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
        assert result > 0


# ---------------------------------------------------------------------------
# price_impact_frac
# ---------------------------------------------------------------------------

class TestPriceImpactFrac:
    def test_zero_at_zero_notional(self):
        assert price_impact_frac(0.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base") == 0.0

    def test_strictly_increasing_in_notional(self):
        impacts = [
            price_impact_frac(n, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base")
            for n in [100, 1_000, 10_000, 100_000]
        ]
        for a, b in zip(impacts, impacts[1:]):
            assert b > a, f"price impact must increase with notional: {a} >= {b}"

    def test_strictly_decreasing_in_l_raw(self):
        """Deeper pool → less impact for same notional."""
        sizes_l_raw = [L_RAW_1M / 10, L_RAW_1M, L_RAW_10M]
        impacts = [
            price_impact_frac(10_000, lraw, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
            for lraw in sizes_l_raw
        ]
        for a, b in zip(impacts, impacts[1:]):
            assert b < a, f"price impact must decrease with pool depth: {a} <= {b}"

    def test_buy_and_sell_symmetric_magnitude(self):
        """For symmetric sides the |ΔP/P| magnitudes should be close (not identical
        because one raises and the other lowers, but within ~2x for small trades)."""
        buy  = price_impact_frac(1_000, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base")
        sell = price_impact_frac(1_000, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
        assert buy > 0 and sell > 0
        ratio = buy / sell
        assert 0.5 < ratio < 2.0, f"buy/sell impact ratio unreasonable: {ratio}"


# ---------------------------------------------------------------------------
# slippage_bps_for_swap
# ---------------------------------------------------------------------------

class TestSlippageBps:
    def test_zero_at_zero_notional(self):
        assert slippage_bps_for_swap(0.0, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "buy_base") == 0.0

    def test_non_negative(self):
        for side in ("buy_base", "sell_base"):
            s = slippage_bps_for_swap(10_000, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, side)
            assert s >= 0

    def test_strictly_increasing_in_notional(self):
        slips = [
            slippage_bps_for_swap(n, L_RAW_1M, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
            for n in [100, 1_000, 10_000]
        ]
        for a, b in zip(slips, slips[1:]):
            assert b > a, f"slippage must increase with notional: {a} >= {b}"

    def test_strictly_decreasing_in_l_raw(self):
        l_raws = [L_RAW_1M / 5, L_RAW_1M, L_RAW_10M]
        slips = [
            slippage_bps_for_swap(5_000, lraw, PRICE, DEC0_ETH, DEC1_USDC, "sell_base")
            for lraw in l_raws
        ]
        for a, b in zip(slips, slips[1:]):
            assert b < a, f"deeper pool must have less slippage: {a} <= {b}"


# ---------------------------------------------------------------------------
# effective_fee_share
# ---------------------------------------------------------------------------

class TestEffectiveFeeShare:
    def test_in_unit_interval(self):
        fs = effective_fee_share(10_000, L_RAW_1M, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC)
        assert 0 < fs < 1

    def test_increasing_in_size_usd(self):
        shares = [
            effective_fee_share(sz, L_RAW_1M, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC)
            for sz in [100, 1_000, 10_000, 100_000]
        ]
        for a, b in zip(shares, shares[1:]):
            assert b > a, f"fee share must increase with size: {a} >= {b}"

    def test_decreasing_in_l_active_raw(self):
        l_raws = [L_RAW_1M / 5, L_RAW_1M, L_RAW_10M]
        shares = [
            effective_fee_share(10_000, lraw, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC)
            for lraw in l_raws
        ]
        for a, b in zip(shares, shares[1:]):
            assert b < a, f"fee share must decrease as pool is deeper: {a} <= {b}"

    def test_zero_for_zero_size(self):
        assert effective_fee_share(0, L_RAW_1M, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC) == 0.0

    def test_approximately_linear_at_small_size(self):
        """For size << pool, doubling size ≈ doubles fee share (within 5%)."""
        sz1, sz2 = 100, 200
        fs1 = effective_fee_share(sz1, L_RAW_10M, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC)
        fs2 = effective_fee_share(sz2, L_RAW_10M, PRICE, RANGE_PCT, DEC0_ETH, DEC1_USDC)
        ratio = fs2 / fs1
        assert math.isclose(ratio, 2.0, rel_tol=0.05), (
            f"expected ~2x fee share, got {ratio:.4f}"
        )


# ---------------------------------------------------------------------------
# exit_conversion_cost_usd
# ---------------------------------------------------------------------------

class TestExitConversionCost:
    def test_zero_for_zero_value(self):
        assert exit_conversion_cost_usd(0, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC) == 0.0

    def test_at_least_fee_floor(self):
        v = 10_000.0
        cost = exit_conversion_cost_usd(v, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        assert cost >= v * FEE_TIER

    def test_strictly_above_fee_floor_when_pool_not_infinite(self):
        """With finite pool there is always some slippage → cost > fee floor."""
        v = 10_000.0
        cost = exit_conversion_cost_usd(v, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        assert cost > v * FEE_TIER

    def test_default_side_is_sell_base(self):
        v = 5_000.0
        cost_default = exit_conversion_cost_usd(v, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        cost_explicit = exit_conversion_cost_usd(v, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC, "sell_base")
        assert math.isclose(cost_default, cost_explicit, rel_tol=1e-12)

    def test_deeper_pool_lower_cost(self):
        v = 50_000.0
        cost_shallow = exit_conversion_cost_usd(v, L_RAW_1M,  PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        cost_deep    = exit_conversion_cost_usd(v, L_RAW_10M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        assert cost_deep < cost_shallow


# ---------------------------------------------------------------------------
# roundtrip_cost_usd
# ---------------------------------------------------------------------------

class TestRoundtripCost:
    def test_zero_for_zero_size(self):
        assert roundtrip_cost_usd(0, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC) == 0.0

    def test_equals_entry_plus_exit(self):
        sz = 10_000.0
        rt = roundtrip_cost_usd(sz, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        entry = exit_conversion_cost_usd(sz, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC, "buy_base")
        exit_ = exit_conversion_cost_usd(sz, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC, "sell_base")
        assert math.isclose(rt, entry + exit_, rel_tol=1e-12)

    def test_exceeds_double_fee_floor_when_slippage_nonzero(self):
        """rt > 2 * size * fee_tier whenever there is any slippage."""
        sz = 50_000.0
        rt = roundtrip_cost_usd(sz, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
        assert rt > 2 * sz * FEE_TIER

    def test_increasing_in_size(self):
        costs = [
            roundtrip_cost_usd(sz, L_RAW_1M, PRICE, FEE_TIER, DEC0_ETH, DEC1_USDC)
            for sz in [1_000, 5_000, 25_000]
        ]
        for a, b in zip(costs, costs[1:]):
            assert b > a, f"roundtrip cost must increase with size: {a} >= {b}"
