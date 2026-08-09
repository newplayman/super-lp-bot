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
import base64
import binascii
from dataclasses import asdict
import json
import math
import os
import re
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
    EntryBaseline,
    V3PositionState,
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
    can_reenter,
    classify_breach,
    cooldown_requirement,
    evaluate_risk,
    transition_state,
)
from scripts.lp_netcover_engine_v1_readonly import (  # noqa: E402
    NETCOVER_SHADOW,
    absolute_profit_gate,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool  # noqa: E402
from scripts.lp_tg_alerter_v1_readonly import (  # noqa: E402
    TelegramAlerter,
    safe_send_event,
)
from scripts.lp_shadow_gate_v1_readonly import (  # noqa: E402
    DEFAULT_DB_PATH as DEFAULT_GATE_DB_PATH,
    GateStore,
    root_position_identity,
)

# Rotating free-public-RPC pool, set up in run(). Until then, calls fall back to
# the single-URL _rpc_with_retry so the pure engine + tests need no network.
_POOL = None

ORCA_WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
ORCA_WHIRLPOOL_ACCOUNT_SIZE = 653
ORCA_WHIRLPOOL_DISCRIMINATOR = bytes.fromhex("3f95d10ce1806309")
ORCA_WHIRLPOOL_ADAPTER = "orca_whirlpool_account_v1"
ORCA_WHIRLPOOL_PROTOCOL = "orca_whirlpool"

LEDGER_SCHEMA_VERSION = 2
REENTRY_EVIDENCE_MAX_AGE_SECONDS = 3600.0
MAX_REENTRIES_PER_ROOT = 3
RUNNER_CHECKPOINT_SCHEMA_VERSION = 1
_RUNNER_CHECKPOINT_FILE = "runner_checkpoint.json"
_REENTRY_IDENTITY_SUFFIX = re.compile(r":reentry:(\d+)$")
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
                    # Disabled/missing policy keeps soft decisions as what-if
                    # records, but a hard veto overrides Tier and the switch.
                    decision = evaluate_risk(
                        RiskState(ctx["state"]), signals, observation, config,
                        tier=str(state.get("tier", "")),
                    )
                    if decision.hard_risk_override and decision.should_execute:
                        ctx["state"] = transition_state(
                            RiskState(ctx["state"]), RiskState.EXITING,
                            hard_veto=True,
                        ).value
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
            if (
                crossed
                and decision.should_execute
                and (ctx["enabled"] or decision.hard_risk_override)
            ):
                plan = _execute_policy_decision(state, decision, observation, inventory, s)
                event["action_plan"] = asdict(plan)
                event["exit_cost_basis"] = state["exited"]["exit_cost_basis"]
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
    if state.get("reentry_of"):
        ledger["reentry_of"] = str(state["reentry_of"])
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
    if _POOL is not None and getattr(_POOL, "chain", None) == "solana":
        slot = _rpc()("getSlot", [])
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ValueError("Solana getSlot returned an invalid slot")
        return slot
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


def _reentry_lineage(position_identity):
    """Validate one persisted identity and return its root and sequence."""
    if not isinstance(position_identity, str) or not position_identity.strip():
        raise ValueError("persisted position_identity must be a non-empty string")
    identity = position_identity.strip()
    root_identity = root_position_identity(identity)
    if not root_identity:
        raise ValueError("persisted position_identity has an empty root")
    if identity == root_identity:
        if ":reentry:" in identity:
            raise ValueError("persisted re-entry identity has a malformed suffix")
        return root_identity, 0
    suffix = _REENTRY_IDENTITY_SUFFIX.search(identity)
    if suffix is None:
        raise ValueError("persisted re-entry identity has an invalid suffix")
    sequence = int(suffix.group(1))
    if sequence <= 0 or identity != f"{root_identity}:reentry:{sequence}":
        raise ValueError("persisted re-entry identity has an invalid lineage")
    return root_identity, sequence


def _restore_reentry_state_from_final(run_dir, book):
    """Restore anti-churn lineage when restarting an existing runner output.

    ``_init_book`` intentionally builds fresh pricing/accounting state from the
    live allocation.  The W1 re-entry allowance, however, is durable policy
    state: silently resetting it on process restart would permit a fourth (or
    later) re-entry.  Recover that narrow state from the runner's own final
    snapshot before the first tick.  Any matching but malformed or internally
    inconsistent snapshot aborts startup fail-closed.
    """
    final_path = os.path.join(run_dir, "final_state.json")
    if not os.path.exists(final_path):
        return False, 0
    try:
        with open(final_path, encoding="utf-8") as handle:
            snapshot = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"cannot safely resume re-entry lineage from {final_path}"
        ) from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("pools"), list):
        raise RuntimeError(f"invalid persisted runner state in {final_path}")

    persisted_by_pool = {}
    for persisted in snapshot["pools"]:
        if not isinstance(persisted, dict) or not persisted.get("pool"):
            raise RuntimeError(f"invalid persisted pool state in {final_path}")
        pool_key = str(persisted["pool"]).lower()
        if pool_key in persisted_by_pool:
            raise RuntimeError(f"duplicate persisted pool {pool_key} in {final_path}")
        persisted_by_pool[pool_key] = persisted

    seen_current = set()
    restored = False
    for pool_record in book:
        pool_key = str(pool_record.get("pool") or "").lower()
        if not pool_key or pool_key in seen_current:
            raise RuntimeError("current runner book contains a missing or duplicate pool")
        seen_current.add(pool_key)
        persisted = persisted_by_pool.get(pool_key)
        if persisted is None:
            continue
        persisted_risk_state = str(
            (persisted.get("exit_policy_context") or {}).get("state") or ""
        ).upper()
        if persisted.get("exited") or persisted_risk_state in {
            RiskState.EXITING.value,
            RiskState.COOLDOWN.value,
        }:
            raise RuntimeError(
                "legacy final_state contains a non-active position but no "
                "durable full-state checkpoint; refusing to create a fresh "
                f"ACTIVE position for pool {pool_key}"
            )
        try:
            identity = persisted["position_id"]
            root_identity, identity_sequence = _reentry_lineage(identity)
            stored_root = persisted.get("position_root_id", root_identity)
            stored_sequence = persisted.get(
                "reentry_sequence", identity_sequence
            )
            if (
                isinstance(stored_sequence, bool)
                or not isinstance(stored_sequence, int)
                or stored_sequence < 0
                or str(stored_root) != root_identity
                or stored_sequence != identity_sequence
            ):
                raise ValueError("persisted re-entry lineage fields disagree")
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"invalid persisted re-entry lineage for pool {pool_key}"
            ) from exc

        pool_record["position_id"] = identity
        pool_record["_position_root_id"] = root_identity
        pool_record["_reentry_sequence"] = identity_sequence
        if persisted.get("reentry_of"):
            pool_record["reentry_of"] = str(persisted["reentry_of"])
        cooldown = (
            pool_record.get("state", {})
            .get("exit_policy_context", {})
            .get("cooldown")
        )
        if isinstance(cooldown, dict):
            cooldown["position_identity"] = identity
        restored = True
    final_tick = snapshot.get("final_tick", 0)
    if isinstance(final_tick, bool) or not isinstance(final_tick, int) or final_tick < 0:
        raise RuntimeError(f"invalid final_tick in {final_path}")
    return restored, final_tick


def _checkpoint_state_payload(state):
    payload = dict(state)
    payload["entry_baseline"] = asdict(state["entry_baseline"])
    payload["lp_principal_state"] = asdict(state["lp_principal_state"])
    return payload


def _checkpoint_pool_payload(pool_record):
    return {
        key: value
        for key, value in pool_record.items()
        if key != "state" and not key.startswith("_durable_")
    } | {"state": _checkpoint_state_payload(pool_record["state"])}


def _write_runner_checkpoint(run_dir, book, *, next_tick, last_ts):
    """Atomically persist the complete paper book and monotonic gate cursor."""
    if isinstance(next_tick, bool) or not isinstance(next_tick, int) or next_tick < 0:
        raise ValueError("checkpoint next_tick must be a non-negative integer")
    if last_ts.tzinfo is None or last_ts.utcoffset() is None:
        raise ValueError("checkpoint last_ts must be timezone-aware")
    payload = {
        "checkpoint_schema_version": RUNNER_CHECKPOINT_SCHEMA_VERSION,
        "next_tick": next_tick,
        "last_ts": last_ts.astimezone(timezone.utc).isoformat(),
        "pools": [_checkpoint_pool_payload(pool) for pool in book],
    }
    checkpoint_path = os.path.join(run_dir, _RUNNER_CHECKPOINT_FILE)
    temporary_path = f"{checkpoint_path}.{os.getpid()}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, checkpoint_path)
        directory_fd = os.open(run_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _restore_runner_checkpoint(run_dir, allocs, *, chain):
    """Load a complete durable book, or return None for a genuinely fresh run."""
    checkpoint_path = os.path.join(run_dir, _RUNNER_CHECKPOINT_FILE)
    if not os.path.exists(checkpoint_path):
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if (
            not isinstance(payload, dict)
            or payload.get("checkpoint_schema_version")
            != RUNNER_CHECKPOINT_SCHEMA_VERSION
            or not isinstance(payload.get("pools"), list)
            or not payload["pools"]
        ):
            raise ValueError("invalid checkpoint envelope")
        next_tick = payload["next_tick"]
        if isinstance(next_tick, bool) or not isinstance(next_tick, int) or next_tick < 0:
            raise ValueError("invalid checkpoint next_tick")
        last_ts = datetime.fromisoformat(str(payload["last_ts"]).replace("Z", "+00:00"))
        if last_ts.tzinfo is None or last_ts.utcoffset() is None:
            raise ValueError("invalid checkpoint last_ts")

        allocation_pools = [
            str(allocation.get("pool") or "").lower() for allocation in allocs
        ]
        if (
            any(not pool for pool in allocation_pools)
            or len(set(allocation_pools)) != len(allocation_pools)
        ):
            raise ValueError("allocation contains missing or duplicate pools")

        book = []
        checkpoint_pools = []
        for raw_pool in payload["pools"]:
            if not isinstance(raw_pool, dict) or not isinstance(raw_pool.get("state"), dict):
                raise ValueError("invalid checkpoint pool")
            pool_record = dict(raw_pool)
            state = dict(pool_record["state"])
            state["entry_baseline"] = EntryBaseline(**state["entry_baseline"])
            state["lp_principal_state"] = V3PositionState(
                **state["lp_principal_state"]
            )
            pool_record["state"] = state
            pool_key = str(pool_record.get("pool") or "").lower()
            if not pool_key or pool_key in checkpoint_pools:
                raise ValueError("checkpoint contains missing or duplicate pools")
            checkpoint_pools.append(pool_key)
            if str(pool_record.get("chain") or chain).lower() != str(chain).lower():
                raise ValueError("checkpoint chain disagrees with requested chain")
            identity = _paper_position_identity(pool_record)
            root_identity, identity_sequence = _reentry_lineage(identity)
            stored_root = pool_record.get("_position_root_id", root_identity)
            stored_sequence = pool_record.get("_reentry_sequence", identity_sequence)
            if (
                isinstance(stored_sequence, bool)
                or not isinstance(stored_sequence, int)
                or str(stored_root) != root_identity
                or stored_sequence != identity_sequence
            ):
                raise ValueError("checkpoint re-entry lineage fields disagree")
            pool_record["_position_root_id"] = root_identity
            pool_record["_reentry_sequence"] = identity_sequence
            book.append(pool_record)
        if set(checkpoint_pools) != set(allocation_pools):
            raise ValueError("checkpoint pool set disagrees with allocation")
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"cannot safely resume runner checkpoint from {checkpoint_path}"
        ) from exc
    return book, next_tick, last_ts


def _refresh_reentry_evidence(book, allocation_path):
    """Refresh externally recomputed evidence without risking the main loop.

    The allocation JSON is the runner's existing read-only control input. An
    operator/scanner can atomically replace it between ticks. Any unreadable,
    malformed, missing, or duplicate pool record clears evidence fail-closed.
    """
    try:
        with open(allocation_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("allocation payload must be an object")
        allocations = payload.get("allocations")
        if not isinstance(allocations, list):
            raise ValueError("allocations must be a list")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        for pool_record in book:
            pool_record["reentry_evidence"] = None
        return False

    by_pool = {}
    duplicates = set()
    for allocation in allocations:
        if not isinstance(allocation, dict) or not allocation.get("pool"):
            continue
        key = str(allocation["pool"]).lower()
        if key in by_pool:
            duplicates.add(key)
        else:
            by_pool[key] = allocation
    for pool_record in book:
        key = str(pool_record.get("pool") or "").lower()
        allocation = None if key in duplicates else by_pool.get(key)
        evidence = allocation.get("reentry_evidence") if allocation else None
        pool_record["reentry_evidence"] = (
            dict(evidence) if isinstance(evidence, dict) else None
        )
    return True


def _decode_orca_whirlpool_account(account_result, *, decimals_a, decimals_b):
    """Validate and decode one Orca Whirlpool account, failing closed.

    Whirlpool ``sqrt_price`` is Q64.64 sqrt(raw token-B/token-A).  The
    human-price direction emitted here is therefore token B per token A:

      (sqrt_price_x64 / 2**64)**2 * 10**(decimals_a - decimals_b)

    Only the two immutable layout fields needed for a state observation are
    decoded. No API metadata, address guessing, transaction, or swap evidence
    is involved.
    """
    if not isinstance(account_result, dict):
        raise ValueError("Whirlpool account result is missing")
    value = account_result.get("value")
    if not isinstance(value, dict):
        raise ValueError("Whirlpool account value is missing")
    if value.get("owner") != ORCA_WHIRLPOOL_PROGRAM_ID:
        raise ValueError("Whirlpool account owner mismatch")
    if value.get("space") != ORCA_WHIRLPOOL_ACCOUNT_SIZE:
        raise ValueError("Whirlpool account space mismatch")

    encoded = value.get("data")
    if (
        not isinstance(encoded, list)
        or len(encoded) != 2
        or encoded[1] != "base64"
        or not isinstance(encoded[0], str)
    ):
        raise ValueError("Whirlpool account data must be base64")
    try:
        raw = base64.b64decode(encoded[0], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Whirlpool account base64 is malformed") from exc
    if len(raw) != ORCA_WHIRLPOOL_ACCOUNT_SIZE:
        raise ValueError("Whirlpool decoded account space mismatch")
    if raw[:8] != ORCA_WHIRLPOOL_DISCRIMINATOR:
        raise ValueError("Whirlpool account discriminator mismatch")

    # Anchor Whirlpool layout offsets (little-endian): discriminator 0..8,
    # config/bump/tick/fee fields 8..49, liquidity 49..65, sqrt-price 65..81.
    liquidity = int.from_bytes(raw[49:65], "little", signed=False)
    sqrt_price_x64 = int.from_bytes(raw[65:81], "little", signed=False)
    if liquidity <= 0:
        raise ValueError("Whirlpool liquidity must be positive")
    if sqrt_price_x64 <= 0:
        raise ValueError("Whirlpool sqrt_price must be positive")

    try:
        decimal_scale = 10.0 ** (int(decimals_a) - int(decimals_b))
        price = (sqrt_price_x64 / float(1 << 64)) ** 2 * decimal_scale
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("Whirlpool price must be finite and positive") from exc
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("Whirlpool price must be finite and positive")

    return {
        "owner": value["owner"],
        "space": value["space"],
        "sqrt_price_x64": sqrt_price_x64,
        "liquidity": liquidity,
        "price": price,
        "price_direction": "token_b_per_token_a",
        "decimals_a": int(decimals_a),
        "decimals_b": int(decimals_b),
    }


def _solana_whirlpool_observation(
    pool, *, decimals_a, decimals_b, rpc_call=None
):
    """Read one verified Whirlpool account-state observation via WP-01."""
    call = rpc_call or _rpc()
    result = call(
        "getAccountInfo",
        [pool, {"encoding": "base64", "commitment": "confirmed"}],
    )
    decoded = _decode_orca_whirlpool_account(
        result, decimals_a=decimals_a, decimals_b=decimals_b
    )
    context = result.get("context")
    slot = context.get("slot") if isinstance(context, dict) else None
    if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
        raise ValueError("Whirlpool account context slot is invalid")
    return {
        "block": slot,
        "price": decoded["price"],
        "liquidity": decoded["liquidity"],
        # Account state proves no swap volume. Keeping amount1 exactly zero
        # lets the common passive-position engine observe price/range without
        # manufacturing fee income.
        "amount1": 0,
        "observation_kind": "account_state",
        **decoded,
    }


def _require_solana_allocation_adapter(allocation):
    protocol = allocation.get("protocol")
    adapter = allocation.get("solana_adapter")
    if not protocol:
        raise ValueError("Solana allocation requires explicit protocol")
    if not adapter:
        raise ValueError("Solana allocation requires explicit solana_adapter")
    if protocol != ORCA_WHIRLPOOL_PROTOCOL:
        raise ValueError(f"unsupported Solana protocol {protocol!r}")
    if adapter != ORCA_WHIRLPOOL_ADAPTER:
        raise ValueError(f"unsupported Solana solana_adapter {adapter!r}")
    return protocol, adapter


def _init_book(allocs, *, entry_window_blocks, latest, chain="base"):
    """Tick 0: fetch a small recent window per pool to set the entry anchor."""
    book = []
    for a in allocs:
        pool = a["pool"]
        dec0, dec1 = int(a["dec0"]), int(a["dec1"])
        last_observation = None
        if chain == "solana":
            protocol, solana_adapter = _require_solana_allocation_adapter(a)
            last_observation = _solana_whirlpool_observation(
                pool, decimals_a=dec0, decimals_b=dec1
            )
            anchor = last_observation["price"]
        else:
            protocol = a.get("protocol", a.get("project", ""))
            solana_adapter = None
            from_b = max(0, latest - entry_window_blocks)
            swaps = fetch_pool_swaps(
                pool, from_b, latest, dec0, dec1, rpc_call=_rpc()
            )
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
            "protocol": protocol, "solana_adapter": solana_adapter,
            "chain": chain, "tier": a.get("tier", ""), "pool": pool,
            "reward_apr": float(a.get("reward_apr", 0.0)),
            "fee_apr_onchain": a.get("fee_apr_onchain"),
            "reward_price_usd": float(a.get("reward_token_price_usd", 1.0)),
            "position_id": a.get("position_id"),
            # A scanner/operator may replace this mapping between ticks.  It is
            # deliberately consumed after one successful re-entry so stale
            # economics can never authorize another automatic position.
            "reentry_evidence": a.get("reentry_evidence"),
            "run_entry_capital_usd": float(st["capital"]),
            "realized_pnl_carry_usd": 0.0,
            "last_price": anchor, "last_observation": last_observation,
            "state": st,
        })
        print(f"[init] {a['symbol']:14s} {a['tier']} cap={a['usd']:.0f} "
              f"anchor={anchor:.6g} range=±{a['range_pct']:.2f}% "
              f"exit_on_breach={exit_on_breach} pool={pool}")
        time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
    if not book:
        raise SystemExit("no pools initialized (no swaps found)")
    return book


def _fetch_position_observations(pool_record, latest):
    """Return common-engine observations and an honest swap count."""
    state = pool_record["state"]
    if pool_record.get("solana_adapter") == ORCA_WHIRLPOOL_ADAPTER:
        observation = _solana_whirlpool_observation(
            pool_record["pool"],
            decimals_a=state["dec0"],
            decimals_b=state["dec1"],
        )
        observation["account_context_slot"] = observation["block"]
        # The runner's monotonic cursor is the getSlot result. Account context
        # is retained separately in evidence rather than used to invent an
        # event ordering beyond the observed runner tick.
        observation["block"] = latest
        pool_record["last_observation"] = observation
        return [observation], 0
    swaps = fetch_pool_swaps(
        pool_record["pool"], state["last_block"] + 1, latest,
        state["dec0"], state["dec1"], rpc_call=_rpc(),
    )
    return swaps, len(swaps)


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


def _paper_position_identity(pool_record):
    """Return the identity GateStore will use for the current paper position."""
    explicit = pool_record.get("position_id")
    if explicit:
        return str(explicit)
    pool = pool_record.get("pool")
    if pool:
        return str(pool).lower()
    raise ValueError("paper position lacks position_id and pool")


def _cooldown_reason(state):
    """Classify cooldown conservatively; a hard veto always needs a human."""
    breaches = state.get("breaches") or []
    if breaches and breaches[-1].get("hard_risk_override") is True:
        return "risk"
    return "normal"


def _ensure_position_cooldown(pool_record, *, now):
    """Persist the policy cooldown clock once a paper exit is complete."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("cooldown start must be timezone-aware")
    state = pool_record["state"]
    ctx = state["exit_policy_context"]
    if ctx.get("state") != RiskState.COOLDOWN.value or not state.get("exited"):
        return None
    if ctx.get("cooldown") is not None:
        return ctx["cooldown"]

    reason = _cooldown_reason(state)
    requirement = cooldown_requirement(_policy_config(state), reason=reason)
    # RWA's time gate is a full short window/session change rather than a
    # duration. can_reenter still requires an aware boundary, so the start is
    # its earliest possible boundary and the extra gate remains mandatory.
    ends_at = now if requirement.duration is None else now + requirement.duration
    ctx["cooldown"] = {
        "started_at": now.astimezone(timezone.utc).isoformat(),
        "ends_at": ends_at.astimezone(timezone.utc).isoformat(),
        "reason": reason,
        "manual_release_required": requirement.manual_release_required,
        "requires_full_short_window_or_session_change": (
            requirement.requires_full_short_window_or_session_change
        ),
        "position_identity": _paper_position_identity(pool_record),
    }
    return ctx["cooldown"]


def _strict_bool(mapping, key):
    value = mapping.get(key)
    return value if isinstance(value, bool) else None


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _reentry_gate_results(evidence):
    """Re-evaluate the WP-04 gates from explicit, current evidence.

    Raw economic inputs are preferred. Explicit boolean results are accepted
    for an upstream WP-04 adapter, but truthy strings and partial mappings are
    never treated as proof.
    """
    if not isinstance(evidence, dict):
        return False, False
    wp04 = evidence.get("wp04")
    values = wp04 if isinstance(wp04, dict) else evidence

    cover_key = "netcover" if "netcover" in values else "netcover_ratio"
    cover = _finite_number(values.get(cover_key))
    if cover is not None:
        netcover_passed = cover >= NETCOVER_SHADOW
    else:
        netcover_passed = _strict_bool(values, "netcover_gate_passed") is True

    expected = _finite_number(values.get("expected_net_profit_h"))
    round_trip = _finite_number(
        values.get("round_trip_cost_usd", values.get("round_trip_cost"))
    )
    if expected is not None and round_trip is not None:
        try:
            absolute_passed = absolute_profit_gate(expected, round_trip).allowed
        except ValueError:
            absolute_passed = False
    else:
        absolute_result = values.get("absolute_profit_gate")
        if isinstance(absolute_result, dict):
            absolute_passed = _strict_bool(absolute_result, "allowed") is True
        else:
            absolute_passed = (
                _strict_bool(values, "absolute_profit_gate_passed") is True
            )
    return netcover_passed, absolute_passed


def _reentry_evidence_is_current(
    evidence, *, cooldown, position_identity, now
):
    """Bind re-entry proof to this position and the completed cooldown."""
    if not isinstance(evidence, dict):
        return False
    if str(evidence.get("position_identity") or "") != str(position_identity):
        return False
    try:
        as_of = datetime.fromisoformat(
            str(evidence["as_of"]).replace("Z", "+00:00")
        )
        ends_at = datetime.fromisoformat(
            str(cooldown["ends_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return False
    if (
        as_of.tzinfo is None
        or as_of.utcoffset() is None
        or ends_at.tzinfo is None
        or ends_at.utcoffset() is None
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        return False
    age = (now - as_of).total_seconds()
    return (
        ends_at <= as_of <= now
        and 0.0 <= age <= REENTRY_EVIDENCE_MAX_AGE_SECONDS
    )


def _maybe_reenter_position(pool_record, *, now, latest_block):
    """Replace a completed cooldown position only when every gate is proven."""
    state = pool_record["state"]
    ctx = state["exit_policy_context"]
    if ctx.get("state") != RiskState.COOLDOWN.value or not state.get("exited"):
        return False
    cooldown = _ensure_position_cooldown(pool_record, now=now)
    if not isinstance(cooldown, dict):
        return False

    old_identity = _paper_position_identity(pool_record)
    # Derive the root and at least the current sequence from the persisted
    # identity.  This prevents a runner restart (which loses private in-memory
    # keys) from resetting the anti-churn allowance back to zero.
    try:
        root_identity, identity_sequence = _reentry_lineage(old_identity)
    except ValueError:
        pool_record["reentry_rejection"] = {
            "reason": "INVALID_REENTRY_SEQUENCE_FAIL_CLOSED",
            "root_identity": None,
            "observed_identity": old_identity,
            "observed_sequence": pool_record.get("_reentry_sequence"),
            "limit": MAX_REENTRIES_PER_ROOT,
        }
        return False
    try:
        private_sequence = int(
            pool_record.get("_reentry_sequence", identity_sequence)
        )
    except (TypeError, ValueError):
        private_sequence = -1
    if private_sequence < 0:
        pool_record["reentry_rejection"] = {
            "reason": "INVALID_REENTRY_SEQUENCE_FAIL_CLOSED",
            "root_identity": root_identity,
            "observed_sequence": pool_record.get("_reentry_sequence"),
            "limit": MAX_REENTRIES_PER_ROOT,
        }
        return False
    prior_reentries = max(private_sequence, identity_sequence)
    if prior_reentries >= MAX_REENTRIES_PER_ROOT:
        pool_record["reentry_rejection"] = {
            "reason": "MAX_REENTRIES_PER_ROOT_REACHED",
            "root_identity": root_identity,
            "observed_sequence": prior_reentries,
            "limit": MAX_REENTRIES_PER_ROOT,
        }
        return False

    evidence = pool_record.get("reentry_evidence")
    if not _reentry_evidence_is_current(
        evidence,
        cooldown=cooldown,
        position_identity=old_identity,
        now=now,
    ):
        return False
    regime_changed = _strict_bool(evidence, "regime_changed")
    if regime_changed is None:
        return False
    netcover_passed, absolute_passed = _reentry_gate_results(evidence)
    requires_window = bool(
        cooldown.get("requires_full_short_window_or_session_change")
    )
    if requires_window:
        full_window = _strict_bool(
            evidence, "full_short_window_elapsed_or_session_changed"
        )
        if full_window is None:
            return False
    else:
        full_window = True

    # Runner automation is intentionally stricter than can_reenter's generic
    # API: any cooldown classified for manual release is never auto-released.
    if cooldown.get("manual_release_required") is not False:
        return False
    try:
        ends_at = datetime.fromisoformat(
            str(cooldown["ends_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return False
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        return False
    if not can_reenter(
        now=now,
        cooldown_ends_at=ends_at,
        regime_changed=regime_changed,
        netcover_gate_passed=netcover_passed,
        absolute_profit_gate_passed=absolute_passed,
        full_short_window_elapsed_or_session_changed=full_window,
        manual_release_required=False,
        manual_released=False,
    ):
        return False

    last_price = _finite_number(pool_record.get("last_price"))
    if last_price is None or last_price <= 0.0:
        return False
    old_mark = mark_position(state, last_price)
    old_attribution = attribution_ledger(state, old_mark)
    capital = _finite_number(
        float(state["capital"]) + float(old_attribution["pnl_vs_usdc"])
    )
    if capital is None or capital <= 0.0:
        return False

    pool_record["_position_root_id"] = root_identity
    sequence = prior_reentries + 1
    new_identity = f"{root_identity}:reentry:{sequence}"
    config = _policy_config(state)
    costs = state.get("attribution_costs", {})
    new_state = init_state(
        capital=capital,
        anchor=last_price,
        range_pct=state["range_pct"],
        fee_tier=state["fee_tier"],
        dec0=state["dec0"],
        dec1=state["dec1"],
        last_block=latest_block,
        exit_on_breach=ctx.get("legacy_operator_confirmed", False),
        exit_cost_bps=state.get("exit_cost_bps"),
        exit_policy_enabled=ctx.get("enabled", False),
        profile=config.profile,
        risky_token_side=config.risky_token_side,
        stable_token_side=config.stable_token_side,
        risky_inventory_target=config.risky_inventory_target,
        max_exit_slippage_bps=config.max_slippage_bps,
        rpc_health=ctx.get("rpc_health", "UNKNOWN"),
        major_cooldown_minutes=config.major_cooldown_minutes,
        risk_signals=ctx.get("risk_signals"),
        reward_token_price_usd=pool_record.get("reward_price_usd", 1.0),
        gas_cost=costs.get("gas_cost", 0.0),
        priority_fee=costs.get("priority_fee", 0.0),
        lvr_estimate=costs.get("lvr_estimate", 0.0),
        exit_latency_loss=costs.get("exit_latency_loss", 0.0),
        switching_cost=costs.get("switching_cost", 0.0),
        entry_swap_cost=state["entry_baseline"].entry_swap_cost,
    )
    new_state["tier"] = state.get("tier", str(pool_record.get("tier", "")).upper())
    new_state["reentry_of"] = old_identity
    new_state["reentry_evidence"] = dict(evidence)
    pool_record.setdefault("run_entry_capital_usd", float(state["capital"]))
    pool_record["realized_pnl_carry_usd"] = float(
        pool_record.get("realized_pnl_carry_usd", 0.0)
    ) + float(old_attribution["pnl_vs_usdc"])
    pool_record["state"] = new_state
    pool_record["position_id"] = new_identity
    pool_record["reentry_of"] = old_identity
    pool_record["_reentry_sequence"] = sequence
    pool_record["last_reentry_evidence"] = dict(evidence)
    pool_record["reentry_evidence"] = None
    pool_record.pop("reentry_rejection", None)
    durable_checkpoint = pool_record.get("_durable_checkpoint_after_reentry")
    if callable(durable_checkpoint):
        # The anti-churn sequence must survive SIGKILL/power loss immediately;
        # waiting for the outer loop or graceful-finally would reopen W1.
        durable_checkpoint()
    return True


def _tick(book, *, last_ts, alerter=None):
    latest = _latest_block()
    now = _now_utc()
    elapsed = (now - last_ts).total_seconds()
    by_pool = []
    portfolio_net = 0.0
    portfolio_nav = 0.0
    for p in book:
        st = p["state"]
        cooldown_n_swaps = 0
        cooldown_observation_fetched = False
        reentered_this_tick = False
        if (
            st.get("exited")
            and st["exit_policy_context"].get("state") == RiskState.COOLDOWN.value
        ):
            cooldown = _ensure_position_cooldown(p, now=now)
            if (
                isinstance(cooldown, dict)
                and cooldown.get("manual_release_required") is False
                and isinstance(p.get("reentry_evidence"), dict)
                and _reentry_evidence_is_current(
                    p["reentry_evidence"],
                    cooldown=cooldown,
                    position_identity=_paper_position_identity(p),
                    now=now,
                )
            ):
                # Refresh only the read-only market cursor needed by an actual
                # re-entry attempt. The exited state short-circuits accounting,
                # so no LP fee/reward can accrue during cooldown.
                observations, cooldown_n_swaps = _fetch_position_observations(
                    p, latest
                )
                update_position(st, observations, now_block=latest)
                if observations:
                    p["last_price"] = observations[-1]["price"]
                cooldown_observation_fetched = True
                time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
            reentered_this_tick = _maybe_reenter_position(
                p, now=now, latest_block=latest
            )
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
            n_swaps, new_breach = cooldown_n_swaps, False
        elif staged_inventory:
            # LP liquidity is gone, but risky withdrawn inventory remains. Keep
            # a read-only market mark and block all LP fee/reward accrual until
            # a later execution path proves risk-off complete (INV-EXIT-01).
            observations, n_swaps = _fetch_position_observations(p, latest)
            update_position(st, observations, now_block=latest)
            _ensure_position_cooldown(p, now=now)
            if observations:
                p["last_price"] = observations[-1]["price"]
            mk = mark_position(st, p["last_price"])
            pool_net = mk["net_quote"]
            new_breach = False
            time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
        else:
            if reentered_this_tick:
                observations, n_swaps = [], cooldown_n_swaps
            else:
                observations, n_swaps = _fetch_position_observations(p, latest)
            n_breach_before = len(st["breaches"])
            # book reward for elapsed BEFORE update, so a same-tick exit keeps it
            position_elapsed = 0.0 if reentered_this_tick else elapsed
            accrue_capital_time(st, position_elapsed)
            accrue_reward_ledger(
                st,
                accrue_reward(st["capital"], p["reward_apr"], position_elapsed),
                reward_token_price_usd=p.get("reward_price_usd", 1.0),
            )
            update_position(st, observations, now_block=latest)
            _ensure_position_cooldown(p, now=now)
            if observations:
                p["last_price"] = observations[-1]["price"]
            mk = mark_position(st, p["last_price"])
            # active mark excludes reward; exited mark includes it
            pool_net = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
            new_breach = len(st["breaches"]) > n_breach_before
            if not cooldown_observation_fetched:
                time.sleep(float(os.environ.get("CALL_PACE_SECS", "0.0")))
        _emit_runner_alerts(p, alerter)
        attribution = attribution_ledger(st, mk)
        position_pnl = float(attribution["pnl_vs_usdc"])
        pnl_carry = float(p.get("realized_pnl_carry_usd", 0.0))
        run_pnl = pnl_carry + position_pnl
        run_capital = float(p.get("run_entry_capital_usd", st["capital"]))
        portfolio_net += run_pnl
        portfolio_nav += run_capital + run_pnl
        pool_output = {
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
        }
        # Keep the attribution ledger position-local while exposing run-level
        # economics in the canonical fields consumed by GateStore §12.0.
        pool_output.update({
            "position_pnl_vs_usdc": position_pnl,
            "run_entry_capital_usd": run_capital,
            "realized_pnl_carry_usd": pnl_carry,
            "pnl_vs_usdc": run_pnl,
            "net_usd": round(run_pnl, 2),
            "net_pct": round(run_pnl / run_capital * 100.0, 4)
            if run_capital
            else 0.0,
        })
        if p.get("position_id"):
            pool_output["position_id"] = str(p["position_id"])
        if p.get("reentry_of"):
            pool_output["reentry_of"] = str(p["reentry_of"])
        if p.get("reentry_rejection"):
            pool_output["reentry_rejection"] = dict(p["reentry_rejection"])
        if p.get("solana_adapter"):
            observation = p.get("last_observation") or {}
            pool_output.update({
                "protocol": p["protocol"],
                "solana_adapter": p["solana_adapter"],
                "observation_kind": "account_state",
                "account_state": {
                    "slot": observation.get(
                        "account_context_slot", observation.get("block")
                    ),
                    "owner": observation.get("owner"),
                    "space": observation.get("space"),
                    "sqrt_price_x64": observation.get("sqrt_price_x64"),
                    "liquidity": observation.get("liquidity"),
                    "price": observation.get("price"),
                    "price_direction": observation.get("price_direction"),
                },
            })
        by_pool.append(pool_output)
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

    restored_checkpoint = _restore_runner_checkpoint(run_dir, allocs, chain=chain)
    fresh_run = restored_checkpoint is None
    if restored_checkpoint is not None:
        book, tick, last_ts = restored_checkpoint
        print(f"[resume] restored full runner checkpoint from {run_dir} next_tick={tick}")
    else:
        latest = _latest_block()
        book = _init_book(
            allocs, entry_window_blocks=entry_window_blocks, latest=latest,
            chain=chain,
        )
        restored_lineage, tick = _restore_reentry_state_from_final(run_dir, book)
        if restored_lineage:
            print(f"[resume] restored legacy re-entry lineage from {run_dir}")
        last_ts = _now_utc()
    if fresh_run:
        # snapshot the resolved book for reproducibility
        with open(os.path.join(run_dir, "book_init.json"), "w") as f:
            json.dump([{k: v for k, v in p.items() if k != "state"} | {
                "anchor": p["state"]["anchor"], "capital": p["state"]["capital"],
                "range_pct": p["state"]["range_pct"], "fee_tier": p["state"]["fee_tier"],
            } for p in book], f, indent=2)

    last_hour = -1
    stop = {"flag": False}
    checkpoint_runtime = {"next_tick": tick, "last_ts": last_ts}

    def _durable_reentry_checkpoint():
        _write_runner_checkpoint(
            run_dir,
            book,
            next_tick=checkpoint_runtime["next_tick"],
            last_ts=checkpoint_runtime["last_ts"],
        )

    for pool_record in book:
        pool_record["_durable_checkpoint_after_reentry"] = (
            _durable_reentry_checkpoint
        )
    _durable_reentry_checkpoint()

    def _handle(signum, frame):  # graceful flush
        stop["flag"] = True
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    try:
        while not stop["flag"]:
            _refresh_reentry_evidence(book, allocation_path)
            rec, last_ts = _tick(book, last_ts=last_ts, alerter=selected_alerter)
            checkpoint_runtime["last_ts"] = last_ts
            # Captures all state transitions before non-durable reporting I/O.
            _durable_reentry_checkpoint()
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
            checkpoint_runtime["next_tick"] = tick
            _durable_reentry_checkpoint()
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
        checkpoint_runtime["next_tick"] = tick
        _durable_reentry_checkpoint()
        print(f"[done] {tick} ticks; state flushed to {run_dir}")


def _flush_state(run_dir, book, tick):
    snap = {"ledger_schema_version": LEDGER_SCHEMA_VERSION, "final_tick": tick, "pools": []}
    for p in book:
        st = p["state"]
        position_identity = _paper_position_identity(p)
        position_root_id, identity_sequence = _reentry_lineage(position_identity)
        mk = mark_position(st, p["last_price"])
        net_quote = mk["net_quote"] if st.get("exited") else mk["net_quote"] + st["reward_quote"]
        attribution = attribution_ledger(st, mk)
        position_pnl = float(attribution["pnl_vs_usdc"])
        pnl_carry = float(p.get("realized_pnl_carry_usd", 0.0))
        run_pnl = pnl_carry + position_pnl
        run_capital = float(p.get("run_entry_capital_usd", st["capital"]))
        pool_snapshot = {
            "symbol": p["symbol"], "tier": p["tier"], "pool": p["pool"],
            "position_id": position_identity,
            "position_root_id": position_root_id,
            "reentry_sequence": identity_sequence,
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
        }
        if p.get("reentry_of"):
            pool_snapshot["reentry_of"] = str(p["reentry_of"])
        if p.get("reentry_rejection"):
            pool_snapshot["reentry_rejection"] = dict(p["reentry_rejection"])
        pool_snapshot.update({
            "position_pnl_vs_usdc": position_pnl,
            "run_entry_capital_usd": run_capital,
            "realized_pnl_carry_usd": pnl_carry,
            "pnl_vs_usdc": run_pnl,
            "run_portfolio_nav_usd": run_capital + run_pnl,
        })
        if p.get("solana_adapter"):
            observation = p.get("last_observation") or {}
            pool_snapshot.update({
                "protocol": p["protocol"],
                "solana_adapter": p["solana_adapter"],
                "observation_kind": "account_state",
                "account_state": {
                    "slot": observation.get(
                        "account_context_slot", observation.get("block")
                    ),
                    "owner": observation.get("owner"),
                    "space": observation.get("space"),
                    "sqrt_price_x64": observation.get("sqrt_price_x64"),
                    "liquidity": observation.get("liquidity"),
                    "price": observation.get("price"),
                    "price_direction": observation.get("price_direction"),
                },
            })
        snap["pools"].append(pool_snapshot)
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
