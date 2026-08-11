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
    ACTIVE_SHARE_LIMIT,
    HARD_POSITION_TVL_SHARE,
    POSITION_TVL_SHARE,
    NETCOVER_SHADOW,
    NETCOVER_TINY_LIVE,
    absolute_profit_gate,
    apply_netcover_gate,
)
from scripts.lp_netcover_inputs_v1_readonly import (
    DRAG_APR_MAX,
    HISTORICAL_GAS_USD,
    INPUT_SEMANTICS,
    NETCOVER_INPUT_FIELDS,
    assemble_netcover_inputs,
    profile_kind,
    select_drag_adjusted_horizon,
)
from scripts.lp_portfolio_allocator_v1_readonly import M1_MIN_POSITION_USD


def _complete(**updates):
    record = {
        "chain": "Base",
        "project": "uniswap-v3",
        "protocol_type": "clmm",
        "profile": "PASSIVE_CL",
        "holding_horizon_days": 14,
        "is_new_pool": False,
        "fee_apr_24h": 20.0,
        "fee_apr_7d": 10.0,
        "reward_apr": 0.0,
        "reward_high_duration": 24.0,
        "reward_persistence_evidence_source": "measured_observation",
        "il_apr": 4.0,
        "sigma": 0.02,
        "sigma_pair": 0.02,
        "l_active_raw": 2_641_450_665_466_979_248,
        "price_usd": 1_669.9252504577303,
        "last_swap_price_token1_per_token0": 1_669.9252504577303,
        "last_swap_liquidity_raw": 2_641_450_665_466_979_248,
        "last_swap_cost_state_source": "measured:latest_decoded_swap_event",
        "token0": "0x4200000000000000000000000000000000000006",
        "token1": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "fee_tier": 0.000842,
        "dec0": 18,
        "dec1": 6,
    }
    record.update(updates)
    return record


@pytest.mark.parametrize("project", ["orca-dex", "raydium-amm"])
def test_m0n_defillama_solana_project_aliases_are_tactical(project):
    assert profile_kind({"project": project}) == "TACTICAL"


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


def test_solana_measured_clmm_state_is_accepted_but_forged_provenance_is_closed():
    solana = _complete(
        chain="Solana",
        holding_horizon_hours=168.0,
        fee_apr_24h=36.5,
        fee_apr_7d=36.5,
        sigma_pair=0.0324,
        il_apr=1.0,
        token0="AAPLxMint",
        token1="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        dec0=6,
        dec1=6,
        sqrt_price_x64=1 << 64,
        sqrt_price_x64_source="measured:pool.sqrt_price_x64",
        l_active_raw=1_000_000_000_000,
        l_active_raw_source="measured:pool.liquidity",
        last_swap_cost_state_source="measured:latest_decoded_solana_swap_event",
        tvlUsd=100_000.0,
    )
    trusted = assemble_netcover_inputs(solana, position_usd=5.0)
    assert trusted["fee_ev_usd"] is not None
    assert trusted["position_cap_usd"] is not None

    forged = assemble_netcover_inputs(solana | {
        "sqrt_price_x64_source": "caller:claimed_pool_state",
    }, position_usd=5.0)
    assert forged["fee_ev_usd"] is None


def test_solana_measured_gas_is_positive_and_incomplete_evidence_is_closed():
    solana = _complete(
        chain="Solana", holding_horizon_hours=168.0,
        token0="AAPLxMint", token1="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        dec0=6, dec1=6, sqrt_price_x64=1 << 64,
        sqrt_price_x64_source="measured:pool.sqrt_price_x64",
        l_active_raw=1_000_000_000_000,
        l_active_raw_source="measured:pool.liquidity", tvlUsd=100_000.0,
        solana_transaction_cost_evidence={
            "status": "PASS", "signature_fee_lamports": 5_000,
            "priority_fee_lamports": 100, "rent_lamports": 4_078_560,
            "operation_count": 2, "sol_usd": 150.0,
            "sol_usd_source": "free_quote", "quoted_at": 1,
        },
    )
    measured = assemble_netcover_inputs(solana, position_usd=5.0)
    assert measured["gas_usd"] > 0.0
    assert measured["gas_usd_source"].startswith("measured:solana_public_rpc")

    incomplete = assemble_netcover_inputs(solana | {
        "solana_transaction_cost_evidence": {"status": "PASS"},
    }, position_usd=5.0)
    assert incomplete["gas_usd"] is None
    assert incomplete["solana_gas_cost_reason"] == "SOLANA_GAS_EVIDENCE_FIELDS_MISSING"
    assert "SOLANA_GAS_EVIDENCE_FIELDS_MISSING" in incomplete["permanent_fail_closed_reasons"]


def test_m1_runtime_position_cap_is_persisted_and_hard_share_verified():
    out = assemble_netcover_inputs(_complete(tvlUsd=150_000.0))

    assert out["capital_tier"] == "M1"
    assert out["tier_configured_max_usd"] == 60.0
    assert out["active_liquidity_notional_usd"] > 0.0
    assert out["position_cap_usd"] == 60.0
    assert out["position_investable_usd"] == M1_MIN_POSITION_USD
    assert out["position_cap_tvl_share"] == pytest.approx(0.0004)
    assert out["position_cap_regular_tvl_share_limit"] == POSITION_TVL_SHARE
    assert out["position_cap_active_share_limit"] == ACTIVE_SHARE_LIMIT
    assert out["position_cap_tvl_share"] <= HARD_POSITION_TVL_SHARE
    assert out["position_cap_hard_tvl_share_ok"] is True
    assert out["position_cap_pass"] is True


def test_thin_active_liquidity_fails_closed_below_m1_actual_position():
    out = assemble_netcover_inputs(_complete(
        tvlUsd=1_000_000.0,
        l_active_raw=1,
        last_swap_liquidity_raw=1,
    ))

    assert out["position_cap_usd"] < M1_MIN_POSITION_USD
    assert out["position_investable_usd"] == out["position_cap_usd"]
    assert out["position_cap_pass"] is False
    assert out["position_cap_reason"] == "INV-TVLSHARE-01_POSITION_CAP_BELOW_M1_MIN"
    assert set(INPUT_SEMANTICS.values()) <= {
        "measured", "model_estimate", "historical_observation"
    }
    for field in NETCOVER_INPUT_FIELDS:
        assert out[f"{field}_semantics"] == INPUT_SEMANTICS[field]


def test_missing_sigma_or_depth_stays_none_and_gate_rejects_fail_closed():
    missing = assemble_netcover_inputs(
        _complete(
            sigma=None,
            sigma_pair=None,
            l_active_raw=None,
            price_usd=None,
            last_swap_liquidity_raw=None,
            last_swap_price_token1_per_token0=None,
        )
    )
    assert missing["fee_ev_usd"] is None
    assert missing["reward_ev_usd"] is None
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
        "protocol_type": "clmm",
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


def test_forged_fee_value_and_capture_metadata_cannot_override_recalculation():
    assembled = assemble_netcover_inputs(_complete(
        fee_ev_usd=999_999.0,
        fee_capture_reference_horizon_hours=1.0,
        fee_capture_reference_range_pct=0.0001,
        fee_capture_target_range_pct=0.0001,
        fee_capture_reference_share=1.0,
        fee_capture_target_share=1.0,
        fee_capture_share_ratio=999_999.0,
        fee_capture_evidence_apr_pct=999_999.0,
        fee_capture_haircut=999_999.0,
    ))

    assert assembled["fee_ev_usd"] != 999_999.0
    assert assembled["fee_capture_reference_horizon_hours"] == 168.0
    assert assembled["fee_capture_share_ratio"] != 999_999.0
    assert assembled["fee_capture_evidence_apr_pct"] == 10.0
    assert assembled["fee_capture_haircut"] == 0.65


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


def test_reward_haircut_combines_category_with_surrogate_without_double_counting():
    common = {
        "reward_apr": 60.0,
        "apyReward": 60.0,
        "apy": 70.0,
        "apyBase": 10.0,
        "apyMean30d": 58.0,
        "apyBase7d": 8.0,
        "apyPct30D": 10.0,
        "count": 386,
        "reward_category": "protocol",
        "reward_high_duration": None,
        "reward_persistence_evidence_source": "surrogate_defillama",
        "reward_conversion_l_active_raw": 10**24,
        "reward_conversion_price_usd": 1.0,
        "reward_conversion_fee_tier": 0.0005,
        "reward_conversion_dec0": 18,
        "reward_conversion_dec1": 6,
    }
    strong = assemble_netcover_inputs(_complete(**common))
    weak = assemble_netcover_inputs(_complete(**{**common, "apyPct30D": -100.0}))
    measured = assemble_netcover_inputs(_complete(
        **{
            key: value for key, value in common.items()
            if key not in {"reward_persistence_evidence_source", "reward_high_duration"}
        },
        reward_high_duration=24.0,
        reward_persistence_evidence_source="measured_observation",
    ))

    assert strong["reward_category_haircut"] == 0.50
    assert strong["reward_persistence_haircut"] == 0.25
    assert strong["reward_haircut"] == pytest.approx(0.125)
    assert weak["reward_haircut"] == 0.0
    assert measured["reward_haircut"] == 0.50
    # Persistence changes income credibility, not the conservative cost of
    # converting the same gross reward amount.
    assert strong["reward_conversion_cost_usd"] == pytest.approx(
        weak["reward_conversion_cost_usd"]
    )
    gated = apply_netcover_gate([strong])[0]
    assert gated["expected_net_yield_usd"] + gated["risk_usd"] == pytest.approx(
        strong["fee_ev_usd"] + strong["reward_ev_usd"] * 0.125
    )


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


def test_horizon_changes_range_aware_income_and_invalid_cross_profile_h_is_missing():
    six = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=6)
    )
    day = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=24)
    )
    assert day["fee_ev_usd"] > six["fee_ev_usd"] > 0.0
    assert day["fee_ev_usd"] < six["fee_ev_usd"] * 4.0
    assert day["il_ev_usd"] == pytest.approx(six["il_ev_usd"] * 4.0)
    invalid = assemble_netcover_inputs(
        _complete(profile="PASSIVE", holding_horizon_days=None, holding_horizon_hours=24)
    )
    assert invalid["holding_horizon_hours"] is None
    assert invalid["fee_ev_usd"] is None


def test_fee_ev_h7_h30_keeps_time_factor_and_canonical_share_ratio():
    h7 = assemble_netcover_inputs(_complete(holding_horizon_days=7))
    h30 = assemble_netcover_inputs(_complete(holding_horizon_days=30))

    observed = h30["fee_ev_usd"] / h7["fee_ev_usd"]
    expected_share_ratio = (
        h30["fee_capture_share_ratio"] / h7["fee_capture_share_ratio"]
    )
    expected = (30.0 / 7.0) * expected_share_ratio
    square_root_growth = (30.0 / 7.0) ** 0.5
    assert observed == pytest.approx(expected)
    assert observed == pytest.approx(square_root_growth, rel=0.25)
    assert 1.0 < observed < 30.0 / 7.0
    assert observed != pytest.approx(30.0 / 7.0)
    assert h7["fee_capture_reference_horizon_hours"] == 168.0
    assert h30["fee_capture_target_range_pct"] > h7["fee_capture_target_range_pct"]
    assert h30["fee_capture_target_share"] < h7["fee_capture_target_share"]
    assert h30["fee_capture_evidence_apr_pct"] == 10.0
    assert h30["fee_capture_haircut"] == 0.65


def test_fee_ev_time_factor_and_share_ratio_have_independent_exact_assertions():
    h6 = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=6)
    )
    h12 = assemble_netcover_inputs(
        _complete(profile="TACTICAL", holding_horizon_days=None, holding_horizon_hours=12)
    )
    expected_without_share = 50.0 * 10.0 / 100.0 * 0.65 * (12.0 / 8760.0)
    assert h12["fee_ev_usd"] == pytest.approx(
        expected_without_share * h12["fee_capture_share_ratio"]
    )
    assert h12["fee_ev_usd"] / h6["fee_ev_usd"] == pytest.approx(
        2.0
        * h12["fee_capture_share_ratio"]
        / h6["fee_capture_share_ratio"]
    )
    assert h6["fee_capture_share_ratio"] != pytest.approx(
        h12["fee_capture_share_ratio"]
    )


def test_reward_ev_time_factor_and_share_ratio_have_independent_exact_assertions():
    common = {
        "profile": "TACTICAL",
        "holding_horizon_days": None,
        "reward_apr": 12.0,
        "reward_category": "protocol",
    }
    h6 = assemble_netcover_inputs(_complete(**common, holding_horizon_hours=6))
    h12 = assemble_netcover_inputs(_complete(**common, holding_horizon_hours=12))
    expected_without_share = 50.0 * 12.0 / 100.0 * (12.0 / 8760.0)
    assert h12["reward_ev_usd"] == pytest.approx(
        expected_without_share * h12["fee_capture_share_ratio"]
    )
    assert h12["reward_ev_usd"] / h6["reward_ev_usd"] == pytest.approx(
        2.0
        * h12["fee_capture_share_ratio"]
        / h6["fee_capture_share_ratio"]
    )


def test_missing_pair_sigma_fails_closed_for_both_income_terms():
    out = assemble_netcover_inputs(
        _complete(
            sigma_pair=None,
            sigma_daily=None,
            reward_apr=12.0,
            reward_category="protocol",
        )
    )
    assert out["fee_ev_usd"] is None
    assert out["reward_ev_usd"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"sigma_pair": None},
        {"l_active_raw": None, "last_swap_liquidity_raw": None},
        {"price_usd": None, "last_swap_price_token1_per_token0": None},
        {"dec0": None},
        {"dec1": None},
    ],
)
def test_fee_ev_missing_range_liquidity_price_or_decimals_fails_closed(updates):
    out = assemble_netcover_inputs(_complete(**updates))
    assert out["fee_ev_usd"] is None
    assert out["fee_capture_share_ratio"] is None


def test_fee_ev_range_at_or_above_100pct_fails_closed_without_clamp():
    out = assemble_netcover_inputs(_complete(sigma_pair=1.0, holding_horizon_days=30))
    assert out["fee_capture_target_range_pct"] > 100.0
    assert out["fee_ev_usd"] is None


def test_fee_ev_rejects_generic_sigma_and_unprovenanced_direct_price_depth():
    generic_sigma = assemble_netcover_inputs(_complete(sigma_pair=None, sigma=0.02))
    assert generic_sigma["fee_ev_usd"] is None

    direct_prefill = assemble_netcover_inputs(_complete(
        sigma_pair=None,
        sigma_daily=0.02,
        holding_horizon_hours=720.0,
        holding_horizon_days=None,
        last_swap_price_token1_per_token0=None,
        last_swap_liquidity_raw=None,
        last_swap_cost_state_source=None,
        price_usd=1.0,
        l_active_raw=10**30,
    ))
    assert direct_prefill["entry_cost_usd"] is not None
    assert direct_prefill["fee_ev_usd"] is None
    assert direct_prefill["fee_capture_share_ratio"] is None


def test_drag_adjustment_uses_fee_fraction_and_smallest_legal_horizon():
    adjusted = select_drag_adjusted_horizon(
        profile="PASSIVE", er_horizon_hours=168.0, fee_tier=0.003,
        gas_usd=HISTORICAL_GAS_USD["base"], position_usd=50.0,
    )
    assert adjusted["holding_horizon_hours"] == 720.0
    assert adjusted["holding_horizon_source"] == "drag_adjusted(from=168)"
    assert adjusted["drag_apr_pct"] <= DRAG_APR_MAX
    assert adjusted["high_drag_flag"] is False


def test_drag_adjustment_not_triggered_and_max_h_fail_opens_with_flag():
    unchanged = select_drag_adjusted_horizon(
        profile="PASSIVE", er_horizon_hours=168.0, fee_tier=0.0001,
        gas_usd=HISTORICAL_GAS_USD["base"], position_usd=50.0,
    )
    assert unchanged["holding_horizon_hours"] == 168.0
    assert unchanged["holding_horizon_source"] == "ER_policy"
    assert unchanged["high_drag_flag"] is False

    still_high = select_drag_adjusted_horizon(
        profile="TACTICAL", er_horizon_hours=6.0, fee_tier=0.01,
        gas_usd=HISTORICAL_GAS_USD["base"], position_usd=50.0,
    )
    assert still_high["holding_horizon_hours"] == 72.0
    assert still_high["holding_horizon_source"] == "drag_adjusted(from=6)"
    assert still_high["drag_apr_pct"] > DRAG_APR_MAX
    assert still_high["high_drag_flag"] is True


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


def test_same_pool_same_parameters_recompute_netcover_after_add1_fee_density():
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
    # The old cost-sensitivity helper retains the superseded linear-H FeeEV;
    # ADD-1 must therefore produce a lower, independently recomputed result.
    assert gated["netcover"] < expected["netcover_30d"]
    assert gated["expected_net_yield_usd"] < expected["expected_net_profit_h_usd"]
    recomputed_profit = absolute_profit_gate(
        gated["expected_net_yield_usd"], assembled["round_trip_cost_usd"]
    )
    assert recomputed_profit.allowed is False


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
