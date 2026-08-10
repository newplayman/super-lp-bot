"""Contracts for the WP-04 full-cost NetCover gate (pure, no network)."""

import math

import pytest

from scripts.lp_netcover_engine_v1_readonly import (
    MIN_PROFIT_USD,
    NETCOVER_SHADOW,
    NETCOVER_TINY_LIVE,
    SAFETY_MULTIPLE,
    NetCoverEstimate,
    absolute_profit_gate,
    apply_netcover_gate,
    adjusted_income_ev,
    evaluate_netcover,
    expected_risk_cost,
    gross_fee_cover,
    netcover,
    position_cap_usd,
)


def test_inv_gate_01_thresholds_are_explicit_and_not_relaxed():
    assert NETCOVER_SHADOW == 1.0
    assert NETCOVER_TINY_LIVE == 1.5
    assert SAFETY_MULTIPLE == 5.0
    assert MIN_PROFIT_USD == 1.0


@pytest.mark.parametrize("haircut, expected", [(0.9, 19.0), (0.75, 17.5), (0.0, 10.0)])
def test_adjusted_income_haircuts_reward_only(haircut, expected):
    assert adjusted_income_ev(10.0, 10.0, haircut) == pytest.approx(expected)


def test_reward_haircut_may_be_selected_from_explicit_mapping():
    assert adjusted_income_ev(3.0, 8.0, {"category": "major", "major": 0.75}) == 9.0


def test_expected_risk_cost_contains_every_prd_component():
    cost = expected_risk_cost(
        il=1.0, lvr=2.0, entry_cost=3.0, exit_cost=4.0,
        gas=5.0, slippage=6.0, reward_conv=7.0, exit_latency=8.0,
    )
    assert cost == 36.0


def test_netcover_and_diagnostic_gross_fee_cover_are_distinct():
    assert gross_fee_cover(10.0, 2.0) == 5.0
    assert netcover(10.0, 5.0) == 2.0
    assert math.isinf(netcover(1.0, 0.0))
    assert netcover(0.0, 0.0) == 0.0


def test_evaluation_marks_lvr_and_exit_latency_as_model_estimates():
    out = evaluate_netcover(
        fee_ev=5.0, reward_ev=4.0, reward_haircut=0.5,
        expected_il=1.0, lvr_coefficient=0.5,
        entry_cost=0.5, exit_cost=0.5, gas=0.25, slippage=0.25,
        reward_conversion_cost=0.25, exit_latency_loss=0.25,
    )
    assert isinstance(out, NetCoverEstimate)
    assert out.adjusted_income_ev == 7.0
    assert out.expected_lvr_model == 0.5
    assert out.exit_latency_loss_model == 0.25
    assert out.expected_risk_cost == 3.5
    assert out.netcover == 2.0
    assert out.shadow_candidate is True
    assert out.tiny_live_candidate is True
    assert out.semantics["expected_lvr_model"].startswith("model_estimate")
    assert out.semantics["exit_latency_loss_model"].startswith("model_estimate")


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_negative_or_nonfinite_cost_inputs_fail_closed(bad):
    with pytest.raises(ValueError):
        expected_risk_cost(bad, 0, 0, 0, 0, 0, 0, 0)


def test_inv_cost_01_high_apr_but_tiny_absolute_profit_is_skip():
    decision = absolute_profit_gate(expected_net_profit_h=0.08, round_trip_cost=0.10)
    assert decision.allowed is False
    assert decision.required_profit_usd == 1.0
    assert decision.reason == "INV-COST-01_EXPECTED_NET_PROFIT_TOO_LOW"


def test_absolute_profit_gate_uses_five_times_roundtrip_when_larger():
    assert absolute_profit_gate(-0.5, 0.1).allowed is False
    assert absolute_profit_gate(2.49, 0.5).allowed is False
    assert absolute_profit_gate(2.5, 0.5).allowed is True


def test_inv_tvlshare_01_cap_shrinks_with_tvl_and_active_liquidity():
    assert position_cap_usd(500, 1_000_000, 1_000_000) == 500.0
    assert position_cap_usd(500, 400_000, 1_000_000) == 200.0
    assert position_cap_usd(500, 100_000_000, 1_000) == 20.0


def test_position_cap_validates_inputs_fail_closed():
    with pytest.raises(ValueError):
        position_cap_usd(60, 0, 10_000)


def test_scanner_adapter_is_full_cost_and_missing_fields_fail_closed():
    assert apply_netcover_gate([{"pool": "0xmissing"}])[0]["netcover_pass"] is False
    rec = {
        "pool": "0xok", "capital_usd": 100,
        "protocol_type": "clmm", "netcover_model_path": "clmm_vol_sized_range_v1",
        "fee_ev_usd": 4, "reward_ev_usd": 2, "il_ev_usd": 1,
        "entry_cost_usd": 0.1, "exit_cost_usd": 0.1, "gas_usd": 0.1,
        "slippage_usd": 0.1, "reward_conversion_cost_usd": 0.1,
        "exit_latency_loss_usd": 0.1,
    }
    out = apply_netcover_gate([rec], reward_haircut=0.5, lvr_coefficient=0.5)[0]
    assert out["lvr_ev_usd"] == 0.5
    assert out["risk_usd"] == pytest.approx(2.1)
    assert out["expected_net_yield_usd"] == pytest.approx(2.9)
    assert out["expected_net_yield_pct"] == pytest.approx(2.9)
    assert out["netcover_ratio"] == out["netcover"]
    assert out["netcover_pass"] is True
