"""INV-IL-01/02 contracts for the read-only V3 inventory engine."""

from dataclasses import FrozenInstanceError, replace
import inspect

import pytest

from scripts.lp_il_inventory_engine_v1_readonly import (
    V3PositionState,
    alpha_vs_hodl,
    current_inventory,
    entry_baseline,
    hodl_nav,
    il_pct,
    il_usd,
    lp_nav_ex_fee,
    paper_entry_baseline,
    pnl_vs_usdc,
    position_state_from_capital,
)
from scripts.lp_portfolio_paper_runner_v1_readonly import init_state, mark_position, update_position


def _paper_position(*, price=100.0, capital=1_000.0, range_pct=10.0):
    baseline = paper_entry_baseline(price, capital, range_pct)
    state = position_state_from_capital(price, capital, range_pct)
    return baseline, state


def test_entry_baseline_is_frozen_and_swap_cost_is_independent():
    baseline = entry_baseline(2.0, 300.0, entry_swap_cost=1.25)
    assert hodl_nav(baseline, 100.0, 1.0) == pytest.approx(500.0)
    assert baseline.entry_swap_cost == 1.25
    with pytest.raises(FrozenInstanceError):
        baseline.q0_entry = 999.0

    other_cost = replace(baseline, entry_swap_cost=99.0)
    assert hodl_nav(other_cost, 100.0, 1.0) == hodl_nav(baseline, 100.0, 1.0)


def test_paper_entry_uses_actual_v3_leg_ratio_not_synthetic_fifty_fifty():
    baseline, state = _paper_position()
    token0_value = baseline.q0_entry * 100.0
    token1_value = baseline.q1_entry
    assert token0_value + token1_value == pytest.approx(1_000.0)
    assert token0_value != pytest.approx(500.0, abs=0.1)
    assert lp_nav_ex_fee(state, 100.0) == pytest.approx(1_000.0)


def test_same_price_ratio_has_zero_il():
    baseline, state = _paper_position()
    lp = lp_nav_ex_fee(state, 100.0)
    hodl = hodl_nav(baseline, 100.0, 1.0)
    assert il_usd(lp, hodl) == pytest.approx(0.0, abs=1e-9)
    assert il_pct(il_usd(lp, hodl), hodl) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("prices", [(100.0, 105.0, 110.0, 125.0), (100.0, 95.0, 90.0, 75.0)])
def test_absolute_il_is_monotone_as_price_moves_away_in_one_direction(prices):
    baseline, state = _paper_position()
    values = [abs(il_usd(lp_nav_ex_fee(state, p), hodl_nav(baseline, p, 1.0))) for p in prices]
    assert values == sorted(values)


def test_out_of_range_inventory_is_one_sided_but_il_keeps_moving():
    baseline, state = _paper_position()
    inv1 = current_inventory(state, 120.0)
    inv2 = current_inventory(state, 160.0)
    assert inv1.q0 == 0.0 and inv2.q0 == 0.0
    assert inv1.q1 == pytest.approx(inv2.q1)
    il1 = il_usd(inv1.nav_quote, hodl_nav(baseline, 120.0, 1.0))
    il2 = il_usd(inv2.nav_quote, hodl_nav(baseline, 160.0, 1.0))
    assert il1 != pytest.approx(il2)
    assert abs(il2) > abs(il1)


def test_lp_nav_api_has_no_fee_or_reward_parameters_and_ignores_mapping_extras():
    assert tuple(inspect.signature(lp_nav_ex_fee).parameters) == ("state", "price")
    _, state = _paper_position()
    plain = lp_nav_ex_fee(state, 105.0)
    injected = lp_nav_ex_fee({
        "liquidity": state.liquidity,
        "price_lower": state.price_lower,
        "price_upper": state.price_upper,
        "fee_quote": 1_000_000.0,
        "reward_quote": 2_000_000.0,
    }, 105.0)
    assert injected == pytest.approx(plain)


def test_pnl_vs_usdc_and_alpha_vs_hodl_can_have_opposite_signs():
    assert pnl_vs_usdc(1_050.0, 1_000.0) == 50.0
    assert alpha_vs_hodl(1_050.0, 1_200.0) == -150.0


@pytest.mark.parametrize(
    "call",
    [
        lambda: entry_baseline(-1.0, 2.0),
        lambda: paper_entry_baseline(0.0, 100.0, 10.0),
        lambda: paper_entry_baseline(1.0, 0.0, 10.0),
        lambda: paper_entry_baseline(1.0, 100.0, 0.0),
        lambda: paper_entry_baseline(1.0, 100.0, 100.0),
        lambda: V3PositionState(liquidity=-1.0, price_lower=1.0, price_upper=2.0),
        lambda: lp_nav_ex_fee({"liquidity": 1.0, "price_lower": 1.0, "price_upper": 2.0}, float("nan")),
    ],
)
def test_invalid_inputs_fail_closed(call):
    with pytest.raises(ValueError):
        call()


def test_zero_hodl_denominator_is_explicit():
    with pytest.raises(ZeroDivisionError):
        il_pct(-1.0, 0.0)


def test_runner_initializes_immutable_baseline_and_exposes_three_denominators():
    state = init_state(
        capital=1_000.0,
        anchor=100.0,
        range_pct=10.0,
        fee_tier=0.003,
        dec0=18,
        dec1=6,
        last_block=0,
        entry_swap_cost=1.5,
    )
    assert state["entry_baseline"].entry_swap_cost == 1.5
    assert state["entry_baseline"].q0_entry * 100.0 != pytest.approx(500.0, abs=0.1)

    state["fees_quote"] = 10.0
    state["reward_quote"] = 20.0
    mark = mark_position(state, 125.0)
    assert mark["lp_nav_ex_fee_quote"] == mark["lp_value_quote"]
    assert mark["il_vs_hodl_quote"] == mark["il_quote"]
    assert mark["current_total_nav_quote"] == pytest.approx(mark["lp_nav_ex_fee_quote"] + 30.0)
    assert mark["pnl_vs_usdc_quote"] == pytest.approx(mark["current_total_nav_quote"] - 1_000.0)
    assert mark["alpha_vs_hodl_quote"] == pytest.approx(
        mark["current_total_nav_quote"] - mark["hodl_nav_quote"]
    )


def test_runner_fee_reward_do_not_change_lp_nav_or_il():
    state = init_state(
        capital=1_000.0, anchor=100.0, range_pct=10.0, fee_tier=0.003,
        dec0=18, dec1=6, last_block=0,
    )
    before = mark_position(state, 105.0)
    state["fees_quote"] = 333.0
    state["reward_quote"] = 444.0
    after = mark_position(state, 105.0)
    assert after["lp_nav_ex_fee_quote"] == before["lp_nav_ex_fee_quote"]
    assert after["il_vs_hodl_quote"] == before["il_vs_hodl_quote"]


def test_runner_exit_keeps_current_hodl_and_il_semantics_truthful():
    state = init_state(
        capital=1_000.0, anchor=100.0, range_pct=10.0, fee_tier=0.003,
        dec0=18, dec1=6, last_block=0, exit_on_breach=True,
    )
    update_position(state, [{"block": 1, "price": 120.0, "amount1": 1}], now_block=1)
    mark_120 = mark_position(state, 120.0)
    mark_160 = mark_position(state, 160.0)
    assert mark_120["lp_value_quote"] == mark_160["lp_value_quote"]  # legacy cash field
    assert mark_120["hodl_nav_quote"] != mark_160["hodl_nav_quote"]
    assert mark_120["il_vs_hodl_quote"] != mark_160["il_vs_hodl_quote"]
    assert mark_160["alpha_vs_hodl_quote"] == pytest.approx(
        mark_160["current_total_nav_quote"] - mark_160["hodl_nav_quote"]
    )
