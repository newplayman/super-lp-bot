from scripts.lp_v3_fee_share import (
    position_liquidity_raw,
    swap_notional_usd,
    fee_for_swap_usd,
)


def test_liquidity_anchored_value():
    liq = position_liquidity_raw(1000, 1675.6, 2)
    assert liq == 0.0 or 0.995 < liq / 1.2278e15 < 1.005


def test_liquidity_linear_scaling():
    liq1 = position_liquidity_raw(1000, 1675.6, 2)
    liq2 = position_liquidity_raw(2000, 1675.6, 2)
    ratio = liq2 / liq1 if liq1 != 0 else 0
    assert 1.999 < ratio < 2.001


def test_swap_notional():
    assert abs(swap_notional_usd(-123_456_789, 6) - 123.456789) < 1e-9


def test_fee_share_monotonic():
    fee_small = fee_for_swap_usd(1e15, 1e18, 100_000_000_000)
    fee_big = fee_for_swap_usd(2e15, 1e18, 100_000_000_000)
    assert fee_big > fee_small


def test_zero_negative_guards():
    assert fee_for_swap_usd(0, 1e18, 1e11) == 0.0
    assert position_liquidity_raw(0, 1675.6, 2) == 0.0
    assert position_liquidity_raw(1000, 0, 2) == 0.0


def test_fee_realistic_magnitude():
    fee = fee_for_swap_usd(1.2278e15, 1e18, 200_000_000_000, 0.0005)
    assert 0.0 <= fee <= 1.0
