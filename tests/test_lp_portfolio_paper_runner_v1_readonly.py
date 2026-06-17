"""Pure tests for the multi-pool LP paper-shadow runner (no network)."""
from scripts.lp_portfolio_paper_runner_v1_readonly import (
    init_state,
    update_position,
    mark_position,
    accrue_reward,
)

DEC = 18
FEE = 0.003
R = 10.0
L = 10 ** 18
AMT1 = 10 ** 18  # 1.0 token1 raw


def _state(cap=1000.0, anchor=1.0):
    return init_state(capital=cap, anchor=anchor, range_pct=R,
                      fee_tier=FEE, dec0=DEC, dec1=DEC, last_block=0)


def test_in_range_swaps_accrue_fees_anchor_unchanged():
    st = _state()
    swaps = [
        {"block": 1, "price": 1.00, "liquidity": L, "amount1": AMT1},
        {"block": 2, "price": 1.03, "liquidity": L, "amount1": AMT1},
    ]
    update_position(st, swaps, now_block=2)
    assert st["fees_quote"] > 0
    assert st["breaches"] == []
    assert st["anchor"] == 1.0          # passive: anchor never moves
    assert st["last_block"] == 2
    assert st["in_range_now"] is True


def test_net_rises_with_fees():
    st = _state()
    before = mark_position(st, 1.0)["net_quote"]
    update_position(st, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=1)
    after = mark_position(st, 1.0)["net_quote"]
    assert after > before


def test_out_of_range_swap_no_fee_records_breach_no_rebalance():
    st = _state()
    update_position(st, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=1)
    fees_in = st["fees_quote"]
    update_position(st, [{"block": 2, "price": 1.5, "liquidity": L, "amount1": AMT1}], now_block=2)
    assert st["fees_quote"] == fees_in          # out-of-range accrues nothing
    assert len(st["breaches"]) == 1
    assert st["anchor"] == 1.0                   # no rebalance
    assert st["in_range_now"] is False


def test_breach_logged_once_per_crossing():
    st = _state()
    swaps = [
        {"block": 1, "price": 1.5, "liquidity": L, "amount1": AMT1},   # cross out
        {"block": 2, "price": 1.6, "liquidity": L, "amount1": AMT1},   # still out -> no new breach
        {"block": 3, "price": 1.0, "liquidity": L, "amount1": AMT1},   # back in
        {"block": 4, "price": 1.5, "liquidity": L, "amount1": AMT1},   # cross out again
    ]
    update_position(st, swaps, now_block=4)
    assert len(st["breaches"]) == 2             # two crossings, not four out-ticks


def test_swaps_at_or_before_last_block_ignored():
    st = _state()
    st["last_block"] = 5
    update_position(st, [{"block": 5, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=6)
    assert st["fees_quote"] == 0.0              # block 5 not > last_block 5


def test_mark_position_roundtrip_il_zero_move_negative():
    st = _state()
    mk0 = mark_position(st, 1.0)
    assert abs(mk0["il_quote"]) < 1e-6          # at anchor IL ~ 0
    mk1 = mark_position(st, 1.2)
    assert mk1["il_quote"] < 0                  # price move => IL < 0


def test_mark_position_net_pct_consistent():
    st = _state(cap=2000.0)
    st["fees_quote"] = 20.0
    mk = mark_position(st, 1.0)
    assert abs(mk["net_quote"] - 20.0) < 1e-6   # value==cap at anchor, +fees
    assert abs(mk["net_pct"] - 1.0) < 1e-9      # 20/2000 = 1%


def test_accrue_reward_linear_and_zero_at_zero():
    assert accrue_reward(1000.0, 50.0, 0) == 0.0
    full = accrue_reward(1000.0, 50.0, 365 * 86400)
    assert abs(full - 500.0) < 1e-6             # 50% APR, 1y, 1000 => 500
    half = accrue_reward(1000.0, 50.0, 365 * 86400 / 2)
    assert abs(half * 2 - full) < 1e-9          # linear in time
    assert abs(accrue_reward(2000.0, 50.0, 365 * 86400) - 1000.0) < 1e-6  # linear in capital


def test_init_state_shape():
    st = _state()
    for k in ("capital", "anchor", "range_pct", "fee_tier", "dec0", "dec1",
              "l_pos_raw", "fees_quote", "reward_quote", "last_block",
              "breaches", "in_range_now"):
        assert k in st
    assert st["l_pos_raw"] > 0
    assert st["breaches"] == [] and st["in_range_now"] is True
