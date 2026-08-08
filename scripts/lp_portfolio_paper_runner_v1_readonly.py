#!/usr/bin/env python3
"""Multi-pool LP paper-shadow runner (READ-ONLY research).

Takes a fixed allocation (the portfolio allocator's output) and tracks the
paper P&L of the whole book over time. Per pool it holds a vol-sized *passive*
LP position and:
  - accrues real fees from real on-chain swaps that land inside the band,
  - accrues reward emissions linearly from the pool's reward_apr,
  - marks LP value + IL from the latest on-chain price,
  - logs band breaches for the operator (does NOT auto-rebalance — Tier-A
    policy is wide-range-passive; a breach is information, not an action).

This mirrors strategy_pivot_d4_realtime_paper_shadow_validation.py (the
single-pool Tier-A version) but is LP-only (no hedge) and multi-pool.

FROZEN-project rules: read-only. No wallet / signing / broadcast / chain
writes. RPC reads only. Honors FETCH_PACE_SECS for getLogs pacing.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# repo-root import shim so `scripts.*` resolves when run as a file
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.lp_tier_c_exit_feasibility_v1_readonly import (  # noqa: E402
    fetch_pool_swaps,
    _rpc_with_retry,
)
from scripts.lp_il_inventory_engine_v1_readonly import (  # noqa: E402
    alpha_vs_hodl,
    current_inventory,
    hodl_nav,
    il_pct,
    il_usd,
    lp_nav_ex_fee,
    paper_entry_baseline,
    pnl_vs_usdc,
    position_state_from_capital,
)
from scripts.lp_v3_fee_share import (  # noqa: E402
    position_liquidity_raw,
    fee_for_swap_usd,
)
from scripts.lp_swap_cost_model_v1_readonly import (  # noqa: E402
    exit_conversion_cost_usd,
    price_impact_frac,
    slippage_bps_for_swap,
)
from scripts.lp_exit_policy_v1_readonly import (  # noqa: E402
    BreachDirection,
    BreachObservation,
    ExitMode,
    ExitPolicyConfig,
    QuoteResult,
    RiskSignals,
    RiskState,
    RpcHealth,
    build_paper_action_plan,
    classify_breach,
    evaluate_risk,
    transition_state,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool  # noqa: E402
from scripts.lp_tg_alerter_v1_readonly import (  # noqa: E402
    TelegramAlerter,
    safe_send_event,
)
from scripts.lp_shadow_gate_v1_readonly import (  # noqa: E402
    DEFAULT_DB_PATH as DEFAULT_GATE_DB_PATH,
    GateStore,
)

# Rotating free-public-RPC pool, set up in run(). Until then, calls fall back to
# the single-URL _rpc_with_retry so the pure engine + tests need no network.
_POOL = None

LEDGER_SCHEMA_VERSION = 2
ATTRIBUTION_FIELDS = (
    "entry_capital_usd", "hodl_nav", "lp_nav_ex_fee",
    "il_vs_hodl_usd", "il_vs_hodl_pct", "swap_fee_income",
    "reward_income_marked", "reward_income_realized", "reward_price_pnl",
    "gas_cost", "priority_fee", "entry_swap_cost", "exit_swap_cost",
    "slippage", "price_impact", "lvr_estimate", "exit_latency_loss",
    "switching_cost", "realized_net_pnl", "alpha_vs_hodl",
    "pnl_vs_usdc", "capital_time_weighted", "ACE",
)
ATTRIBUTION_SEMANTICS = {
    "currency": "USD",
    "reward_model": "linear_apr_paper_emission_not_farm_or_gauge_evidence",
    "reward_income_marked": "unclaimed_linear_emission_basis",
    "reward_income_realized": "paper_simulated_claim_not_onchain",
    "reward_price_pnl": "reward_token_mark_change_separate_from_emission_income",
    "lvr_estimate": "model_estimate_usd_not_observed_execution",
    "exit_latency_loss": "model_estimate_usd_not_observed_execution",
    "slippage": "USD_model_or_paper_observation",
    "price_impact": "USD_depth_model_not_observed_execution",
    "capital_time_weighted": "USD_seconds_in_range",
    "ACE": "swap_fee_income_USD_per_USD_second_in_range",
    "realized_net_pnl": "zero_until_paper_position_is_converted_to_cash",
    "exit_cost_basis": (
        "depth_model=liquidity-backed path (zero when no swap requested); "
        "flat_placeholder=missing-liquidity fallback"
    ),
}


def _rpc():
    """The active RPC entrypoint: rotating pool if initialized, else single-URL."""
    return _POOL.call if _POOL is not None else _rpc_with_retry


def _rpc_health_state():
    """Expose only observed pool health; missing evidence stays UNKNOWN."""
    if _POOL is None:
        return "UNKNOWN"
    try:
        state = str(_POOL.health_snapshot().get("state") or "UNKNOWN").upper()
    except Exception:  # noqa: BLE001 - health evidence must fail closed
        return "UNKNOWN"
    return state if state in {"NORMAL", "DEGRADED", "EXIT_ONLY"} else "UNKNOWN"


# ---------------------------------------------------------------------------
# Pure engine (unit-tested, NO network)
# ---------------------------------------------------------------------------

def init_state(*, capital, anchor, range_pct, fee_tier, dec0, dec1, last_block,
               exit_on_breach=False, exit_cost_bps=None, entry_swap_cost=0.0,
               exit_policy_enabled=False, profile="MAJORS",
               risky_token_side="token0:risky", stable_token_side="token1:quote",
               risky_inventory_target=0.25, max_exit_slippage_bps=75.0,
               rpc_health="NORMAL", major_cooldown_minutes=30,
               risk_signals=None, reward_token_price_usd=1.0,
               gas_cost=0.0, priority_fee=0.0, lvr_estimate=0.0,
               exit_latency_loss=0.0, switching_cost=0.0):
    """Build a fresh passive-position state dict.

    exit_on_breach: deprecated explicit compatibility instruction for old
      allocations. Missing fields never infer this from Tier; new callers use
      exit_policy_enabled plus combination signals.
    exit_cost_bps: conversion cost charged on exit (swap fee + slippage). If
      None, a placeholder = round(fee_tier*1e4)+10bps is used until the
      depth/slippage model (lp_swap_cost_model) is wired in to size it properly.
    """
    if exit_cost_bps is None:
        exit_cost_bps = round(float(fee_tier) * 1e4) + 10.0
    config = ExitPolicyConfig(
        profile=str(profile),
        risky_token_side=str(risky_token_side),
        stable_token_side=str(stable_token_side),
        risky_inventory_target=float(risky_inventory_target),
        max_slippage_bps=float(max_exit_slippage_bps),
        major_cooldown_minutes=int(major_cooldown_minutes),
    )
    rpc_state = RpcHealth(str(rpc_health).upper())
    paper_position = position_state_from_capital(anchor, capital, range_pct)
    baseline = paper_entry_baseline(anchor, capital, range_pct, entry_swap_cost)
    return {
        "capital": float(capital),
        "anchor": float(anchor),
        "range_pct": float(range_pct),
        "fee_tier": float(fee_tier),
        "dec0": int(dec0),
        "dec1": int(dec1),
        # liquidity for ONE unit of capital (size=1.0); fees are scaled by
        # capital afterwards, exactly like the passive replay convention.
        "l_pos_raw": position_liquidity_raw(1.0, anchor, range_pct, int(dec0), int(dec1)),
        # INV-IL-02: actual post-ratio-swap V3 legs, frozen by dataclass.
        "entry_baseline": baseline,
        # Principal-only range/liquidity state used by the single IL/NAV engine.
        "lp_principal_state": paper_position,
        "fees_quote": 0.0,
        "reward_quote": 0.0,
        "reward_accounting": {
            "unclaimed_units": 0.0,
            "unclaimed_emission_basis_usd": 0.0,
            "realized_emission_basis_usd": 0.0,
            "realized_price_pnl_usd": 0.0,
            "mark_price_usd": float(reward_token_price_usd),
            "simulated_claim_count": 0,
        },
        "capital_time": {
            "elapsed_seconds": 0.0,
            "time_in_range_seconds": 0.0,
        },
        "attribution_costs": {
            "gas_cost": float(gas_cost),
            "priority_fee": float(priority_fee),
            "exit_swap_cost": 0.0,
            "slippage": 0.0,
            "price_impact": 0.0,
            "lvr_estimate": float(lvr_estimate),
            "exit_latency_loss": float(exit_latency_loss),
            "switching_cost": float(switching_cost),
        },
        "last_block": int(last_block),
        "breaches": [],
        "in_range_now": True,
        "exit_on_breach": bool(exit_on_breach),
        "exit_cost_bps": float(exit_cost_bps),
        "exited": None,
        # WP-03 context is JSON-safe because runner snapshots are persistent I/O.
        # An explicit legacy exit flag is treated as operator-confirmed intent;
        # missing policy fields stay conservatively record-only.
        "exit_policy_context": {
            "enabled": bool(exit_policy_enabled or exit_on_breach),
            "legacy_operator_confirmed": bool(exit_on_breach),
            "profile": config.profile,
            "risky_token_side": config.risky_token_side,
            "stable_token_side": config.stable_token_side,
            "risky_inventory_target": config.risky_inventory_target,
            "max_slippage_bps": config.max_slippage_bps,
            "major_cooldown_minutes": config.major_cooldown_minutes,
            "rpc_health": rpc_state.value,
            "state": RiskState.HEALTHY.value,
            "cooldown": None,
            "substate": None,
            "alerts": [],
            "risk_signals": dict(risk_signals or {}),
        },
    }


def _do_exit(state, *, exit_price, block, l_active_raw=None):
    """Realize a position at exit_price and convert to base currency (paper).

    Frozen once set: LP value at exit + accrued fees, minus the cost of
    converting the LP holdings back to base. If the active pool liquidity is
    known (l_active_raw, from the breach swap), the depth-aware swap-cost model
    sizes that conversion (fee + real slippage); otherwise a flat exit_cost_bps
    placeholder is used. Fees are already in base, so only lp_value is converted.
    Reward is held separately and added at mark time. After exit the position
    holds base cash and accrues nothing.
    """
    cap = state["capital"]
    lp_value = lp_nav_ex_fee(state["lp_principal_state"], exit_price)
    entry_hodl = hodl_nav(state["entry_baseline"], exit_price, 1.0)
    il = il_usd(lp_value, entry_hodl)
    if l_active_raw and l_active_raw > 0:
        side = "sell_base"
        cost = exit_conversion_cost_usd(
            lp_value, l_active_raw, exit_price, state["fee_tier"],
            state["dec0"], state["dec1"], side=side,
        )
        slip_bps = slippage_bps_for_swap(
            lp_value, l_active_raw, exit_price, state["dec0"], state["dec1"], side
        )
        impact = price_impact_frac(
            lp_value, l_active_raw, exit_price, state["dec0"], state["dec1"], side
        )
        cost_basis = "depth_model"
        fallback_reason = None
    else:
        cost = lp_value * state["exit_cost_bps"] / 1e4
        slip_bps = 0.0
        impact = 0.0
        cost_basis = "flat_placeholder"
        fallback_reason = "missing_liquidity"
    costs = state["attribution_costs"]
    costs["exit_swap_cost"] = float(cost)
    costs["slippage"] = float(lp_value * slip_bps / 1e4)
    costs["price_impact"] = float(lp_value * impact)
    simulate_reward_claim(state)
    state["exited"] = {
        "block": int(block),
        "price": float(exit_price),
        "lp_value_quote": lp_value,
        "lp_nav_ex_fee_quote": lp_value,
        "il_quote": il,
        "il_pct": il_pct(il, entry_hodl),
        "fees_quote": state["fees_quote"],
        "exit_cost_quote": cost,
        "exit_cost_basis": cost_basis,
        "exit_cost_fallback_reason": fallback_reason,
        "realized_quote": lp_value - cost + state["fees_quote"],  # base cash recovered
    }
    return state


def _policy_config(state):
    ctx = state["exit_policy_context"]
    return ExitPolicyConfig(
        profile=ctx["profile"],
        risky_token_side=ctx["risky_token_side"],
        stable_token_side=ctx["stable_token_side"],
        risky_inventory_target=ctx["risky_inventory_target"],
        max_slippage_bps=ctx["max_slippage_bps"],
        major_cooldown_minutes=ctx["major_cooldown_minutes"],
    )


def _inventory_observation(state, *, price, direction, l_active_raw=None):
    """Build the mandatory directional breach observation from LP principal."""
    config = _policy_config(state)
    inv = current_inventory(state["lp_principal_state"], price)
    token0_value = inv.q0 * price
    token1_value = inv.q1
    risky_is_token0 = config.risky_token_side.lower().startswith("token0")
    risky_value = token0_value if risky_is_token0 else token1_value
    nav = inv.nav_quote
    ratio = risky_value / nav if nav > 0 else 0.0
    delta = max(0.0, risky_value - config.risky_inventory_target * nav)
    if delta > 0 and l_active_raw and l_active_raw > 0:
        side = "sell_base" if risky_is_token0 else "buy_base"
        expected_cost = exit_conversion_cost_usd(
            delta, l_active_raw, price, state["fee_tier"],
            state["dec0"], state["dec1"], side=side,
        )
    elif delta > 0:
        expected_cost = delta * state["exit_cost_bps"] / 1e4
    else:
        expected_cost = 0.0
    return BreachObservation(
        breach_direction=direction,
        post_remove_inventory_ratio=ratio,
        post_remove_delta_usd=delta,
        expected_swap_cost=expected_cost,
    ), inv


def _signals_for_breach(direction, raw, *, legacy_confirmed=False):
    values = dict(raw or {})
    values["lower_breach"] = direction is BreachDirection.LOWER
    values["upper_breach"] = direction is BreachDirection.UPPER
    values.setdefault("range_distance_fraction", 1.0)
    if legacy_confirmed:
        # Compatibility is explicit and isolated: the old boolean represented
        # an operator-confirmed exit instruction, never a missing-field default.
        if direction is BreachDirection.LOWER:
            values.setdefault("trend_continuation", True)
        else:
            values.setdefault("structural_risk_worsening", True)
    return RiskSignals(**values)


def _advance_policy(ctx, signals, observation, config, *, tier=""):
    """Advance sequential legal states for one fully observed event."""
    decision = evaluate_risk(RiskState(ctx["state"]), signals, observation, config, tier=tier)
    for _ in range(3):
        if decision.next_state is decision.previous_state or decision.next_state is RiskState.EXITING:
            break
        ctx["state"] = transition_state(decision.previous_state, decision.next_state).value
        decision = evaluate_risk(RiskState(ctx["state"]), signals, observation, config, tier=tier)
    if decision.next_state is RiskState.EXITING:
        if decision.hard_risk_override:
            ctx["state"] = transition_state(
                RiskState(ctx["state"]), RiskState.EXITING, hard_veto=True
            ).value
        else:
            ctx["state"] = transition_state(
                RiskState(ctx["state"]), RiskState.EXITING
            ).value
    elif decision.next_state is not decision.previous_state:
        ctx["state"] = transition_state(decision.previous_state, decision.next_state).value
    return decision


def _depth_quote(state, observation, *, price, l_active_raw):
    if observation.post_remove_delta_usd <= 0:
        return QuoteResult.ok(expected_slippage_bps=0.0, expected_swap_cost_usd=0.0)
    if not l_active_raw or l_active_raw <= 0:
        return QuoteResult.failed("missing_liquidity_for_quote")
    risky_is_token0 = _policy_config(state).risky_token_side.lower().startswith("token0")
    side = "sell_base" if risky_is_token0 else "buy_base"
    slip = slippage_bps_for_swap(
        observation.post_remove_delta_usd, l_active_raw, price,
        state["dec0"], state["dec1"], side,
    )
    cost = exit_conversion_cost_usd(
        observation.post_remove_delta_usd, l_active_raw, price,
        state["fee_tier"], state["dec0"], state["dec1"], side=side,
    )
    return QuoteResult.ok(expected_slippage_bps=slip, expected_swap_cost_usd=cost)


def _do_remove_only(state, *, exit_price, block, inventory, mode, plan,
                    l_active_raw=None):
    """Simulate LP removal while continuing to mark the withdrawn inventory."""
    lp_value = inventory.nav_quote
    entry_hodl = hodl_nav(state["entry_baseline"], exit_price, 1.0)
    il = il_usd(lp_value, entry_hodl)
    if plan.risk_off_complete:
        simulate_reward_claim(state)
    cost_basis = "depth_model" if l_active_raw and l_active_raw > 0 else "flat_placeholder"
    state["attribution_costs"]["exit_latency_loss"] = float(plan.exit_latency_loss_usd or 0.0)
    state["exited"] = {
        "block": int(block),
        "price": float(exit_price),
        "lp_value_quote": lp_value,
        "lp_nav_ex_fee_quote": lp_value,
        "il_quote": il,
        "il_pct": il_pct(il, entry_hodl),
        "fees_quote": state["fees_quote"],
        "exit_cost_quote": 0.0,
        "exit_cost_basis": cost_basis,
        "exit_cost_fallback_reason": None if cost_basis == "depth_model" else "missing_liquidity",
        "realized_quote": lp_value + state["fees_quote"],
        "inventory_holdings": {"q0": inventory.q0, "q1": inventory.q1},
        "exit_mode": mode.value,
        "risk_off_complete": plan.risk_off_complete,
        "paper_only": True,
    }
    return state


def _execute_policy_decision(state, decision, observation, inventory, swap):
    """Turn a decision into a paper action plan; never builds or sends a tx."""
    ctx = state["exit_policy_context"]
    config = _policy_config(state)
    mode = decision.recommended_exit_mode
    rpc_health = RpcHealth(ctx["rpc_health"])
    supplied_quote = swap.get("exit_quote")
    quote = supplied_quote if isinstance(supplied_quote, QuoteResult) else None
    if mode is not ExitMode.REMOVE_ONLY and quote is None:
        quote = _depth_quote(
            state, observation, price=swap["price"], l_active_raw=swap.get("liquidity")
        )
    predicted_ratio = observation.post_remove_inventory_ratio
    if (
        quote is not None
        and quote.succeeded
        and quote.expected_slippage_bps is not None
        and quote.expected_slippage_bps <= config.max_slippage_bps
        and rpc_health is not RpcHealth.KILLED
        and not (rpc_health is RpcHealth.EXIT_ONLY and mode is ExitMode.REMOVE_TO_TARGET)
    ):
        predicted_ratio = config.risky_inventory_target
    plan = build_paper_action_plan(
        mode=mode,
        rpc_health=rpc_health,
        quote=quote,
        config=config,
        post_trade_risky_inventory_ratio=predicted_ratio,
        actual_slippage_bps=swap.get("actual_slippage_bps"),
        exit_latency_loss_usd=swap.get("exit_latency_loss_usd"),
    )
    if mode is ExitMode.REMOVE_ONLY or not plan.swap_allowed:
        _do_remove_only(
            state, exit_price=swap["price"], block=swap["block"],
            inventory=inventory, mode=mode, plan=plan,
            l_active_raw=swap.get("liquidity"),
        )
    else:
        _do_exit(
            state, exit_price=swap["price"], block=swap["block"],
            l_active_raw=swap.get("liquidity"),
        )
        state["exited"].update({
            "exit_mode": mode.value,
            "risk_off_complete": plan.risk_off_complete,
            "paper_only": True,
        })
        state["attribution_costs"]["exit_latency_loss"] = float(
            plan.exit_latency_loss_usd or 0.0
        )
        if plan.actual_slippage_bps is not None:
            state["attribution_costs"]["slippage"] = float(
                state["exited"]["lp_value_quote"] * plan.actual_slippage_bps / 1e4
            )
    ctx["substate"] = plan.substate
    if plan.alert:
        ctx["alerts"].append(plan.block_reason)
    ctx["state"] = transition_state(
        RiskState.EXITING,
        RiskState.COOLDOWN,
        risk_off_complete=plan.risk_off_complete,
    ).value
    return plan


def update_position(state, swaps, *, now_block):
    """Advance a passive position with new swaps (block > state['last_block']).

    In-range swaps accrue fees (scaled by capital). Out-of-range swaps accrue
    NO fee and record a breach once per crossing (in->out transition). The
    anchor and capital never change — this is a passive, no-rebalance position.

    Strict WP-03 mode never exits on a lone breach.  It records the directional
    decision first, then acts only after a PRD combination or hard-risk veto.
    The deprecated explicit exit_on_breach flag is an isolated compatibility
    adapter for already-authored allocations.
    """
    if state.get("exited"):  # closed: holds base cash, accrues nothing
        state["last_block"] = int(now_block)
        return state

    anchor = state["anchor"]
    r = state["range_pct"]
    lo = anchor * (1 - r / 100)
    hi = anchor * (1 + r / 100)
    l_pos_unit = state["l_pos_raw"]
    cap = state["capital"]
    in_range = state.get("in_range_now", True)

    for s in swaps:
        if s["block"] <= state["last_block"]:
            continue
        price = s["price"]
        if lo <= price <= hi:
            fee_unit = fee_for_swap_usd(
                l_pos_unit, s["liquidity"], s["amount1"], state["fee_tier"], state["dec1"]
            )
            state["fees_quote"] += cap * fee_unit
            in_range = True
        else:
            crossed = in_range
            if in_range:  # only log the crossing, not every out-of-range tick
                direction = classify_breach(price=price, lower_bound=lo, upper_bound=hi)
                observation, inventory = _inventory_observation(
                    state, price=price, direction=direction, l_active_raw=s.get("liquidity")
                )
                ctx = state["exit_policy_context"]
                raw_signals = s.get("risk_signals", ctx.get("risk_signals"))
                if isinstance(raw_signals, RiskSignals):
                    raw_signals = asdict(raw_signals)
                signals = _signals_for_breach(
                    direction,
                    raw_signals,
                    legacy_confirmed=ctx["legacy_operator_confirmed"],
                )
                config = _policy_config(state)
                if ctx["enabled"]:
                    decision = _advance_policy(
                        ctx, signals, observation, config, tier=str(state.get("tier", ""))
                    )
                else:
                    # What-if decision is recorded, but disabled/missing policy
                    # configuration cannot mutate state or execute anything.
                    decision = evaluate_risk(
                        RiskState(ctx["state"]), signals, observation, config,
                        tier=str(state.get("tier", "")),
                    )
                event = {
                    "block": s["block"],
                    "price": price,
                    "breach_direction": decision.breach_direction.value,
                    "post_remove_inventory_ratio": decision.post_remove_inventory_ratio,
                    "post_remove_delta_usd": decision.post_remove_delta_usd,
                    "recommended_exit_mode": decision.recommended_exit_mode.value,
                    "expected_swap_cost": decision.expected_swap_cost,
                    "risk_state_before": decision.previous_state.value,
                    "risk_state_after": ctx["state"],
                    "decision_reason": decision.reason,
                    "hard_risk_override": decision.hard_risk_override,
                }
                state["breaches"].append(event)
            in_range = False
            if crossed and ctx["enabled"] and ctx["legacy_operator_confirmed"]:
                # Exact old API compatibility is explicit, never inferred from
                # tier or missing fields.  Strict policy users take the branch
                # below and are subject to quote/slippage/inventory gates.
                event["compatibility_adapter"] = True
                _do_exit(state, exit_price=price, block=s["block"],
                         l_active_raw=s.get("liquidity"))
                state["exited"].update({
                    "exit_mode": decision.recommended_exit_mode.value,
                    "paper_only": True,
                })
                ctx["state"] = RiskState.COOLDOWN.value
                state["last_block"] = int(now_block)
                state["in_range_now"] = False
                return state  # stop: position closed at the breach
            if crossed and ctx["enabled"] and decision.should_execute:
                plan = _execute_policy_decision(state, decision, observation, inventory, s)
                event["action_plan"] = asdict(plan)
                event["risk_state_after"] = ctx["state"]
                state["last_block"] = int(now_block)
                state["in_range_now"] = False
                return state

    state["last_block"] = int(now_block)
    state["in_range_now"] = in_range
    return state


def mark_position(state, current_price):
    """Mark the position to market at current_price (quote-token units).

    If the position has exited, current_price is ignored: it holds base cash, so
    the marks are the frozen realized values (plus reward accrued to exit).
    """
    cap = state["capital"]
    current_hodl = hodl_nav(state["entry_baseline"], current_price, 1.0)
    if state.get("exited"):
        ex = state["exited"]
        holdings = ex.get("inventory_holdings")
        if holdings is not None:
            principal_now = holdings["q0"] * current_price + holdings["q1"]
            current_total = principal_now + ex["fees_quote"] + state["reward_quote"]
            net = current_total - cap
            return {
                "lp_value_quote": principal_now,
                "il_quote": ex["il_quote"],
                "fees_quote": ex["fees_quote"],
                "net_quote": net,
                "net_pct": (net / cap * 100) if cap else 0.0,
                "hodl_nav_quote": current_hodl,
                "lp_nav_ex_fee_quote": ex["lp_nav_ex_fee_quote"],
                "il_vs_hodl_quote": ex["il_quote"],
                "il_vs_hodl_pct": ex["il_pct"],
                "realized_il_at_exit_quote": ex["il_quote"],
                "current_total_nav_quote": current_total,
                "pnl_vs_usdc_quote": pnl_vs_usdc(current_total, cap),
                "alpha_vs_hodl_quote": alpha_vs_hodl(current_total, current_hodl),
                "exited": True,
                "exit_price": ex["price"],
                "exit_cost_quote": ex["exit_cost_quote"],
            }
        realized = ex["realized_quote"]
        current_total = realized + state["reward_quote"]
        net = current_total - cap
        # No LP exists after exit: freeze the realized exit observation.  The
        # counterfactual HODL basket and alpha continue marking below, so the
        # post-exit opportunity cost is not mislabeled as impermanent loss.
        principal_at_exit = ex["lp_nav_ex_fee_quote"]
        realized_il = ex["il_quote"]
        return {
            "lp_value_quote": realized,  # now base cash, not an LP position
            "il_quote": realized_il,
            "fees_quote": ex["fees_quote"],
            "net_quote": net,
            "net_pct": (net / cap * 100) if cap else 0.0,
            "hodl_nav_quote": current_hodl,
            "lp_nav_ex_fee_quote": principal_at_exit,
            "il_vs_hodl_quote": realized_il,
            "il_vs_hodl_pct": ex["il_pct"],
            "realized_il_at_exit_quote": realized_il,
            "current_total_nav_quote": current_total,
            "pnl_vs_usdc_quote": pnl_vs_usdc(current_total, cap),
            "alpha_vs_hodl_quote": alpha_vs_hodl(current_total, current_hodl),
            "exited": True,
            "exit_price": ex["price"],
            "exit_cost_quote": ex["exit_cost_quote"],
        }
    lp_value = lp_nav_ex_fee(state["lp_principal_state"], current_price)
    il = il_usd(lp_value, current_hodl)
    fees = state["fees_quote"]
    net = lp_value + fees - cap
    net_pct = (net / cap * 100) if cap else 0.0
    current_total = lp_value + fees + state["reward_quote"]
    return {
        "lp_value_quote": lp_value,
        "il_quote": il,
        "fees_quote": fees,
        "net_quote": net,
        "net_pct": net_pct,
        "hodl_nav_quote": current_hodl,
        "lp_nav_ex_fee_quote": lp_value,
        "il_vs_hodl_quote": il,
        "il_vs_hodl_pct": il_pct(il, current_hodl),
        "current_total_nav_quote": current_total,
        "pnl_vs_usdc_quote": pnl_vs_usdc(current_total, cap),
        "alpha_vs_hodl_quote": alpha_vs_hodl(current_total, current_hodl),
        "exited": False,
    }


def accrue_reward(capital, reward_apr_pct, elapsed_secs):
    """Linear reward income over wall-clock time. Pure."""
    return float(capital) * (float(reward_apr_pct) / 100.0) * (float(elapsed_secs) / (365.0 * 86400.0))


def _reward_accounting(state):
    """Return the v2 reward sub-ledger, adapting in-memory v1 state safely."""
    if "reward_accounting" not in state:
        legacy = max(0.0, float(state.get("reward_quote", 0.0)))
        state["reward_accounting"] = {
            "unclaimed_units": legacy,
            "unclaimed_emission_basis_usd": legacy,
            "realized_emission_basis_usd": 0.0,
            "realized_price_pnl_usd": 0.0,
            "mark_price_usd": 1.0,
            "simulated_claim_count": 0,
        }
    return state["reward_accounting"]


def _sync_reward_quote(state):
    reward = _reward_accounting(state)
    unclaimed_value = reward["unclaimed_units"] * reward["mark_price_usd"]
    realized_value = (
        reward["realized_emission_basis_usd"] + reward["realized_price_pnl_usd"]
    )
    state["reward_quote"] = float(unclaimed_value + realized_value)


def mark_reward_price(state, *, reward_token_price_usd):
    """Revalue unclaimed paper reward units; no price source is fabricated."""
    price = float(reward_token_price_usd)
    if price <= 0.0:
        raise ValueError("reward_token_price_usd must be > 0")
    _reward_accounting(state)["mark_price_usd"] = price
    _sync_reward_quote(state)
    return state


def accrue_reward_ledger(state, emitted_income_usd, *, reward_token_price_usd):
    """Accrue linear paper emissions at the supplied reward-token mark.

    The emitted USD is an APR-model income basis, not farm/gauge evidence.
    Token units make later price changes independently attributable.
    """
    income = float(emitted_income_usd)
    if income < 0.0:
        raise ValueError("emitted_income_usd must be >= 0")
    mark_reward_price(state, reward_token_price_usd=reward_token_price_usd)
    reward = _reward_accounting(state)
    reward["unclaimed_units"] += income / reward["mark_price_usd"]
    reward["unclaimed_emission_basis_usd"] += income
    _sync_reward_quote(state)
    return state


def simulate_reward_claim(state):
    """Move unclaimed emissions into the paper-realized bucket.

    This is bookkeeping only: it never calls a gauge, wallet, signer or RPC.
    """
    reward = _reward_accounting(state)
    basis = reward["unclaimed_emission_basis_usd"]
    proceeds = reward["unclaimed_units"] * reward["mark_price_usd"]
    reward["realized_emission_basis_usd"] += basis
    reward["realized_price_pnl_usd"] += proceeds - basis
    reward["unclaimed_units"] = 0.0
    reward["unclaimed_emission_basis_usd"] = 0.0
    reward["simulated_claim_count"] += 1
    _sync_reward_quote(state)
    return state


def accrue_capital_time(state, elapsed_seconds):
    """Accrue wall-clock exposure; in-range capital uses USD-seconds."""
    elapsed = max(0.0, float(elapsed_seconds))
    clock = state.setdefault(
        "capital_time", {"elapsed_seconds": 0.0, "time_in_range_seconds": 0.0}
    )
    clock["elapsed_seconds"] += elapsed
    if state.get("in_range_now", False) and not state.get("exited"):
        clock["time_in_range_seconds"] += elapsed
    return state


def cumulative_fee_prediction_usd(state, fee_apr_pct):
    """Cumulative paper fee prediction over observed in-range capital time.

    ``fee_apr_pct`` is the conservative on-chain fee APR frozen in the
    allocation.  Missing/non-finite/non-positive evidence returns ``None`` so
    the §12.0 gate reports UNKNOWN instead of a fabricated zero error.
    """
    try:
        apr = float(fee_apr_pct)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(apr) or apr <= 0.0:
        return None
    capital_time = float(state.get("capital_time", {}).get("time_in_range_seconds", 0.0))
    predicted = float(state["capital"]) * (apr / 100.0) * capital_time / (365.0 * 86400.0)
    return predicted if math.isfinite(predicted) and predicted > 0.0 else None


def attribution_ledger(state, mark):
    """Build the PRD v2.1 section 11.1 per-position attribution record."""
    reward = _reward_accounting(state)
    unclaimed_basis = float(reward["unclaimed_emission_basis_usd"])
    realized_basis = float(reward["realized_emission_basis_usd"])
    unclaimed_price_pnl = (
        reward["unclaimed_units"] * reward["mark_price_usd"] - unclaimed_basis
    )
    reward_price_pnl = float(reward["realized_price_pnl_usd"] + unclaimed_price_pnl)
    clock = state.get("capital_time", {})
    capital_time = float(state["capital"] * float(clock.get("time_in_range_seconds", 0.0)))
    fees = float(state["fees_quote"])
    costs = state.get("attribution_costs", {})
    entry_cost = float(state["entry_baseline"].entry_swap_cost)
    external_costs = (
        entry_cost
        + float(costs.get("gas_cost", 0.0))
        + float(costs.get("priority_fee", 0.0))
        + float(costs.get("switching_cost", 0.0))
        + (float(costs.get("exit_latency_loss", 0.0)) if state.get("exited") else 0.0)
    )
    pnl_cash_adjusted = float(mark["pnl_vs_usdc_quote"]) - external_costs
    alpha_adjusted = float(mark["alpha_vs_hodl_quote"]) - external_costs
    exited = state.get("exited") or {}
    fully_cash = bool(state.get("exited")) and "inventory_holdings" not in exited
    ledger = {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "entry_capital_usd": float(state["capital"]),
        "hodl_nav": float(mark["hodl_nav_quote"]),
        "lp_nav_ex_fee": float(mark["lp_nav_ex_fee_quote"]),
        "il_vs_hodl_usd": float(mark["il_vs_hodl_quote"]),
        "il_vs_hodl_pct": float(mark["il_vs_hodl_pct"]),
        "swap_fee_income": fees,
        "reward_income_marked": unclaimed_basis,
        "reward_income_realized": realized_basis,
        "reward_price_pnl": reward_price_pnl,
        "gas_cost": float(costs.get("gas_cost", 0.0)),
        "priority_fee": float(costs.get("priority_fee", 0.0)),
        "entry_swap_cost": entry_cost,
        "exit_swap_cost": float(costs.get("exit_swap_cost", 0.0)),
        "slippage": float(costs.get("slippage", 0.0)),
        "price_impact": float(costs.get("price_impact", 0.0)),
        "lvr_estimate": float(costs.get("lvr_estimate", 0.0)),
        "exit_latency_loss": float(costs.get("exit_latency_loss", 0.0)),
        "switching_cost": float(costs.get("switching_cost", 0.0)),
        "realized_net_pnl": pnl_cash_adjusted if fully_cash else 0.0,
        "alpha_vs_hodl": alpha_adjusted,
        "pnl_vs_usdc": pnl_cash_adjusted,
        "capital_time_weighted": capital_time,
        "ACE": fees / capital_time if capital_time > 0.0 else 0.0,
        "attribution_semantics": dict(ATTRIBUTION_SEMANTICS),
    }
    if state.get("exited"):
        ledger["exit_cost_basis"] = exited.get("exit_cost_basis", "flat_placeholder")
        ledger["exit_cost_fallback_reason"] = exited.get("exit_cost_fallback_reason")
    else:
        ledger["exit_cost_basis"] = None
        ledger["exit_cost_fallback_reason"] = None
    return ledger


def read_heartbeat_compatible(path):
    """Read summary metrics from either legacy v1 or ledger-v2 heartbeat."""
    from scripts.lp_report_digest_v1_readonly import summarize_heartbeat

    summary = summarize_heartbeat(path)
    version = 1
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(record, dict):
                    version = int(record.get("ledger_schema_version", 1))
    except OSError:
        pass
    return {"ledger_schema_version": version, **summary}


# ---------------------------------------------------------------------------
# Runner (network)
# ---------------------------------------------------------------------------

def _now_utc():
    return datetime.now(timezone.utc)


def _latest_block():
    return int(_rpc()("eth_blockNumber", []), 16)


def _report_dir(out):
    if out:
        d = out
    else:
        stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
        d = os.path.join(_REPO_ROOT, "reports", "lp_portfolio_paper_runner", stamp)
    os.makedirs(d, exist_ok=True)
    return d


def _load_allocation(path):
    with open(path) as f:
        data = json.load(f)
    allocs = data.get("allocations", [])
    if not allocs:
        raise SystemExit(f"no allocations in {path}")
    return allocs


def _init_book(allocs, *, entry_window_blocks, latest):
    """Tick 0: fetch a small recent window per pool to set the entry anchor."""
    book = []
    for a in allocs:
        pool = a["pool"]
        dec0, dec1 = int(a["dec0"]), int(a["dec1"])
        from_b = max(0, latest - entry_window_blocks)
        swaps = fetch_pool_swaps(pool, from_b, latest, dec0, dec1, rpc_call=_rpc())
        if not swaps:
            print(f"[warn] {a['symbol']} {pool}: no swaps in entry window; skipping")
            continue
        anchor = swaps[-1]["price"]
        tier = str(a.get("tier", "")).upper()
        # Missing WP-03 fields are conservatively record-only for every tier.
        # Only an explicit old boolean enables the isolated compatibility path.
        exit_on_breach = bool(a.get("exit_on_breach", False))
        policy_keys = {
            "profile", "risky_token_side", "stable_token_side",
            "risky_inventory_target", "max_exit_slippage_bps", "rpc_health",
        }
        exit_policy_enabled = bool(
            a.get("exit_policy_enabled", any(key in a for key in policy_keys))
        )
        st = init_state(
            capital=a["usd"], anchor=anchor, range_pct=a["range_pct"],
            fee_tier=a["fee_tier"], dec0=dec0, dec1=dec1, last_block=latest,
            exit_on_breach=exit_on_breach, exit_cost_bps=a.get("exit_cost_bps"),
            exit_policy_enabled=exit_policy_enabled,
            profile=a.get("profile", "MAJORS"),
            risky_token_side=a.get("risky_token_side", "token0:risky"),
            stable_token_side=a.get("stable_token_side", "token1:quote"),
            risky_inventory_target=a.get("risky_inventory_target", 0.25),
            max_exit_slippage_bps=a.get("max_exit_slippage_bps", 75.0),
            rpc_health=a.get("rpc_health", "NORMAL"),
            major_cooldown_minutes=a.get("major_cooldown_minutes", 30),
            risk_signals=a.get("risk_signals"),
            reward_token_price_usd=a.get("reward_token_price_usd", 1.0),
            gas_cost=a.get("gas_cost", 0.0),
            priority_fee=a.get("priority_fee", 0.0),
            lvr_estimate=a.get("lvr_estimate", a.get("lvr_estimate_model", 0.0)),
            exit_latency_loss=a.get(
                "exit_latency_loss", a.get("exit_latency_loss_model", 0.0)
            ),
            switching_cost=a.get("switching_cost", 0.0),
        )
        st["tier"] = tier
        book.append({
            "symbol": a["symbol"], "project": a.get("project", ""),
            "tier": a.get("tier", ""), "pool": pool,
            "reward_apr": float(a.get("reward_apr", 0.0)),
            "fee_apr_onchain": a.get("fee_apr_onchain"),
            "reward_price_usd": float(a.get("reward_token_price_usd", 1.0)),
            "last_price": anchor, "state": st,
        })
        print(f"[init] {a['symbol']:14s} {a['tier']} cap={a['usd']:.0f} "
              f"anchor={anchor:.6g} range=±{a['range_pct']:.2f}% "
              f"exit_on_breach={exit_on_breach} pool={pool}")
        time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
    if not book:
        raise SystemExit("no pools initialized (no swaps found)")
    return book


def _runner_exit_alert_status(state):
    exited = state.get("exited")
    if not exited:
        return None
    ctx = state["exit_policy_context"]
    complete = exited.get("risk_off_complete")
    if complete is True:
        return "risk_off_complete"
    if complete is False and ctx.get("state") == RiskState.EXITING.value:
        return "exit_staged"
    # The explicit legacy compatibility path predates risk_off_complete but
    # converts to base cash and moves directly to COOLDOWN.
    if complete is None and ctx.get("legacy_operator_confirmed"):
        return "risk_off_complete"
    return None


def _emit_runner_alerts(pool_record, alerter):
    """Emit each semantic runner transition once; never mutate accounting."""
    if alerter is None:
        return
    state = pool_record["state"]
    cursor = pool_record.setdefault(
        "_tg_alert_cursor",
        {"breaches": 0, "exit_status": None, "rpc_health": None},
    )
    symbol = pool_record["symbol"]
    pool = pool_record["pool"]

    breach_count = len(state["breaches"])
    delivered_breaches = cursor["breaches"]
    for index, event in enumerate(
        state["breaches"][cursor["breaches"]:breach_count],
        start=cursor["breaches"],
    ):
        direction = event.get("breach_direction", "UNKNOWN")
        result = safe_send_event(
            alerter,
            "breach",
            f"{symbol} pool={pool} direction={direction} block={event.get('block')}",
            severity="WARNING",
            throttle_key=f"runner:{pool}:breach:{direction}",
        )
        if getattr(result, "delivery", None) == "THROTTLED":
            break
        delivered_breaches = index + 1
    cursor["breaches"] = delivered_breaches

    exit_status = _runner_exit_alert_status(state)
    if exit_status is not None and exit_status != cursor["exit_status"]:
        exited = state["exited"]
        if exit_status == "exit_staged":
            message = (
                f"{symbol} pool={pool} LP removed but risky inventory remains; "
                "state=EXITING risk_off_complete=false"
            )
            severity = "WARNING"
        else:
            message = (
                f"{symbol} pool={pool} risk-off complete "
                f"mode={exited.get('exit_mode', 'LEGACY')}"
            )
            severity = "INFO"
        result = safe_send_event(
            alerter,
            exit_status,
            message,
            severity=severity,
            throttle_key=f"runner:{pool}:{exit_status}",
        )
        if getattr(result, "delivery", None) != "THROTTLED":
            cursor["exit_status"] = exit_status
    elif exit_status is None:
        cursor["exit_status"] = None

    rpc_health = str(state["exit_policy_context"].get("rpc_health", "NORMAL")).upper()
    if rpc_health == RpcHealth.KILLED.value and cursor["rpc_health"] != rpc_health:
        result = safe_send_event(
            alerter,
            "kill",
            f"{symbol} pool={pool} RPC health KILLED; all actions blocked",
            severity="CRITICAL",
            throttle_key=f"runner:{pool}:kill",
        )
        if getattr(result, "delivery", None) != "THROTTLED":
            cursor["rpc_health"] = rpc_health
    elif rpc_health != RpcHealth.KILLED.value:
        cursor["rpc_health"] = rpc_health


def _tick(book, *, last_ts, alerter=None):
    latest = _latest_block()
    now = _now_utc()
    elapsed = (now - last_ts).total_seconds()
    by_pool = []
    portfolio_net = 0.0
    portfolio_nav = 0.0
    for p in book:
        st = p["state"]
        staged_inventory = bool(
            st.get("exited")
            and st["exited"].get("inventory_holdings") is not None
            and st["exited"].get("risk_off_complete") is False
            and st["exit_policy_context"].get("state") == RiskState.EXITING.value
        )
        if st.get("exited") and not staged_inventory:
            # closed position holds base cash: no RPC, no further accrual.
            mk = mark_position(st, p["last_price"])
            pool_net = mk["net_quote"]  # exited mark already includes reward
            n_swaps, new_breach = 0, False
        elif staged_inventory:
            # LP liquidity is gone, but risky withdrawn inventory remains. Keep
            # a read-only market mark and block all LP fee/reward accrual until
            # a later execution path proves risk-off complete (INV-EXIT-01).
            swaps = fetch_pool_swaps(p["pool"], st["last_block"] + 1, latest,
                                     st["dec0"], st["dec1"], rpc_call=_rpc())
            update_position(st, swaps, now_block=latest)
            if swaps:
                p["last_price"] = swaps[-1]["price"]
            mk = mark_position(st, p["last_price"])
            pool_net = mk["net_quote"]
            n_swaps, new_breach = len(swaps), False
            time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
        else:
            swaps = fetch_pool_swaps(p["pool"], st["last_block"] + 1, latest,
                                     st["dec0"], st["dec1"], rpc_call=_rpc())
            n_breach_before = len(st["breaches"])
            # book reward for elapsed BEFORE update, so a same-tick exit keeps it
            accrue_capital_time(st, elapsed)
            accrue_reward_ledger(
                st,
                accrue_reward(st["capital"], p["reward_apr"], elapsed),
                reward_token_price_usd=p.get("reward_price_usd", 1.0),
            )
            update_position(st, swaps, now_block=latest)
            if swaps:
                p["last_price"] = swaps[-1]["price"]
            mk = mark_position(st, p["last_price"])
            # active mark excludes reward; exited mark includes it
            pool_net = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
            n_swaps = len(swaps)
            new_breach = len(st["breaches"]) > n_breach_before
            time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
        portfolio_net += pool_net
        _emit_runner_alerts(p, alerter)
        attribution = attribution_ledger(st, mk)
        portfolio_nav += attribution["entry_capital_usd"] + attribution["pnl_vs_usdc"]
        by_pool.append({
            "symbol": p["symbol"], "tier": p["tier"], "pool": p["pool"],
            "net_pct": round(mk["net_pct"], 4),
            "net_usd": round(pool_net, 2),
            "fees": round(st["fees_quote"], 4),
            "il": round(mk["il_quote"], 4),
            "hodl_nav": round(mk["hodl_nav_quote"], 4),
            "lp_nav_ex_fee": round(mk["lp_nav_ex_fee_quote"], 4),
            "current_total_nav": round(mk["current_total_nav_quote"], 4),
            "pnl_vs_usdc": round(mk["pnl_vs_usdc_quote"], 4),
            "alpha_vs_hodl": round(mk["alpha_vs_hodl_quote"], 4),
            "reward": round(st["reward_quote"], 4),
            "lp_value": round(mk["lp_value_quote"], 2),
            "n_swaps": n_swaps,
            "breaches": len(st["breaches"]),
            "new_breach": new_breach,
            "in_range": st["in_range_now"],
            "exited": bool(st.get("exited")),
            "risk_state": st["exit_policy_context"]["state"],
            "exit_substate": st["exit_policy_context"]["substate"],
            "fee_prediction_usd": cumulative_fee_prediction_usd(
                st, p.get("fee_apr_onchain")
            ),
            **attribution,
        })
    return {"ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "ts_utc": now.isoformat(), "block": latest,
            "rpc_health": _rpc_health_state(),
            "portfolio_net_usd": round(portfolio_net, 2),
            "portfolio_nav_usd": round(portfolio_nav, 2),
            "by_pool": by_pool}, now


def _write_pid(run_dir):
    with open(os.path.join(run_dir, "runner.pid"), "w") as f:
        f.write(str(os.getpid()))


def _append_heartbeat(run_dir, rec, tick):
    rec = {"tick": tick, **rec}
    with open(os.path.join(run_dir, "heartbeat.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


def _record_gate_observation(store, source_run, tick, rec):
    """Normal runner-tick hook; kept injectable for deterministic tests."""
    return store.record_heartbeat(source_run, tick, rec)


_CSV_HEADER = "ts_utc,tick,block,portfolio_net_usd\n"


def _append_hourly_csv(run_dir, rec, tick):
    path = os.path.join(run_dir, "portfolio_state_hourly.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write(_CSV_HEADER)
        f.write(f"{rec['ts_utc']},{tick},{rec['block']},{rec['portfolio_net_usd']}\n")


def run(allocation_path, *, poll_secs=1800, max_ticks=None, out=None,
        entry_window_blocks=4000, chain="base", alerter=None,
        gate_db=DEFAULT_GATE_DB_PATH):
    global _POOL
    _POOL = RpcPool(chain)
    selected_alerter = TelegramAlerter.from_env() if alerter is None else alerter
    allocs = _load_allocation(allocation_path)
    run_dir = _report_dir(out)
    gate_store = GateStore(gate_db) if gate_db else None
    source_run = str(Path(run_dir).resolve())
    _write_pid(run_dir)
    print(f"[run] dir={run_dir} pools={len(allocs)} poll={poll_secs}s "
          f"max_ticks={max_ticks} chain={chain} "
          f"rpc_pool={len(_POOL._endpoints)} endpoints (rotating, free public)")

    latest = _latest_block()
    book = _init_book(allocs, entry_window_blocks=entry_window_blocks, latest=latest)
    # snapshot the resolved book for reproducibility
    with open(os.path.join(run_dir, "book_init.json"), "w") as f:
        json.dump([{k: v for k, v in p.items() if k != "state"} | {
            "anchor": p["state"]["anchor"], "capital": p["state"]["capital"],
            "range_pct": p["state"]["range_pct"], "fee_tier": p["state"]["fee_tier"],
        } for p in book], f, indent=2)

    last_ts = _now_utc()
    last_hour = -1
    tick = 0
    stop = {"flag": False}

    def _handle(signum, frame):  # graceful flush
        stop["flag"] = True
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    try:
        while not stop["flag"]:
            rec, last_ts = _tick(book, last_ts=last_ts, alerter=selected_alerter)
            _append_heartbeat(run_dir, rec, tick)
            if gate_store is not None:
                _record_gate_observation(gate_store, source_run, tick, rec)
            cur_hour = datetime.fromisoformat(rec["ts_utc"]).hour
            if cur_hour != last_hour:
                _append_hourly_csv(run_dir, rec, tick)
                last_hour = cur_hour
            print(f"[tick {tick}] blk={rec['block']} net=${rec['portfolio_net_usd']:.2f} "
                  + " ".join(f"{p['symbol']}:{p['net_pct']:+.2f}%"
                             + ("!" if p["new_breach"] else "")
                             + ("·EXIT" if p.get("exited") else ("" if p["in_range"] else "·OOR"))
                             for p in rec["by_pool"]))
            tick += 1
            if max_ticks is not None and tick >= max_ticks:
                break
            if stop["flag"]:
                break
            for _ in range(int(poll_secs)):
                if stop["flag"]:
                    break
                time.sleep(1)
    finally:
        _flush_state(run_dir, book, tick)
        print(f"[done] {tick} ticks; state flushed to {run_dir}")


def _flush_state(run_dir, book, tick):
    snap = {"ledger_schema_version": LEDGER_SCHEMA_VERSION, "final_tick": tick, "pools": []}
    for p in book:
        st = p["state"]
        mk = mark_position(st, p["last_price"])
        net_quote = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
        attribution = attribution_ledger(st, mk)
        snap["pools"].append({
            "symbol": p["symbol"], "tier": p["tier"], "pool": p["pool"],
            "capital": st["capital"], "anchor": st["anchor"],
            "range_pct": st["range_pct"], "last_price": p["last_price"],
            "fees_quote": st["fees_quote"], "reward_quote": st["reward_quote"],
            "il_quote": mk["il_quote"], "lp_value_quote": mk["lp_value_quote"],
            "hodl_nav_quote": mk["hodl_nav_quote"],
            "lp_nav_ex_fee_quote": mk["lp_nav_ex_fee_quote"],
            "il_vs_hodl_quote": mk["il_vs_hodl_quote"],
            "il_vs_hodl_pct": mk["il_vs_hodl_pct"],
            "current_total_nav_quote": mk["current_total_nav_quote"],
            "pnl_vs_usdc_quote": mk["pnl_vs_usdc_quote"],
            "alpha_vs_hodl_quote": mk["alpha_vs_hodl_quote"],
            "net_quote": net_quote,
            "net_pct": mk["net_pct"], "n_breaches": len(st["breaches"]),
            "in_range": st["in_range_now"], "breaches": st["breaches"],
            "exit_on_breach": st.get("exit_on_breach", False),
            "exit_policy_context": st["exit_policy_context"],
            "exited": st.get("exited"),
            **attribution,
        })
    with open(os.path.join(run_dir, "final_state.json"), "w") as f:
        json.dump(snap, f, indent=2)


# ---------------------------------------------------------------------------
# Self-test (pure, no network)
# ---------------------------------------------------------------------------

def run_self_test():
    dec0 = dec1 = 18
    fee_tier = 0.003
    r = 10.0
    anchor = 1.0
    st = init_state(capital=1000.0, anchor=anchor, range_pct=r,
                    fee_tier=fee_tier, dec0=dec0, dec1=dec1, last_block=0)
    # Deep enough to keep the paper exit quote economically valid in this
    # invariant smoke test (dec0=dec1=18 => human liquidity 1e6).
    L = 10 ** 24
    amt1 = 10 ** 18  # 1.0 token1 raw
    # two in-range swaps
    in_swaps = [
        {"block": 1, "price": 1.00, "liquidity": L, "amount1": amt1},
        {"block": 2, "price": 1.02, "liquidity": L, "amount1": amt1},
    ]
    update_position(st, in_swaps, now_block=2)
    assert st["fees_quote"] > 0, "in-range swaps must accrue fees"
    assert st["breaches"] == [], "no breach while in range"
    assert st["anchor"] == anchor, "anchor must not move (passive)"
    fees_after_in = st["fees_quote"]

    mk = mark_position(st, anchor)
    assert abs(mk["il_quote"]) < 1e-6, "round-trip to anchor => IL ~ 0"
    assert mk["net_quote"] > 0, "net positive once fees accrued at anchor"

    # an out-of-range swap: no fee, one breach, anchor unchanged
    out_swaps = [{"block": 3, "price": 1.50, "liquidity": L, "amount1": amt1}]
    update_position(st, out_swaps, now_block=3)
    assert st["fees_quote"] == fees_after_in, "out-of-range swap accrues no fee"
    assert len(st["breaches"]) == 1, "one breach recorded"
    assert st["anchor"] == anchor, "anchor still unchanged (no rebalance)"

    mk2 = mark_position(st, 1.20)
    assert mk2["il_quote"] < 0, "price move => IL < 0"

    # reward: linear, zero at zero elapsed
    assert accrue_reward(1000.0, 50.0, 0) == 0.0
    half = accrue_reward(1000.0, 50.0, 365 * 86400 / 2)
    full = accrue_reward(1000.0, 50.0, 365 * 86400)
    assert abs(full - 500.0) < 1e-6, "50% APR for 1y on 1000 => 500"
    assert abs(half * 2 - full) < 1e-9, "reward linear in elapsed"
    assert abs(accrue_reward(2000.0, 50.0, 365 * 86400) - 1000.0) < 1e-6, "linear in capital"

    # Explicit legacy compatibility: closes, converts to base, stops accruing.
    stb = init_state(capital=1000.0, anchor=1.0, range_pct=r, fee_tier=fee_tier,
                     dec0=dec0, dec1=dec1, last_block=0, exit_on_breach=True)
    update_position(stb, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": amt1}], now_block=1)
    assert stb["exited"] is None, "in-range: not exited"
    update_position(stb, [{"block": 2, "price": 1.5, "liquidity": L, "amount1": amt1}], now_block=2)
    assert stb["exited"] is not None, "explicit legacy exit instruction must remain compatible"
    assert stb["exited"]["exit_cost_quote"] > 0, "exit pays a conversion cost"
    fees_at_exit = stb["fees_quote"]
    # further swaps after exit accrue nothing (holds base cash)
    update_position(stb, [{"block": 3, "price": 1.0, "liquidity": L, "amount1": amt1}], now_block=3)
    assert stb["fees_quote"] == fees_at_exit, "no accrual after exit"
    mkb = mark_position(stb, 9.99)  # current price ignored once exited
    assert mkb["exited"] is True and mkb["lp_value_quote"] == stb["exited"]["realized_quote"]

    print("self-test OK: fees accrue in-range, breaches logged out-of-range, "
          "anchor passive, IL sign correct, reward linear, legacy adapter works.")


def main():
    ap = argparse.ArgumentParser(description="Multi-pool LP paper-shadow runner (read-only)")
    ap.add_argument("--allocation", help="path to allocator allocation.json")
    ap.add_argument("--poll-secs", type=int, default=1800,
                    help="seconds between ticks; default 1800 (30min) keeps "
                         "free-RPC load low")
    ap.add_argument("--chain", default="base",
                    help="chain key for the rotating free-RPC pool")
    ap.add_argument("--max-ticks", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--entry-window-blocks", type=int, default=4000)
    ap.add_argument(
        "--gate-db", default=str(DEFAULT_GATE_DB_PATH),
        help="scanner.db receiving automatic §12.0 evidence each successful tick",
    )
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return
    if not args.allocation:
        ap.error("--allocation is required (or use --self-test)")
    run(args.allocation, poll_secs=args.poll_secs, max_ticks=args.max_ticks,
        out=args.out, entry_window_blocks=args.entry_window_blocks, chain=args.chain,
        gate_db=args.gate_db)


if __name__ == "__main__":
    main()
