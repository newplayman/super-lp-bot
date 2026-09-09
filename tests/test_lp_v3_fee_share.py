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


def test_liquidity_decimal_scale_canonical():
    # On-chain L = sqrt(x*y) in RAW units => scale is 10**((dec0+dec1)/2).
    # 18/6 (WETH-USDC) is unchanged vs the legacy 10**(dec0-dec1)=10**12 factor.
    liq_18_6 = position_liquidity_raw(1000, 1675.6, 2, 18, 6)
    assert 0.995 < liq_18_6 / 1.2278e15 < 1.005
    # 18/18: legacy used 10**0 and collapsed l_pos to ~O(1); canonical is 10**18.
    liq_18_18 = position_liquidity_raw(1.0, 100.0, 10, 18, 18)
    assert liq_18_18 > 1e15  # large, not O(1) -> fee share no longer ~0
    # 18/8 (cbBTC/WETH layout): canonical scale 10**13.
    liq_18_8 = position_liquidity_raw(1.0, 0.03, 7, 18, 8)
    assert liq_18_8 > 1e10


def test_quote_usd_per_token1_scaling_and_guards():
    # RH-02bb: quote=0.99 returns 207114224164452.517 (±1e-6 relative error)
    liq_default = position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6)
    liq_quote_1 = position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=1.0)
    assert liq_default == liq_quote_1

    liq_depeg = position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=0.99)
    expected = 207114224164452.517
    assert abs(liq_depeg - expected) / expected < 1e-6

    # Non-positive or non-finite quote guards fail closed to 0.0
    assert position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=0.0) == 0.0
    assert position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=-1.0) == 0.0
    assert position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=float("nan")) == 0.0
    assert position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6, quote_usd_per_token1=float("inf")) == 0.0

