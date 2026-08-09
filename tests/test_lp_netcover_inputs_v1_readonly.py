"""Contracts for the W6 NetCover input assembler (pure, no network)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.lp_cost_sensitivity_v1_readonly import (
    _economics_at_size,
    default_base_vetted_pool,
)
from scripts.lp_netcover_engine_v1_readonly import (
    NETCOVER_SHADOW,
    NETCOVER_TINY_LIVE,
    absolute_profit_gate,
    apply_netcover_gate,
)
from scripts.lp_netcover_inputs_v1_readonly import (
    INPUT_SEMANTICS,
    NETCOVER_INPUT_FIELDS,
    assemble_netcover_inputs,
)
from scripts.lp_portfolio_allocator_v1_readonly import M1_MIN_POSITION_USD


def _complete(**updates):
    record = {
        "chain": "Base",
        "project": "uniswap-v3",
        "profile": "PASSIVE_CL",
        "holding_horizon_days": 14,
        "is_new_pool": False,
        "fee_apr_24h": 20.0,
        "fee_apr_7d": 10.0,
        "reward_apr": 0.0,
        "il_apr": 4.0,
        "sigma": 0.02,
        "l_active_raw": 2_641_450_665_466_979_248,
        "price_usd": 1_669.9252504577303,
        "fee_tier": 0.000842,
        "dec0": 18,
        "dec1": 6,
    }
    record.update(updates)
    return record


def test_all_nine_fields_are_calculated_and_each_has_semantics():
    out = assemble_netcover_inputs(_complete())
    assert out["capital_usd"] == M1_MIN_POSITION_USD == 50.0
    assert all(out[field] is not None for field in NETCOVER_INPUT_FIELDS)
    assert out["fee_ev_usd"] > 0
    assert out["reward_ev_usd"] == 0.0
    assert out["il_ev_usd"] > 0
    assert out["entry_cost_usd"] > 0
    assert out["exit_cost_usd"] > 0
    assert out["gas_usd"] == 0.0795
    assert out["slippage_usd"] > 0
    assert out["reward_conversion_cost_usd"] == 0.0
    assert out["exit_latency_loss_usd"] > 0
    assert out["netcover_input_semantics"] == INPUT_SEMANTICS
    assert set(INPUT_SEMANTICS.values()) <= {
        "measured", "model_estimate", "historical_observation"
    }
    for field in NETCOVER_INPUT_FIELDS:
        assert out[f"{field}_semantics"] == INPUT_SEMANTICS[field]


def test_missing_sigma_or_depth_stays_none_and_gate_rejects_fail_closed():
    missing = assemble_netcover_inputs(
        _complete(sigma=None, l_active_raw=None, price_usd=None)
    )
    assert missing["il_ev_usd"] is None
    assert missing["entry_cost_usd"] is None
    assert missing["exit_cost_usd"] is None
    assert missing["slippage_usd"] is None
    gated = apply_netcover_gate([missing])[0]
    assert gated["netcover_pass"] is False
    assert gated["netcover_ratio"] is None
    assert gated["rejection_reason"].startswith("NETCOVER_INPUT_MISSING:")


@pytest.mark.parametrize(
    ("category", "haircut"),
    [
        ("stablecoin", 0.90),
        ("major", 0.75),
        ("protocol", 0.50),
        ("new_token", 0.25),
        ("points", 0.0),
    ],
)
def test_prd_reward_haircut_table_is_attached(category, haircut):
    out = assemble_netcover_inputs(
        _complete(
            reward_apr=12.0,
            reward_category=category,
            reward_conversion_l_active_raw=10**24,
            reward_conversion_price_usd=1.0,
            reward_conversion_fee_tier=0.0005,
            reward_conversion_dec0=18,
            reward_conversion_dec1=6,
        )
    )
    assert out["reward_haircut"] == haircut
    assert out["reward_ev_usd"] > 0
    if category == "points":
        assert out["reward_conversion_cost_usd"] == 0.0
    else:
        assert out["reward_conversion_cost_usd"] > 0


def test_reward_bearing_unknown_category_or_missing_conversion_depth_is_closed():
    unknown = assemble_netcover_inputs(_complete(reward_apr=10.0))
    assert unknown["reward_ev_usd"] is None
    assert unknown["reward_conversion_cost_usd"] is None

    no_route = assemble_netcover_inputs(
        _complete(reward_apr=10.0, reward_category="protocol")
    )
    assert no_route["reward_ev_usd"] is not None
    assert no_route["reward_conversion_cost_usd"] is None
    assert apply_netcover_gate([no_route])[0]["netcover_pass"] is False


def test_points_haircut_needs_no_fictional_swap_route():
    points = assemble_netcover_inputs(
        _complete(reward_apr=100.0, reward_category="points")
    )
    assert points["reward_haircut"] == 0.0
    assert points["reward_conversion_cost_usd"] == 0.0


@pytest.mark.parametrize(
    ("profile", "hours"),
    [("TACTICAL", 6.0), ("TACTICAL", 72.0), ("PASSIVE_CL", 168.0), ("PASSIVE", 720.0)],
)
def test_horizon_follows_profile_discrete_set(profile, hours):
    out = assemble_netcover_inputs(
        _complete(profile=profile, holding_horizon_days=None, holding_horizon_hours=hours)
    )
    assert out["holding_horizon_hours"] == hours


def test_horizon_changes_usd_inputs_and_invalid_cross_profile_h_is_missing():
    six = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=6)
    )
    day = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=24)
    )
    assert day["fee_ev_usd"] == pytest.approx(six["fee_ev_usd"] * 4.0)
    assert day["il_ev_usd"] == pytest.approx(six["il_ev_usd"] * 4.0)
    invalid = assemble_netcover_inputs(
        _complete(profile="PASSIVE", holding_horizon_days=None, holding_horizon_hours=24)
    )
    assert invalid["holding_horizon_hours"] is None
    assert invalid["fee_ev_usd"] is None


def test_new_or_unknown_pool_uses_stricter_fee_haircut_not_optimistic_default():
    established = assemble_netcover_inputs(_complete(is_new_pool=False))
    new = assemble_netcover_inputs(_complete(is_new_pool=True))
    unknown = assemble_netcover_inputs(_complete(is_new_pool=None))
    assert established["fee_apr_haircut"] == 0.65
    assert new["fee_apr_haircut"] == unknown["fee_apr_haircut"] == 0.40
    assert new["fee_ev_usd"] < established["fee_ev_usd"]


def test_same_pool_swap_components_match_cost_sensitivity_exactly():
    pool = default_base_vetted_pool()
    expected = _economics_at_size(M1_MIN_POSITION_USD, pool)
    out = assemble_netcover_inputs(
        _complete(
            holding_horizon_days=30,
            l_active_raw=pool.l_active_raw_historical,
            price_usd=pool.price_usd,
            fee_tier=pool.fee_tier,
            dec0=pool.dec0,
            dec1=pool.dec1,
        )
    )
    assert out["entry_cost_usd"] == pytest.approx(expected["entry_cost_usd"])
    assert out["exit_cost_usd"] == pytest.approx(expected["exit_cost_usd"])
    assert out["slippage_usd"] == pytest.approx(expected["slippage_usd"])
    assert out["round_trip_cost_usd"] == pytest.approx(expected["round_trip_cost_usd"])


def test_same_pool_same_parameters_recompute_netcover_and_profit_conclusion():
    pool = replace(
        default_base_vetted_pool(),
        reward_apr_pct=0.0,
        reward_conversion_apr_pct_model=0.0,
    )
    expected = _economics_at_size(M1_MIN_POSITION_USD, pool)
    assembled = assemble_netcover_inputs(_complete(
        holding_horizon_days=30,
        fee_apr_24h=pool.conservative_fee_apr_pct / 0.65,
        fee_apr_7d=pool.conservative_fee_apr_pct / 0.65,
        reward_apr=0.0,
        il_apr=pool.expected_il_apr_pct,
        l_active_raw=pool.l_active_raw_historical,
        price_usd=pool.price_usd,
        fee_tier=pool.fee_tier,
        dec0=pool.dec0,
        dec1=pool.dec1,
    ))
    gated = apply_netcover_gate([assembled])[0]
    assert gated["netcover"] == pytest.approx(expected["netcover_30d"])
    assert gated["expected_net_yield_usd"] == pytest.approx(
        expected["expected_net_profit_h_usd"]
    )
    recomputed_profit = absolute_profit_gate(
        gated["expected_net_yield_usd"], assembled["round_trip_cost_usd"]
    )
    assert recomputed_profit.allowed == expected["absolute_profit_gate_pass"]
    assert recomputed_profit.required_profit_usd == pytest.approx(
        expected["absolute_profit_required_usd"]
    )


def test_measured_swap_with_stable_token0_is_normalized_without_tvl_proxy():
    out = assemble_netcover_inputs(_complete(
        price_usd=None,
        l_active_raw=None,
        last_swap_price_token1_per_token0=2.0,
        last_swap_liquidity_raw=10**24,
        token0="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        token1="0xacfe6019ed1a7dc6f7b508c02d1b04ec88cc21bf",
        dec0=6,
        dec1=18,
    ))
    assert out["entry_cost_usd"] is not None
    assert out["exit_cost_usd"] is not None
    assert out["slippage_usd"] is not None


def test_inv_gate_01_thresholds_are_not_relaxed_by_w6():
    assert NETCOVER_SHADOW == 1.0
    assert NETCOVER_TINY_LIVE == 1.5
