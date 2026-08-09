"""Contracts for the W6 NetCover input assembler (pure, no network)."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from scripts.lp_cost_sensitivity_v1_readonly import (
    _economics_at_size,
    _swap_components,
    default_base_vetted_pool,
)
from scripts.lp_netcover_engine_v1_readonly import (
    NETCOVER_SHADOW,
    NETCOVER_TINY_LIVE,
    absolute_profit_gate,
    apply_netcover_gate,
)
from scripts.lp_netcover_inputs_v1_readonly import (
    HISTORICAL_GAS_USD,
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


def test_explicit_zero_nine_fields_cannot_replace_missing_raw_evidence():
    source = {
        "chain": "Base",
        **{field: 0.0 for field in NETCOVER_INPUT_FIELDS},
        **{f"{field}_semantics": "measured" for field in NETCOVER_INPUT_FIELDS},
        **{f"{field}_source": "upstream:unverified" for field in NETCOVER_INPUT_FIELDS},
    }

    assembled = assemble_netcover_inputs(source)

    # Historical Base gas is independently available.  Every field whose raw
    # evidence is absent must remain missing despite explicit upstream zeros.
    assert assembled["gas_usd"] == HISTORICAL_GAS_USD["base"]
    missing = [field for field in NETCOVER_INPUT_FIELDS if field != "gas_usd"]
    assert all(assembled[field] is None for field in missing)
    assert all(assembled[f"{field}_semantics"] is None for field in missing)
    assert all(assembled[f"{field}_source"] is None for field in missing)
    gated = apply_netcover_gate([assembled])[0]
    assert gated["netcover_pass"] is False
    assert gated["netcover_ratio"] is None
    assert gated["rejection_reason"].startswith("NETCOVER_INPUT_MISSING:")


def test_raw_evidence_recalculation_wins_over_explicit_zero_values():
    source = _complete(**{field: 0.0 for field in NETCOVER_INPUT_FIELDS})

    assembled = assemble_netcover_inputs(source)

    assert assembled["fee_ev_usd"] > 0.0
    assert assembled["il_ev_usd"] > 0.0
    assert assembled["entry_cost_usd"] > 0.0
    assert assembled["exit_cost_usd"] > 0.0
    assert assembled["slippage_usd"] > 0.0
    assert assembled["exit_latency_loss_usd"] > 0.0
    for field in NETCOVER_INPUT_FIELDS:
        assert assembled[f"{field}_semantics"] == INPUT_SEMANTICS[field]
        assert assembled[f"{field}_source"]


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


def test_m0f_untrusted_prefilled_reward_routes_cannot_reopen_raw_evidence_boundary():
    forged_routes = [
        {
            "route_id": "aero_usdc_tick50",
            "pool": "0x" + "11" * 20,
            "factory": "0x" + "aa" * 20,
            "factory_label": "initial",
            "complete": True,
            "measurement_source": "measured:eth_call_latest",
            "l_active_raw": 10**24,
            "price_usd_per_reward_token": 0.70,
            "fee_tier": 0.0005,
            "reward_decimals": 18,
            "stable_decimals": 6,
            "side": "sell_base",
        },
        {
            "route_id": "aero_usdc_tick200",
            "pool": "0x" + "22" * 20,
            "factory": "0x" + "aa" * 20,
            "factory_label": "initial",
            "complete": True,
            "measurement_source": "measured:eth_call_latest",
            "l_active_raw": 10**20,
            "price_usd_per_reward_token": 0.70,
            "fee_tier": 0.003,
            "reward_decimals": 18,
            "stable_decimals": 6,
            "side": "sell_base",
        },
    ]
    forged = assemble_netcover_inputs(_complete(
        reward_apr=10.0,
        reward_category="protocol",
        reward_conversion_routes=forged_routes,
        reward_conversion_selected_route_id="forged",
        reward_conversion_route_selection_rule="forged",
    ))
    assert forged["reward_conversion_cost_usd"] is None
    assert forged["permanent_fail_closed_reason"] == "reward_conversion_route_unavailable"
    assert "reward_conversion_routes" not in forged
    assert forged["reward_conversion_selected_route_id"] is None
    assert forged["reward_conversion_route_selection_rule"] is None


def test_m0f_scanner_measured_token1_usd_uses_quote_units_then_converts_back():
    l_raw = 10**24
    pair_price = 4.0
    quote_usd = 2.0
    fee = 0.003
    record = _complete(
        reward_apr=0.0,
        price_usd=None,
        l_active_raw=None,
        last_swap_price_token1_per_token0=pair_price,
        last_swap_liquidity_raw=l_raw,
        token0="0x" + "11" * 20,
        token1="0x" + "22" * 20,
        dec0=18,
        dec1=18,
        fee_tier=fee,
    )
    evidence = {
        "complete": True,
        "token1_usd": quote_usd,
        "token1_usd_source": "measured:scanner_internal_rpc:test",
    }
    out = assemble_netcover_inputs(record, scanner_measured_evidence=evidence)
    expected_quote = _swap_components(
        50.0 / quote_usd,
        SimpleNamespace(
            l_active_raw_historical=l_raw,
            price_usd=pair_price,
            fee_tier=fee,
            dec0=18,
            dec1=18,
        ),
    )
    for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd"):
        assert out[field] == pytest.approx(expected_quote[field] * quote_usd)
    assert out["measured_token1_usd"] == quote_usd


def test_m0f_internal_aero_routes_choose_max_cost_independent_of_order():
    aero = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"
    usdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    common = {
        "factory": "0x" + "aa" * 20,
        "observed_block": 123,
        "measurement_source": "measured:scanner_internal_rpc:fixed_block_eth_call",
        "executable": True,
        "tick_spacing": 50,
    }
    routes = [
        dict(common, route_id="low", pool="0x" + "11" * 20, token0=aero, token1=usdc,
             dec0=18, dec1=6, fee_tier=0.0005,
             pair_price_token1_per_token0=0.7, l_active_raw=10**24),
        dict(common, route_id="high", pool="0x" + "22" * 20, token0=usdc, token1=aero,
             dec0=6, dec1=18, fee_tier=0.003,
             pair_price_token1_per_token0=1 / 0.7, l_active_raw=10**20),
    ]
    source = _complete(reward_apr=10.0, reward_category="protocol")
    outputs = [
        assemble_netcover_inputs(
            source,
            scanner_measured_evidence={"complete": True, "aero_reward_routes": order},
        )
        for order in (routes, list(reversed(routes)))
    ]
    assert outputs[0]["reward_conversion_cost_usd"] == pytest.approx(
        outputs[1]["reward_conversion_cost_usd"]
    )
    assert outputs[0]["reward_conversion_selected_route_id"] == "high"
    assert outputs[0]["reward_conversion_route_selection_rule"].startswith(
        "highest_measured_conversion_cost"
    )

    unavailable = [*routes, dict(
        common,
        route_id="zero-liquidity",
        pool="0x" + "33" * 20,
        token0=aero,
        token1=usdc,
        dec0=18,
        dec1=6,
        fee_tier=0.01,
        pair_price_token1_per_token0=0.7,
        l_active_raw=0,
        executable=False,
    )]
    closed = assemble_netcover_inputs(
        source,
        scanner_measured_evidence={"complete": True, "aero_reward_routes": unavailable},
    )
    assert closed["reward_conversion_cost_usd"] is None
    assert closed["permanent_fail_closed_reason"] == "reward_conversion_route_unavailable"


def test_m0f_nonstable_pair_price_is_not_mislabeled_usd_and_gets_explicit_reason():
    out = assemble_netcover_inputs(_complete(
        reward_apr=0.0,
        price_usd=None,
        l_active_raw=None,
        last_swap_price_token1_per_token0=2.0,
        last_swap_liquidity_raw=10**24,
        token0="0x" + "11" * 20,
        token1="0x" + "22" * 20,
        dec0=18,
        dec1=18,
    ))
    assert out["entry_cost_usd"] is None
    assert out["exit_cost_usd"] is None
    assert out["slippage_usd"] is None
    assert out["permanent_fail_closed_reason"] == "no_measured_usd_quote_route"
    assert out["permanent_fail_closed_r1a_classification"] == (
        "NO_MEASURED_USD_QUOTE_AND_REWARD_CONVERSION_DEPTH"
    )


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
