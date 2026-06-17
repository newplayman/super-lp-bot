"""Tests for the Tier-C exit-feasibility analyzer (read-only, no network).

These pin the verdict logic that answers the decisive Tier-C question: when a
new-token pool breaks its LP range lower bound, was the stop-loss actually
executable, or did price gap through the floor / liquidity collapse so the stop
could never fill there? The analyzer is pure; tests drive it with synthetic
swap streams covering each canonical outcome.
"""
import math

import scripts.lp_tier_c_exit_feasibility_v1_readonly as m


def test_price_from_sqrt_x96_weth_usdc():
    # 0xb2cc convention: token0=WETH(18), token1=USDC(6) -> USDC per WETH.
    # sqrtPriceX96 for ~price 1795: pick a value and check round-trip magnitude.
    # raw = (sp/2**96)**2 ; human = raw * 10**(18-6)
    target = 1795.0
    raw = target / (10 ** (18 - 6))
    sp = int(math.sqrt(raw) * (2 ** 96))
    got = m.price_from_sqrt_x96(sp, 18, 6)
    assert abs(got - target) / target < 1e-3


def test_decoder_signed_amounts_and_tick():
    # build a data blob: amount0 negative, amount1 positive, sqrt/L/tick set.
    def w(v):
        return format(v & ((1 << 256) - 1), "064x")
    amount0 = -123456
    amount1 = 789
    sp = 12345678901234567890
    liq = 10 ** 18
    tick = -202111
    data = "0x" + w(amount0) + w(amount1) + w(sp) + w(liq) + w(tick)
    d = m.decode_v3_swap_data(data)
    assert d["amount0"] == amount0
    assert d["amount1"] == amount1
    assert d["sqrt_price_x96"] == sp
    assert d["liquidity"] == liq
    assert d["tick"] == tick


def _streams():
    return m.synthetic_streams(entry=1.0)


def test_no_breach_when_price_stays_in_range():
    r = m.analyze_exit_feasibility(_streams()["no_breach"], entry_price=1.0, range_pct=5.0)
    assert r["verdict"] == "NO_BREACH"
    assert r["breached"] is False


def test_clean_continuous_decline_is_exitable():
    # gentle decline straddling the floor with stable liquidity -> exitable.
    r = m.analyze_exit_feasibility(_streams()["clean"], entry_price=1.0, range_pct=5.0)
    assert r["breached"] is True
    assert r["verdict"] == "EXITABLE_CLEAN"
    assert r["gap_through_pct"] < m.GAP_DEGRADED
    assert r["liq_collapse_ratio"] < m.COLLAPSE_UNEXITABLE


def test_price_gap_through_floor_is_flagged_gapped():
    # one swap teleports ~39% below the floor: a resting floor stop fills far
    # worse than the floor (no near-floor fills at all) -> GAPPED.
    r = m.analyze_exit_feasibility(_streams()["gapped"], entry_price=1.0, range_pct=5.0)
    assert r["breached"] is True
    assert r["verdict"] == "GAPPED"
    assert m.GAP_DEGRADED <= r["gap_through_pct"] < m.GAP_UNEXITABLE
    assert r["near_floor_fills"] == 0  # no chance to exit near the floor


def test_severe_gap_past_half_is_unexitable():
    # teleport >50% below floor: treated as unexitable (price was never near floor).
    L = 10 ** 18
    swaps = [
        {"price": 1.00, "liquidity": L, "block": 0},
        {"price": 0.97, "liquidity": L, "block": 1},
        {"price": 0.40, "liquidity": L, "block": 2},  # ~58% below 0.95 floor
    ]
    r = m.analyze_exit_feasibility(swaps, entry_price=1.0, range_pct=5.0)
    assert r["verdict"] == "UNEXITABLE"
    assert r["gap_through_pct"] >= m.GAP_UNEXITABLE


def test_liquidity_collapse_is_unexitable():
    r = m.analyze_exit_feasibility(_streams()["collapse"], entry_price=1.0, range_pct=5.0)
    assert r["breached"] is True
    assert r["verdict"] == "UNEXITABLE"
    assert r["liq_collapse_ratio"] >= m.COLLAPSE_UNEXITABLE


def test_moderate_gap_is_flagged_gapped_not_clean():
    # cross floor (0.95) and land ~12% below it, stable liquidity: GAPPED.
    L = 10 ** 18
    swaps = [
        {"price": 1.00, "liquidity": L, "block": 0},
        {"price": 0.96, "liquidity": L, "block": 1},
        {"price": 0.835, "liquidity": L, "block": 2},  # ~12% below 0.95 floor
        {"price": 0.83, "liquidity": L, "block": 3},
    ]
    r = m.analyze_exit_feasibility(swaps, entry_price=1.0, range_pct=5.0)
    assert r["verdict"] == "GAPPED"
    assert m.GAP_DEGRADED <= r["gap_through_pct"] < m.GAP_UNEXITABLE


def test_realized_loss_vs_floor_tracks_post_breach_dump():
    # exit price reported is the worst within the dump lookahead window.
    L = 10 ** 18
    swaps = [
        {"price": 1.00, "liquidity": L, "block": 0},
        {"price": 0.96, "liquidity": L, "block": 1},
        {"price": 0.945, "liquidity": L, "block": 2},  # just below 0.95 floor
        {"price": 0.70, "liquidity": L, "block": 3},   # dump continues
    ]
    r = m.analyze_exit_feasibility(swaps, entry_price=1.0, range_pct=5.0)
    assert r["breached"] is True
    assert r["realized_exit_price"] == 0.70
    # realized loss vs floor 0.95 ~ (0.95-0.70)/0.95 ~ 26%
    assert r["realized_loss_vs_floor_pct"] > 0.2


def test_empty_stream_is_no_data():
    r = m.analyze_exit_feasibility([], entry_price=1.0, range_pct=5.0)
    assert r["verdict"] == "NO_DATA"
