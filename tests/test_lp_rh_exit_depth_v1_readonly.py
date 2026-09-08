import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal
from pathlib import Path
import json

import pytest

from scripts import lp_rh_exit_depth_v1_readonly as mod


def _pool(**changes):
    state = {
        "sqrt_price_x96": mod.Q96,
        "current_tick": 0,
        "tick_spacing": 1,
        "fee_pips": 0,
        "liquidity": 10**18,
        "tick_data": [mod.TickRange(-100000, 100000, 10**18)],
        "zero_for_one": True,
    }
    state.update(changes)
    return state


def test_sqrt_price_at_zero_is_q96():
    assert mod.sqrt_price_x96_at_tick(0) == 2**96


@pytest.mark.parametrize("tick", [-887272, -198118, -1, 0, 1, 100000, 887272])
def test_tick_round_trip(tick):
    assert mod.tick_at_sqrt_price_x96(mod.sqrt_price_x96_at_tick(tick)) == tick


def test_observed_pool_tick_round_trip():
    assert mod.tick_at_sqrt_price_x96(3953938817749275760872870) == -198118


def test_amount0_doubles_with_liquidity():
    a, b = mod.sqrt_price_x96_at_tick(-10), mod.sqrt_price_x96_at_tick(10)
    one = mod.amount0_delta(a, b, 10**18, False)
    two = mod.amount0_delta(a, b, 2 * 10**18, False)
    assert two == 2 * one


def test_amount1_doubles_with_liquidity():
    a, b = mod.sqrt_price_x96_at_tick(-10), mod.sqrt_price_x96_at_tick(10)
    one = mod.amount1_delta(a, b, 10**18, False)
    two = mod.amount1_delta(a, b, 2 * 10**18, False)
    assert two == 2 * one


def test_deltas_are_monotonic_when_range_widens():
    mid = mod.sqrt_price_x96_at_tick(0)
    narrow = mod.sqrt_price_x96_at_tick(5)
    wide = mod.sqrt_price_x96_at_tick(10)
    assert mod.amount0_delta(mid, wide, 10**18, False) > mod.amount0_delta(mid, narrow, 10**18, False)
    assert mod.amount1_delta(mid, wide, 10**18, False) > mod.amount1_delta(mid, narrow, 10**18, False)


def test_round_up_is_not_below_round_down():
    a, b = mod.sqrt_price_x96_at_tick(-3), mod.sqrt_price_x96_at_tick(7)
    assert mod.amount0_delta(a, b, 123456789, True) >= mod.amount0_delta(a, b, 123456789, False)
    assert mod.amount1_delta(a, b, 123456789, True) >= mod.amount1_delta(a, b, 123456789, False)


def test_small_single_tick_swap_has_no_crossing_and_low_impact():
    result = mod.simulate_exit_swap(amount_in=10**12, **_pool())
    assert result["ticks_crossed"] == 0
    assert result["price_impact_bps"] < Decimal("10")
    assert result["amount_out"] > 0


def test_reverse_direction_moves_price_up():
    state = _pool()
    down = mod.simulate_exit_swap(amount_in=10**12, **state)
    state["zero_for_one"] = False
    up = mod.simulate_exit_swap(amount_in=10**12, **state)
    assert down["sqrt_price_after"] < state["sqrt_price_x96"]
    assert up["sqrt_price_after"] > state["sqrt_price_x96"]


def test_cross_tick_updates_liquidity_and_stops_in_next_segment():
    liquidity = 10**18
    ticks = [mod.TickRange(-40, -20, liquidity // 2),
             mod.TickRange(-20, 20, liquidity)]
    first = mod.amount0_delta(mod.sqrt_price_x96_at_tick(-20), mod.Q96,
                              liquidity, True)
    extra = mod.amount0_delta(mod.sqrt_price_x96_at_tick(-40),
                              mod.sqrt_price_x96_at_tick(-20), liquidity // 2, True)
    result = mod.simulate_exit_swap(
        sqrt_price_x96=mod.Q96, current_tick=0, tick_spacing=1, fee_pips=0,
        liquidity=liquidity, tick_data=ticks, amount_in=first + extra // 2,
        zero_for_one=True)
    assert result["ticks_crossed"] == 1
    assert mod.sqrt_price_x96_at_tick(-40) < result["sqrt_price_after"] < mod.sqrt_price_x96_at_tick(-20)
    assert result["liquidity_exhausted"] is False


def test_reverse_cross_tick_uses_upward_net():
    liquidity = 10**18
    ticks = [mod.TickRange(0, 20, liquidity), mod.TickRange(20, 40, liquidity // 2)]
    first = mod.amount1_delta(mod.Q96, mod.sqrt_price_x96_at_tick(20), liquidity, True)
    extra = mod.amount1_delta(mod.sqrt_price_x96_at_tick(20),
                              mod.sqrt_price_x96_at_tick(30), liquidity // 2, True)
    result = mod.simulate_exit_swap(
        sqrt_price_x96=mod.Q96, current_tick=0, tick_spacing=1, fee_pips=0,
        liquidity=liquidity, tick_data=ticks, amount_in=first + extra // 2,
        zero_for_one=False)
    assert result["ticks_crossed"] == 1
    assert mod.sqrt_price_x96_at_tick(20) < result["sqrt_price_after"] < mod.sqrt_price_x96_at_tick(40)


def test_tick_data_exhaustion_is_explicit():
    liquidity = 10**18
    ticks = [mod.TickRange(-10, 10, liquidity)]
    amount = mod.amount0_delta(mod.sqrt_price_x96_at_tick(-10), mod.Q96,
                                liquidity, True) + 1
    result = mod.simulate_exit_swap(
        sqrt_price_x96=mod.Q96, current_tick=0, tick_spacing=1, fee_pips=0,
        liquidity=liquidity, tick_data=ticks, amount_in=amount,
        zero_for_one=True)
    assert result["liquidity_exhausted"] is True
    assert result["amount_out"] > 0


def test_t24_empty_tick_data_is_unavailable_not_zero():
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **_pool(tick_data=[]))
    assert result["sufficient"] is False
    assert result["reason"] == "INPUTS_UNAVAILABLE: EXIT_QUOTE"
    assert result["max_exit_usd"] is None


def test_missing_required_pool_state_is_fail_closed():
    # RH-05h narrowed the sub-reason from EXIT_QUOTE to MISSING_KEYS so a caller
    # can tell a typo from genuinely absent chain data. The contract this test
    # guards -- absent pool state fails closed with no number -- is unchanged,
    # and the assertion is tightened to name the keys rather than loosened.
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     tick_data=[mod.TickRange(-10, 10, 10**18)])
    assert result["max_exit_usd"] is None
    assert result["impact_at_size_bps"] is None
    assert result["sufficient"] is False
    assert result["reason"] == "INPUTS_UNAVAILABLE: MISSING_KEYS"
    assert result["missing_keys"] == ["current_tick", "fee_pips", "liquidity",
                                      "sqrt_price_x96", "tick_spacing"]


def test_exit_depth_insufficient_when_impact_limit_is_tight():
    result = mod.exit_depth_for_size(
        position_value_usd=Decimal("100000000000000000"),
        max_impact_bps=Decimal("10"),
        **_pool(token0_decimals=0, input_price_usd=1,
                tick_data=[mod.TickRange(-100000, 100000, 10**18)]))
    assert result["sufficient"] is False
    assert result["reason"] == "EXIT_DEPTH_INSUFFICIENT"
    assert result["max_exit_usd"] < Decimal("100000000000000000")


def test_measured_cap_without_data_is_none():
    assert mod.measured_exit_depth_cap(tick_data=[]) is None


def test_measured_cap_with_quote_is_decimal():
    cap = mod.measured_exit_depth_cap(
        position_value_usd=Decimal("1000000000000"),
        max_impact_bps=Decimal("100"),
        **_pool(token0_decimals=0, input_price_usd=1))
    assert isinstance(cap, Decimal)
    assert cap > 0


def test_tighter_slippage_limit_reduces_max_exit():
    state = _pool(token0_decimals=0, input_price_usd=1)
    tight = mod.exit_depth_for_size(position_value_usd=Decimal("100000000000000000"),
                                    max_impact_bps=Decimal("10"), **state)
    loose = mod.exit_depth_for_size(position_value_usd=Decimal("100000000000000000"),
                                    max_impact_bps=Decimal("100"), **state)
    assert tight["max_exit_usd"] < loose["max_exit_usd"]


def test_constant_liquidity_would_overestimate_after_drop():
    liquidity = 10**18
    reduced = 10**15
    ticks = [mod.TickRange(-200, -100, reduced),
             mod.TickRange(-100, 100, liquidity)]
    first = mod.amount0_delta(mod.sqrt_price_x96_at_tick(-100), mod.Q96,
                              liquidity, True)
    extra = mod.amount0_delta(mod.sqrt_price_x96_at_tick(-150),
                              mod.sqrt_price_x96_at_tick(-100), reduced, True)
    amount = first + extra // 2
    result = mod.simulate_exit_swap(
        sqrt_price_x96=mod.Q96, current_tick=0, tick_spacing=1, fee_pips=0,
        liquidity=liquidity, tick_data=ticks, amount_in=amount,
        zero_for_one=True)
    denominator = liquidity * mod.Q96 + amount * mod.Q96
    naive_sqrt = (liquidity * mod.Q96 * mod.Q96 + denominator - 1) // denominator
    naive = mod.amount1_delta(naive_sqrt, mod.Q96, liquidity, False)
    assert result["amount_out"] < naive  # prevents systematic depth overestimation


def test_fee_is_reported_separately_from_net_effective_price():
    state = _pool(fee_pips=3000)
    result = mod.simulate_exit_swap(amount_in=10**12, **state)
    assert result["fee_paid"] > 0
    assert result["fee_paid"] < 10**12
    assert result["effective_price"] > 0


def test_mapping_tick_data_is_accepted():
    state = _pool(tick_data=[{"tick_lower": -100000, "tick_upper": 100000,
                              "liquidity_net": 10**18}])
    result = mod.simulate_exit_swap(
        amount_in=10**12,
        **state)
    assert result["amount_out"] > 0


def test_cli_writes_decimal_result(tmp_path):
    state = _pool(token0_decimals=0, input_price_usd=1)
    state["tick_data"] = [{"tick_lower": -100000, "tick_upper": 100000,
                            "liquidity_net": 10**18}]
    source = tmp_path / "pool.json"
    output = tmp_path / "quote.json"
    source.write_text(json.dumps(state))
    import subprocess
    subprocess.run([
        "/root/lp-bot/.venv/bin/python", str(Path(mod.__file__)),
        "--pool-state-json", str(source), "--position-usd", "1000",
        "--max-impact-bps", "100", "--out", str(output)], check=True)
    payload = json.loads(output.read_text())
    assert payload["sufficient"] is True


def test_source_has_no_float_money_math_or_network_imports():
    source = Path(mod.__file__).read_text()
    assert "float(" not in source
    assert "urllib" not in source
    assert "requests" not in source
    assert "web3" not in source


# --- RH-05h: state-semantics fixes (MISSING_KEYS / PRICE_OR_DECIMALS / COMPUTED_FAIL) ---

def test_missing_current_tick_reports_missing_keys():
    state = _pool()
    del state["current_tick"]
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "MISSING_KEYS" in result["reason"]
    assert result["missing_keys"] == ["current_tick"]
    assert result["max_exit_usd"] is None


def test_missing_fee_pips_and_liquidity_listed_in_order():
    state = _pool()
    del state["fee_pips"]
    del state["liquidity"]
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "MISSING_KEYS" in result["reason"]
    assert result["missing_keys"] == ["fee_pips", "liquidity"]


def test_misspelled_tick_key_still_reports_missing_current_tick():
    # Reproduces the main-brain's three wasted runs: `tick` instead of `current_tick`.
    state = _pool()
    del state["current_tick"]
    state["tick"] = 0
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "MISSING_KEYS" in result["reason"]
    assert "current_tick" in result["missing_keys"]


def test_missing_token0_decimals_is_price_or_decimals():
    state = _pool(token0_price_usd=1)  # side price present, decimals absent
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "PRICE_OR_DECIMALS" in result["reason"]
    assert result["max_exit_usd"] is None


def test_missing_all_price_sources_is_price_or_decimals():
    state = _pool(token0_decimals=0)  # decimals present, no price at all
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "PRICE_OR_DECIMALS" in result["reason"]
    assert result["max_exit_usd"] is None


def test_explicit_price_cannot_substitute_for_decimals():
    state = _pool(input_price_usd=1)  # explicit price, but no decimals
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert "PRICE_OR_DECIMALS" in result["reason"]
    assert result["max_exit_usd"] is None


def _exhausted_pool():
    liquidity = 10**18
    ticks = [mod.TickRange(-10, 10, liquidity)]
    # One wei past the range's full capacity: guarantees exhaustion at this size.
    exhaust_amount = (mod.amount0_delta(mod.sqrt_price_x96_at_tick(-10),
                                        mod.Q96, liquidity, True) + 1)
    state = _pool(liquidity=liquidity, tick_data=ticks,
                  token0_decimals=0, input_price_usd=1)
    return state, Decimal(exhaust_amount)


def test_liquidity_exhausted_is_computed_fail():
    state, position = _exhausted_pool()
    result = mod.exit_depth_for_size(position_value_usd=position,
                                     max_impact_bps=Decimal("10000"),
                                     **state)
    assert result["reason"] == "COMPUTED_FAIL: LIQUIDITY_EXHAUSTED"
    assert result["max_exit_usd"] is not None


def test_liquidity_exhausted_is_not_sufficient():
    state, position = _exhausted_pool()
    result = mod.exit_depth_for_size(position_value_usd=position,
                                     max_impact_bps=Decimal("10000"),
                                     **state)
    assert result["sufficient"] is False


def test_sufficient_pool_still_returns_exit_depth_ok():
    state = _pool(token0_decimals=0, input_price_usd=1)
    result = mod.exit_depth_for_size(position_value_usd=Decimal("1000"),
                                     max_impact_bps=Decimal("100"),
                                     **state)
    assert result["reason"] == "EXIT_DEPTH_OK"
    assert result["max_exit_usd"] == Decimal("1000")


def test_insufficient_not_exhausted_still_returns_insufficient():
    state = _pool(token0_decimals=0, input_price_usd=1)
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100000000000000000"),
                                     max_impact_bps=Decimal("10"),
                                     **state)
    assert result["reason"] == "EXIT_DEPTH_INSUFFICIENT"
    assert result["sufficient"] is False


def test_empty_tick_data_still_unavailable():
    result = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                     max_impact_bps=Decimal("100"),
                                     **_pool(tick_data=[]))
    assert result["reason"] == "INPUTS_UNAVAILABLE: EXIT_QUOTE"
    assert result["max_exit_usd"] is None


def test_three_new_reasons_are_pairwise_distinct():
    s_missing = _pool()
    del s_missing["current_tick"]
    r_missing = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                        max_impact_bps=Decimal("100"), **s_missing)
    r_price = mod.exit_depth_for_size(position_value_usd=Decimal("100"),
                                      max_impact_bps=Decimal("100"),
                                      **_pool(input_price_usd=1))
    state, position = _exhausted_pool()
    r_exhausted = mod.exit_depth_for_size(position_value_usd=position,
                                          max_impact_bps=Decimal("10000"),
                                          **state)
    reasons = {r_missing["reason"], r_price["reason"], r_exhausted["reason"]}
    assert len(reasons) == 3
