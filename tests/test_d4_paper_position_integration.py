"""Integration tests for the UNHEDGED D4 PaperPosition accounting.

The delta hedge was removed (operator decision: a perp hedge does not survive
its own real-world frictions, and it was an agent-introduced addition). These
tests guard the LP-only accounting that remains: real fee accrual from swaps,
LP mark-to-market in the net, IL as a diagnostic only (no double count), and
the absence of any hedge/funding surface on the position object.

Read-only: no RPC, no wallet, no network. Pure object behaviour.
"""
import scripts.strategy_pivot_d4_realtime_paper_shadow_validation as d4

P0 = 1675.6          # entry ETH price (USD)
ENTRY_TICK = -202111  # ~ price 1675.6 on the 0xb2cc pool


def _pos():
    p = d4.PaperPosition(1000, 2)
    p.set_entry(ENTRY_TICK, 47237736, P0)
    return p


def _swap(tick, amount1_usdc_raw, block=47237800, liquidity=int(8e17)):
    return {"ok": True, "block": block, "tick": tick,
            "amount1": amount1_usdc_raw, "liquidity": liquidity}


def test_no_hedge_surface_on_position():
    # The hedge/funding API is gone entirely.
    p = _pos()
    for attr in ("hedge_eth_amount", "hedge_pnl_usd", "funding_pnl_usd",
                 "hedge_mode", "hedge_ratio", "hedge_notional_usd"):
        assert not hasattr(p, attr), f"{attr} should be removed"
    assert not hasattr(p, "accrue_funding")
    # PaperPosition no longer takes a hedge_mode kwarg.
    import inspect
    params = inspect.signature(d4.PaperPosition.__init__).parameters
    assert "hedge_mode" not in params
    assert "hedge_ratio" not in params


def test_eth_exposure_diagnostic_is_set_and_positive():
    # We still REPORT how much ETH the LP holds (exposure), we just don't hedge it.
    p = _pos()
    assert p.lp_eth_exposure > 0
    # ~half the position in ETH at entry for a symmetric range: ~0.29-0.30 ETH.
    assert 0.25 < p.lp_eth_exposure < 0.35
    # exposure shrinks as price rises toward the range top (V3 sells ETH).
    p.mark(P0 * 1.015)
    assert p.lp_eth_exposure < 0.30


def test_in_range_swap_accrues_fee_out_of_range_does_not():
    p = _pos()
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
    p = _pos()
    fee = p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))
    assert 0.0 < fee < 1.0


def test_net_is_lp_only_no_hedge_no_il_double_count():
    p = _pos()
    p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))
    p.accrue_reward(63.52, 24)
    p.mark(1778.9)
    expected = (p.lp_mtm_usd + p.accumulated_lp_fee_usd + p.reward_income_usd
                - p.rebalance_cost_usd - p.claim_gas_usd - p.gas_estimate_usd)
    assert abs(p.total_net() - expected) < 1e-9
    # estimated_il_usd is diagnostic (<=0) and must NOT be in the net.
    assert p.estimated_il_usd <= 1e-9


def test_mark_at_entry_is_flat():
    p = _pos()
    p.mark(P0)
    assert abs(p.lp_mtm_usd) < 1e-6


def test_up_move_in_range_lp_gains_fee_dominates_when_calm():
    # A small in-range up-move: LP mtm moves modestly, fees accrue. Net should be
    # driven by fee + reward, with no hedge leg masking it.
    p = _pos()
    # simulate a day of in-range $200k swaps
    total_fee = 0.0
    for _ in range(20):
        total_fee += p.apply_event(_swap(-202100, -200_000 * 10**6), int(8e17))
    p.accrue_reward(63.52, 24)
    p.mark(P0 * 1.005)  # +0.5%, still in range
    assert p.accumulated_lp_fee_usd == total_fee > 0
    # net contains exactly the LP-only components
    assert abs(p.total_net()
               - (p.lp_mtm_usd + p.accumulated_lp_fee_usd + p.reward_income_usd)) < 1e-9


def test_to_dict_has_no_hedge_keys():
    p = _pos()
    p.mark(P0)
    d = p.to_dict(P0)
    for k in ("hedge_pnl_usd", "funding_pnl_usd", "hedge_mode", "hedge_eth_amount", "hedge_ratio"):
        assert k not in d
    assert "lp_eth_exposure" in d
    assert "lp_mtm_usd" in d
