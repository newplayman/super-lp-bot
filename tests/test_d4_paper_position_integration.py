"""Integration tests for the corrected D4 PaperPosition two-leg accounting.

These guard the fixes made after the original D4 run was found to be
instrumentation-broken (LP leg uninstrumented: fee/IL read 0 while only the
hedge was marked). They assert: real fee accrual from swaps, LP
mark-to-market in the net, no IL double-counting, and that the dynamic-delta
hedge offsets the LP delta better than the static notional hedge.

Read-only: no RPC, no wallet, no network. Pure object behaviour.
"""
import scripts.strategy_pivot_d4_realtime_paper_shadow_validation as d4

P0 = 1675.6          # entry ETH price (USD)
ENTRY_TICK = -202111  # ~ price 1675.6 on the 0xb2cc pool


def _pos(mode):
    p = d4.PaperPosition(1000, 2, hedge_mode=mode)
    p.set_entry(ENTRY_TICK, 47237736, P0)
    return p


def _swap(tick, amount1_usdc_raw, block=47237800, liquidity=int(8e17)):
    return {"ok": True, "block": block, "tick": tick,
            "amount1": amount1_usdc_raw, "liquidity": liquidity}


def test_entry_hedge_static_over_hedges_vs_dynamic():
    # Static shorts 0.75*notional/price ETH; dynamic shorts 0.75*actual LP delta,
    # which is smaller because the LP holds only ~half its value in WETH.
    ps, pd = _pos("static"), _pos("dynamic")
    assert ps.hedge_eth_amount < 0 and pd.hedge_eth_amount < 0
    assert abs(pd.hedge_eth_amount) < abs(ps.hedge_eth_amount)
    # static ~ -0.4476, dynamic ~ -0.2216
    assert 0.40 < abs(ps.hedge_eth_amount) < 0.50
    assert 0.18 < abs(pd.hedge_eth_amount) < 0.26


def test_in_range_swap_accrues_fee_out_of_range_does_not():
    p = _pos("static")
    fee = p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))  # in range, $200k
    assert fee > 0
    assert p.events_seen == 1
    assert p.accumulated_lp_fee_usd == fee
    # out-of-range swap (tick above upper bound): no fee, marks not-in-range
    f2 = p.apply_event(_swap(-201000, -50_000 * 10**6), int(8e17))
    assert f2 == 0.0
    assert p.in_range is False
    assert p.events_seen == 2  # still counted as seen


def test_fee_share_is_realistic_not_proxy():
    # The old bug used a ~1.8%/day proxy. Real share of a $200k swap for a
    # $1000 position in an ~$800M-liquidity pool is sub-dollar.
    p = _pos("static")
    fee = p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))
    assert 0.0 < fee < 1.0


def test_net_identity_no_il_double_count():
    p = _pos("static")
    p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))
    p.accrue_reward(63.52, 24)
    p.accrue_funding(0.83, 24)
    p.mark(1778.9)
    expected = (p.lp_mtm_usd + p.accumulated_lp_fee_usd + p.reward_income_usd
                - p.rebalance_cost_usd - p.claim_gas_usd - p.gas_estimate_usd
                + p.hedge_pnl_usd + p.funding_pnl_usd)
    assert abs(p.total_net() - expected) < 1e-9
    # estimated_il_usd is diagnostic (<=0) and must NOT be in the net.
    assert p.estimated_il_usd <= 1e-9


def test_mark_at_entry_is_flat():
    p = _pos("dynamic")
    p.mark(P0)
    assert abs(p.lp_mtm_usd) < 1e-6
    assert abs(p.hedge_pnl_usd) < 1e-6


def test_dynamic_hedge_offsets_lp_delta_better_than_static():
    # Modest +1% move keeps the LP in range. The combined LP+hedge residual
    # must be smaller for the dynamic hedge than the static (over-)hedge, and
    # the hedge must actually offset (residual < bare LP move).
    ps, pd = _pos("static"), _pos("dynamic")
    P1 = P0 * 1.01
    ps.mark(P1)
    pd.mark(P1)
    res_static = abs(ps.lp_mtm_usd + ps.hedge_pnl_usd)
    res_dynamic = abs(pd.lp_mtm_usd + pd.hedge_pnl_usd)
    lp_only = abs(pd.lp_mtm_usd)
    assert res_dynamic < res_static
    assert res_dynamic < lp_only


def test_dynamic_beats_static_on_trending_up_move():
    # On a large up-move that exits the range top, dynamic loses materially
    # less than the static notional short (the documented finding).
    ps, pd = _pos("static"), _pos("dynamic")
    for p in (ps, pd):
        p.accrue_reward(63.52, 24)
        p.accrue_funding(0.83, 24)
        p.mark(1778.9)
    assert pd.total_net() > ps.total_net()
    assert ps.total_net() < 0  # static is clearly negative on a trend
