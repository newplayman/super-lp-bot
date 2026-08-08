"""Pure paired tests for the read-only volatility range sizer."""

import math

import pytest

from scripts.lp_vol_range_sizer_v1_readonly import (
    DEFAULT_K,
    H_GRID,
    daily_vol_from_closes,
    recommend_range_pct,
)


def test_recommend_range_pct_matches_volatility_horizon_formula():
    sigma_daily = 0.03
    horizon_days = 14

    got = recommend_range_pct(sigma_daily, horizon_days)

    assert got == pytest.approx(
        100.0 * DEFAULT_K * sigma_daily * math.sqrt(horizon_days)
    )


def test_recommend_range_pct_scales_linearly_with_pair_volatility():
    low = recommend_range_pct(0.01, 30)
    high = recommend_range_pct(0.04, 30)

    assert high == pytest.approx(4.0 * low)


def test_daily_vol_uses_pool_price_ratio_log_returns():
    # Each close is the pool-native token1/token0 ratio, not either token's USD
    # return. The expected value is therefore derived solely from ratio moves.
    ratio_closes = [(0, 2000.0), (1, 2100.0), (2, 1995.0)]
    log_returns = [math.log(2100.0 / 2000.0), math.log(1995.0 / 2100.0)]
    expected = math.sqrt(sum(r * r for r in log_returns) / len(log_returns)) * math.sqrt(24.0)

    sigma_daily, n_returns = daily_vol_from_closes(ratio_closes)

    assert n_returns == 2
    assert sigma_daily == pytest.approx(expected)


def test_daily_vol_is_invariant_to_ratio_orientation():
    token1_per_token0 = [(0, 2.0), (1, 2.2), (3, 1.98)]
    token0_per_token1 = [(bucket, 1.0 / ratio) for bucket, ratio in token1_per_token0]

    forward, forward_n = daily_vol_from_closes(token1_per_token0)
    inverse, inverse_n = daily_vol_from_closes(token0_per_token1)

    assert forward_n == inverse_n == 2
    assert forward == pytest.approx(inverse)


def test_h_grid_boundaries_remain_the_passive_research_grid():
    assert H_GRID == [7, 14, 30, 45, 60]
    assert H_GRID[0] == 7
    assert H_GRID[-1] == 60
    assert H_GRID == sorted(set(H_GRID))


def test_recommendations_widen_across_h_grid_boundaries():
    lower = recommend_range_pct(0.02, H_GRID[0])
    upper = recommend_range_pct(0.02, H_GRID[-1])

    assert lower > 0
    assert upper > lower
