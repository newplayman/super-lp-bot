"""Acceptance tests for the M0 read-only defensive exit policy."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from scripts.lp_exit_policy_v1_readonly import (
    MAX_MAJOR_COOLDOWN_MINUTES,
    MIN_MAJOR_COOLDOWN_MINUTES,
    BreachDirection,
    BreachObservation,
    ExitMode,
    ExitPolicyConfig,
    QuoteResult,
    RiskSignals,
    RiskState,
    RpcHealth,
    action_allowed,
    build_paper_action_plan,
    can_reenter,
    classify_breach,
    cooldown_requirement,
    evaluate_risk,
    risk_off_complete,
    transition_state,
)


def _config(**changes):
    values = {
        "profile": "MAJORS",
        "risky_token_side": "token0:ETH",
        "stable_token_side": "token1:USDC",
        "risky_inventory_target": 0.25,
        "max_slippage_bps": 75.0,
        "major_cooldown_minutes": 30,
    }
    values.update(changes)
    return ExitPolicyConfig(**values)


def _obs(direction, ratio, *, delta=0.0, cost=0.0):
    return BreachObservation(
        breach_direction=direction,
        post_remove_inventory_ratio=ratio,
        post_remove_delta_usd=delta,
        expected_swap_cost=cost,
    )


def test_contract_enums_and_records_are_explicit_and_immutable():
    assert {x.value for x in RiskState} == {
        "HEALTHY", "WATCH", "RISK_OFF_READY", "EXITING", "COOLDOWN"
    }
    assert {x.value for x in ExitMode} == {
        "REMOVE_ONLY", "REMOVE_TO_TARGET", "REMOVE_TO_STABLE", "PANIC_EXIT"
    }
    assert {x.value for x in BreachDirection} == {"LOWER", "UPPER", "NONE"}
    assert {x.value for x in RpcHealth} == {"NORMAL", "DEGRADED", "EXIT_ONLY", "KILLED"}
    config = _config()
    with pytest.raises(FrozenInstanceError):
        config.risky_inventory_target = 0.5


def test_breach_classification_is_directional_and_validated():
    assert classify_breach(price=89, lower_bound=90, upper_bound=110) is BreachDirection.LOWER
    assert classify_breach(price=111, lower_bound=90, upper_bound=110) is BreachDirection.UPPER
    assert classify_breach(price=100, lower_bound=90, upper_bound=110) is BreachDirection.NONE
    with pytest.raises(ValueError):
        classify_breach(price=100, lower_bound=110, upper_bound=90)


@pytest.mark.parametrize(
    "signals",
    [
        RiskSignals(il_soft_breach=True),
        RiskSignals(netcover_forward=1.4),
        RiskSignals(range_distance_fraction=0.8),
        RiskSignals(trend_worsening=True),
        RiskSignals(rwa_basis_worsening=True),
    ],
)
def test_healthy_to_watch_on_any_soft_signal(signals):
    decision = evaluate_risk(RiskState.HEALTHY, signals, _obs(BreachDirection.NONE, 0.25), _config())
    assert decision.next_state is RiskState.WATCH
    assert decision.should_execute is False


def test_watch_requires_prd_combination_not_single_breach():
    lone_lower = RiskSignals(lower_breach=True)
    decision = evaluate_risk(
        RiskState.WATCH, lone_lower, _obs(BreachDirection.LOWER, 0.80), _config()
    )
    assert decision.next_state is RiskState.WATCH
    assert decision.should_execute is False

    combined = RiskSignals(lower_breach=True, trend_continuation=True)
    decision = evaluate_risk(
        RiskState.WATCH, combined, _obs(BreachDirection.LOWER, 0.80), _config()
    )
    assert decision.next_state is RiskState.RISK_OFF_READY
    assert decision.recommended_exit_mode is ExitMode.REMOVE_TO_STABLE


def test_watch_combination_il_and_netcover_and_structural_risk():
    il_cover = evaluate_risk(
        RiskState.WATCH,
        RiskSignals(il_soft_breach=True, netcover_forward=0.9),
        _obs(BreachDirection.NONE, 0.40),
        _config(),
    )
    assert il_cover.next_state is RiskState.RISK_OFF_READY
    structural = evaluate_risk(
        RiskState.WATCH,
        RiskSignals(liquidity_worsening=True),
        _obs(BreachDirection.NONE, 0.25),
        _config(),
    )
    assert structural.next_state is RiskState.RISK_OFF_READY


@pytest.mark.parametrize(
    "signals",
    [
        RiskSignals(rug_risk=True),
        RiskSignals(honeypot_risk=True),
        RiskSignals(data_corruption=True),
        RiskSignals(contract_risk=True),
        RiskSignals(kill_switch=True),
    ],
)
def test_hard_veto_overrides_tier_and_goes_directly_to_panic(signals):
    decision = evaluate_risk(
        RiskState.HEALTHY,
        signals,
        _obs(BreachDirection.NONE, 0.50),
        _config(),
        tier="A",
    )
    assert decision.next_state is RiskState.EXITING
    assert decision.recommended_exit_mode is ExitMode.PANIC_EXIT
    assert decision.hard_risk_override is True


def test_il_hard_gate_overrides_tier_but_requires_prd_companion_signal():
    decision = evaluate_risk(
        RiskState.HEALTHY,
        RiskSignals(il_hard_breach=True, netcover_forward=0.8),
        _obs(BreachDirection.NONE, 0.40),
        _config(),
        tier="A",
    )
    assert decision.next_state is RiskState.EXITING
    assert decision.hard_risk_override is True


def test_lower_eth_heavy_inventory_recommends_stable_upper_stable_is_remove_only():
    lower = evaluate_risk(
        RiskState.WATCH,
        RiskSignals(lower_breach=True, trend_continuation=True, netcover_forward=0.8),
        _obs(BreachDirection.LOWER, 0.84, delta=590.0, cost=3.5),
        _config(),
    )
    assert lower.recommended_exit_mode is ExitMode.REMOVE_TO_STABLE
    assert lower.breach_direction is BreachDirection.LOWER
    assert lower.post_remove_inventory_ratio == 0.84
    assert lower.post_remove_delta_usd == 590.0
    assert lower.expected_swap_cost == 3.5

    upper = evaluate_risk(
        RiskState.WATCH,
        RiskSignals(structural_risk_worsening=True),
        _obs(BreachDirection.UPPER, 0.05),
        _config(),
    )
    assert upper.recommended_exit_mode is ExitMode.REMOVE_ONLY


def test_remove_only_has_no_swap_and_can_complete_only_at_inventory_target():
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_ONLY,
        rpc_health=RpcHealth.NORMAL,
        quote=None,
        config=_config(),
        post_trade_risky_inventory_ratio=0.20,
    )
    assert plan.paper_only and plan.remove_simulated
    assert plan.swap_requested is False
    assert plan.swap_allowed is False
    assert plan.risk_off_complete is True
    assert plan.substate == "remove_only"


def test_inv_exit_01_remove_with_eighty_percent_risky_cannot_cooldown():
    assert risk_off_complete(0.80, 0.25) is False
    assert transition_state(
        RiskState.EXITING, RiskState.COOLDOWN, risk_off_complete=False
    ) is RiskState.EXITING
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_ONLY,
        rpc_health=RpcHealth.NORMAL,
        quote=None,
        config=_config(),
        post_trade_risky_inventory_ratio=0.80,
    )
    assert plan.risk_off_complete is False
    assert plan.next_state is RiskState.EXITING


@pytest.mark.parametrize(
    "quote,reason",
    [
        (QuoteResult.failed("quote_timeout"), "quote_failed"),
        (QuoteResult.ok(expected_slippage_bps=100.0, expected_swap_cost_usd=8.0), "slippage_limit"),
    ],
)
def test_inv_exit_02_quote_failure_or_slippage_limit_stages_and_alerts(quote, reason):
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_TO_STABLE,
        rpc_health=RpcHealth.NORMAL,
        quote=quote,
        config=_config(max_slippage_bps=75.0),
        post_trade_risky_inventory_ratio=0.80,
        exit_latency_loss_usd=1.25,
    )
    assert plan.swap_requested is True
    assert plan.quote_required is True
    assert plan.swap_allowed is False
    assert plan.substate == "staged/limit_exit"
    assert plan.alert is True
    assert plan.block_reason == reason
    assert plan.exit_latency_loss_usd == 1.25


def test_panic_exit_also_requires_quote_and_never_blind_swaps():
    plan = build_paper_action_plan(
        mode=ExitMode.PANIC_EXIT,
        rpc_health=RpcHealth.NORMAL,
        quote=None,
        config=_config(),
        post_trade_risky_inventory_ratio=0.90,
    )
    assert plan.swap_allowed is False
    assert plan.substate == "staged/limit_exit"
    assert plan.alert is True


def test_killed_rpc_reports_no_remove_simulation_and_no_paper_actions():
    plan = build_paper_action_plan(
        mode=ExitMode.PANIC_EXIT,
        rpc_health=RpcHealth.KILLED,
        quote=QuoteResult.ok(expected_slippage_bps=10.0, expected_swap_cost_usd=1.0),
        config=_config(),
        post_trade_risky_inventory_ratio=0.90,
    )
    assert plan.paper_only is True
    assert plan.remove_simulated is False
    assert plan.swap_allowed is False
    assert plan.paper_actions == ()
    assert plan.block_reason == "rpc_killed"


def test_successful_quote_exposes_expected_and_actual_slippage_interfaces():
    quote = QuoteResult.ok(expected_slippage_bps=25.0, expected_swap_cost_usd=2.5)
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_TO_TARGET,
        rpc_health=RpcHealth.NORMAL,
        quote=quote,
        config=_config(),
        post_trade_risky_inventory_ratio=0.25,
        actual_slippage_bps=28.0,
        exit_latency_loss_usd=0.5,
    )
    assert plan.swap_allowed is True
    assert plan.expected_slippage_bps == 25.0
    assert plan.actual_slippage_bps == 28.0
    assert plan.expected_swap_cost_usd == 2.5
    assert plan.exit_latency_loss_usd == 0.5
    assert plan.paper_actions == ("simulate_remove", "simulate_swap_to_target")


def test_invalid_state_jumps_are_rejected():
    with pytest.raises(ValueError):
        transition_state(RiskState.HEALTHY, RiskState.EXITING)
    with pytest.raises(ValueError):
        transition_state(RiskState.WATCH, RiskState.COOLDOWN)
    assert transition_state(RiskState.HEALTHY, RiskState.EXITING, hard_veto=True) is RiskState.EXITING


def test_cooldown_bounds_and_profile_requirements():
    assert (MIN_MAJOR_COOLDOWN_MINUTES, MAX_MAJOR_COOLDOWN_MINUTES) == (15, 60)
    with pytest.raises(ValueError):
        _config(major_cooldown_minutes=14)
    with pytest.raises(ValueError):
        _config(major_cooldown_minutes=61)
    major = cooldown_requirement(_config(), reason="normal")
    assert major.duration == timedelta(minutes=30)
    rwa = cooldown_requirement(_config(profile="RWA"), reason="normal")
    assert rwa.requires_full_short_window_or_session_change is True
    risk = cooldown_requirement(_config(), reason="rug")
    assert risk.manual_release_required is True


def test_reentry_requires_all_four_gates_and_manual_release_when_required():
    ended = datetime(2026, 8, 8, tzinfo=timezone.utc)
    now = ended + timedelta(seconds=1)
    assert can_reenter(
        now=now,
        cooldown_ends_at=ended,
        regime_changed=True,
        netcover_gate_passed=True,
        absolute_profit_gate_passed=True,
    ) is True
    assert can_reenter(
        now=now,
        cooldown_ends_at=ended,
        regime_changed=True,
        netcover_gate_passed=False,
        absolute_profit_gate_passed=True,
    ) is False
    assert can_reenter(
        now=now,
        cooldown_ends_at=ended,
        regime_changed=True,
        netcover_gate_passed=True,
        absolute_profit_gate_passed=True,
        manual_release_required=True,
        manual_released=False,
    ) is False


@pytest.mark.parametrize(
    "health,allowed,denied",
    [
        (RpcHealth.DEGRADED, ("monitor", "remove", "collect", "swap_to_usdc"), ("open", "add")),
        (RpcHealth.EXIT_ONLY, ("remove", "collect", "swap_to_usdc"), ("monitor", "open", "add", "rebalance", "approve")),
        (RpcHealth.KILLED, (), ("monitor", "remove", "collect", "swap_to_usdc", "approve")),
    ],
)
def test_rpc_action_allowlist_is_fail_closed(health, allowed, denied):
    assert all(action_allowed(health, action) for action in allowed)
    assert all(not action_allowed(health, action) for action in denied)
    assert action_allowed(health, "arbitrary_send") is False
