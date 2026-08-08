#!/usr/bin/env python3
"""Pure, read-only defensive exit policy for Tactical LP Bot M0.

This module deliberately has no wallet, signer, transaction builder, network
client, or broadcast path.  It converts immutable observations into paper-only
decisions and action plans.  I/O belongs to the runner/replay adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


MIN_MAJOR_COOLDOWN_MINUTES = 15
MAX_MAJOR_COOLDOWN_MINUTES = 60
DEFAULT_MAJOR_COOLDOWN_MINUTES = 30


class RiskState(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    RISK_OFF_READY = "RISK_OFF_READY"
    EXITING = "EXITING"
    COOLDOWN = "COOLDOWN"


class ExitMode(str, Enum):
    REMOVE_ONLY = "REMOVE_ONLY"
    REMOVE_TO_TARGET = "REMOVE_TO_TARGET"
    REMOVE_TO_STABLE = "REMOVE_TO_STABLE"
    PANIC_EXIT = "PANIC_EXIT"


class BreachDirection(str, Enum):
    LOWER = "LOWER"
    UPPER = "UPPER"
    NONE = "NONE"


class RpcHealth(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    EXIT_ONLY = "EXIT_ONLY"
    KILLED = "KILLED"


@dataclass(frozen=True)
class ExitPolicyConfig:
    """Explicit asset orientation and hard limits for a single position."""

    profile: str
    risky_token_side: str
    stable_token_side: str
    risky_inventory_target: float
    max_slippage_bps: float
    major_cooldown_minutes: int = DEFAULT_MAJOR_COOLDOWN_MINUTES
    risky_inventory_buffer: float = 0.05

    def __post_init__(self) -> None:
        if not self.risky_token_side or not self.stable_token_side:
            raise ValueError("risky_token_side and stable_token_side must be explicit")
        if self.risky_token_side == self.stable_token_side:
            raise ValueError("risky and stable token sides must differ")
        if not 0.0 <= self.risky_inventory_target <= 1.0:
            raise ValueError("risky_inventory_target must be in [0, 1]")
        if self.max_slippage_bps < 0.0:
            raise ValueError("max_slippage_bps must be non-negative")
        if not MIN_MAJOR_COOLDOWN_MINUTES <= self.major_cooldown_minutes <= MAX_MAJOR_COOLDOWN_MINUTES:
            raise ValueError(
                "major_cooldown_minutes must be within the explicit 15-60 minute range"
            )
        if self.risky_inventory_buffer < 0.0:
            raise ValueError("risky_inventory_buffer must be non-negative")


@dataclass(frozen=True)
class BreachObservation:
    """The five mandatory breach-record fields from PRD v2.1 section 8.2."""

    breach_direction: BreachDirection
    post_remove_inventory_ratio: float
    post_remove_delta_usd: float
    expected_swap_cost: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.post_remove_inventory_ratio <= 1.0:
            raise ValueError("post_remove_inventory_ratio must be in [0, 1]")
        if self.expected_swap_cost < 0.0:
            raise ValueError("expected_swap_cost must be non-negative")


@dataclass(frozen=True)
class RiskSignals:
    """Inputs already computed elsewhere; no NetCover formula is duplicated here."""

    il_soft_breach: bool = False
    il_hard_breach: bool = False
    netcover_forward: Optional[float] = None
    netcover_persistently_below_one: bool = False
    range_distance_fraction: float = 0.0
    trend_worsening: bool = False
    trend_continuation: bool = False
    strong_trend_regime: bool = False
    rwa_basis_worsening: bool = False
    lower_breach: bool = False
    upper_breach: bool = False
    risky_inventory_hard_cap_breach: bool = False
    tvl_worsening: bool = False
    liquidity_worsening: bool = False
    risk_source_worsening: bool = False
    structural_risk_worsening: bool = False
    rug_risk: bool = False
    honeypot_risk: bool = False
    data_corruption: bool = False
    contract_risk: bool = False
    kill_switch: bool = False


@dataclass(frozen=True)
class ExitDecision:
    previous_state: RiskState
    next_state: RiskState
    should_execute: bool
    hard_risk_override: bool
    reason: str
    breach_direction: BreachDirection
    post_remove_inventory_ratio: float
    post_remove_delta_usd: float
    recommended_exit_mode: ExitMode
    expected_swap_cost: float


@dataclass(frozen=True)
class QuoteResult:
    succeeded: bool
    expected_slippage_bps: Optional[float] = None
    expected_swap_cost_usd: Optional[float] = None
    error: Optional[str] = None

    @classmethod
    def ok(cls, *, expected_slippage_bps: float, expected_swap_cost_usd: float) -> "QuoteResult":
        if expected_slippage_bps < 0.0 or expected_swap_cost_usd < 0.0:
            raise ValueError("quote values must be non-negative")
        return cls(True, float(expected_slippage_bps), float(expected_swap_cost_usd), None)

    @classmethod
    def failed(cls, error: str) -> "QuoteResult":
        return cls(False, None, None, str(error))


@dataclass(frozen=True)
class PaperActionPlan:
    mode: ExitMode
    paper_only: bool
    remove_simulated: bool
    swap_requested: bool
    quote_required: bool
    quote_succeeded: bool
    swap_allowed: bool
    substate: str
    alert: bool
    block_reason: Optional[str]
    paper_actions: tuple[str, ...]
    expected_slippage_bps: Optional[float]
    actual_slippage_bps: Optional[float]
    expected_swap_cost_usd: Optional[float]
    exit_latency_loss_usd: Optional[float]
    post_trade_risky_inventory_ratio: float
    risk_off_complete: bool
    next_state: RiskState


@dataclass(frozen=True)
class CooldownRequirement:
    duration: Optional[timedelta]
    requires_full_short_window_or_session_change: bool
    manual_release_required: bool


def classify_breach(*, price: float, lower_bound: float, upper_bound: float) -> BreachDirection:
    """Classify the crossed side; boundaries themselves remain in-range."""
    if lower_bound > upper_bound:
        raise ValueError("lower_bound must be <= upper_bound")
    if price < lower_bound:
        return BreachDirection.LOWER
    if price > upper_bound:
        return BreachDirection.UPPER
    return BreachDirection.NONE


def risk_off_complete(risky_inventory_ratio: float, target: float) -> bool:
    """INV-EXIT-01: liquidity removal alone is never the completion test."""
    if not 0.0 <= risky_inventory_ratio <= 1.0 or not 0.0 <= target <= 1.0:
        raise ValueError("inventory ratio and target must be in [0, 1]")
    return risky_inventory_ratio <= target


def _has_unconditional_veto(signals: RiskSignals) -> bool:
    return any(
        (
            signals.rug_risk,
            signals.honeypot_risk,
            signals.data_corruption,
            signals.contract_risk,
            signals.kill_switch,
        )
    )


def _has_hard_risk(signals: RiskSignals, observation: BreachObservation, config: ExitPolicyConfig) -> bool:
    hard_il_combo = signals.il_hard_breach and (
        (signals.netcover_forward is not None and signals.netcover_forward < 1.0)
        or signals.trend_worsening
        or signals.rwa_basis_worsening
    )
    risky_lower_hard = (
        observation.breach_direction is BreachDirection.LOWER
        and observation.post_remove_inventory_ratio > config.risky_inventory_target
        and (signals.risky_inventory_hard_cap_breach or signals.strong_trend_regime)
    )
    return any(
        (
            _has_unconditional_veto(signals),
            hard_il_combo,
            signals.netcover_persistently_below_one,
            risky_lower_hard,
            signals.strong_trend_regime,
        )
    )


def _has_soft_signal(signals: RiskSignals) -> bool:
    return any(
        (
            signals.il_soft_breach,
            signals.netcover_forward is not None and signals.netcover_forward < 1.5,
            signals.range_distance_fraction >= 0.8,
            signals.trend_worsening,
            signals.rwa_basis_worsening,
            signals.tvl_worsening,
            signals.liquidity_worsening,
            signals.risk_source_worsening,
            signals.structural_risk_worsening,
        )
    )


def _watch_combination(signals: RiskSignals, observation: BreachObservation, config: ExitPolicyConfig) -> bool:
    il_and_cover = (
        signals.il_soft_breach
        and signals.netcover_forward is not None
        and signals.netcover_forward < 1.0
    )
    lower_inventory_trend = (
        observation.breach_direction is BreachDirection.LOWER
        and signals.lower_breach
        and observation.post_remove_inventory_ratio > config.risky_inventory_target
        and signals.trend_continuation
    )
    structural = any(
        (
            signals.tvl_worsening,
            signals.liquidity_worsening,
            signals.risk_source_worsening,
            signals.structural_risk_worsening,
        )
    )
    return il_and_cover or lower_inventory_trend or structural


def _recommended_mode(
    signals: RiskSignals,
    observation: BreachObservation,
    config: ExitPolicyConfig,
) -> ExitMode:
    if _has_unconditional_veto(signals):
        return ExitMode.PANIC_EXIT
    ratio = observation.post_remove_inventory_ratio
    if observation.breach_direction is BreachDirection.UPPER and ratio <= config.risky_inventory_target:
        return ExitMode.REMOVE_ONLY
    if observation.breach_direction is BreachDirection.LOWER and ratio > config.risky_inventory_target:
        deterioration = any(
            (
                signals.trend_continuation,
                signals.trend_worsening,
                signals.il_soft_breach,
                signals.il_hard_breach,
                signals.netcover_forward is not None and signals.netcover_forward < 1.0,
                signals.strong_trend_regime,
            )
        )
        return ExitMode.REMOVE_TO_STABLE if deterioration else ExitMode.REMOVE_TO_TARGET
    if ratio > config.risky_inventory_target:
        return ExitMode.REMOVE_TO_TARGET
    return ExitMode.REMOVE_ONLY


def evaluate_risk(
    state: RiskState,
    signals: RiskSignals,
    observation: BreachObservation,
    config: ExitPolicyConfig,
    *,
    tier: str = "",
) -> ExitDecision:
    """Evaluate one state-machine step with hard risk above the soft Tier policy."""
    del tier  # Tier intentionally cannot bypass any hard gate.
    hard = _has_hard_risk(signals, observation, config)
    mode = _recommended_mode(signals, observation, config)
    next_state = state
    reason = "no_transition"

    if hard:
        next_state = RiskState.EXITING
        reason = "hard_risk_override"
    elif state is RiskState.HEALTHY and _has_soft_signal(signals):
        next_state = RiskState.WATCH
        reason = "soft_watch_signal"
    elif state is RiskState.WATCH and _watch_combination(signals, observation, config):
        next_state = RiskState.RISK_OFF_READY
        reason = "combined_risk_trigger"
    elif state is RiskState.RISK_OFF_READY:
        next_state = RiskState.EXITING
        reason = "exit_mode_selected"

    return ExitDecision(
        previous_state=state,
        next_state=next_state,
        should_execute=next_state is RiskState.EXITING,
        hard_risk_override=hard,
        reason=reason,
        breach_direction=observation.breach_direction,
        post_remove_inventory_ratio=observation.post_remove_inventory_ratio,
        post_remove_delta_usd=observation.post_remove_delta_usd,
        recommended_exit_mode=mode,
        expected_swap_cost=observation.expected_swap_cost,
    )


def transition_state(
    current: RiskState,
    requested: RiskState,
    *,
    hard_veto: bool = False,
    risk_off_complete: bool = False,
) -> RiskState:
    """Apply only legal transitions; incomplete EXITING remains fail-closed."""
    if current is requested:
        return current
    if hard_veto:
        if requested is not RiskState.EXITING:
            raise ValueError("hard veto may only transition directly to EXITING")
        return requested
    if current is RiskState.EXITING and requested is RiskState.COOLDOWN:
        return requested if risk_off_complete else current
    allowed = {
        RiskState.HEALTHY: RiskState.WATCH,
        RiskState.WATCH: RiskState.RISK_OFF_READY,
        RiskState.RISK_OFF_READY: RiskState.EXITING,
        RiskState.COOLDOWN: RiskState.HEALTHY,
    }
    if allowed.get(current) is not requested:
        raise ValueError(f"illegal risk-state transition: {current.value}->{requested.value}")
    return requested


_NORMAL_ACTIONS = frozenset(
    {"monitor", "open", "add", "remove", "collect", "swap_to_usdc", "rebalance", "approve"}
)
_DEGRADED_ACTIONS = frozenset({"monitor", "remove", "collect", "swap_to_usdc"})
_EXIT_ONLY_ACTIONS = frozenset({"remove", "collect", "swap_to_usdc"})


def action_allowed(rpc_health: RpcHealth, action: str) -> bool:
    """INV-RPC-01 allowlist; unknown actions fail closed."""
    allowlists = {
        RpcHealth.NORMAL: _NORMAL_ACTIONS,
        RpcHealth.DEGRADED: _DEGRADED_ACTIONS,
        RpcHealth.EXIT_ONLY: _EXIT_ONLY_ACTIONS,
        RpcHealth.KILLED: frozenset(),
    }
    return action in allowlists[rpc_health]


def build_paper_action_plan(
    *,
    mode: ExitMode,
    rpc_health: RpcHealth,
    quote: Optional[QuoteResult],
    config: ExitPolicyConfig,
    post_trade_risky_inventory_ratio: float,
    actual_slippage_bps: Optional[float] = None,
    exit_latency_loss_usd: Optional[float] = None,
) -> PaperActionPlan:
    """Create a paper-only plan.  No returned value can transmit a transaction."""
    complete = risk_off_complete(post_trade_risky_inventory_ratio, config.risky_inventory_target)
    swap_requested = mode is not ExitMode.REMOVE_ONLY
    quote_required = swap_requested
    quote_succeeded = bool(quote and quote.succeeded)
    expected_slippage = quote.expected_slippage_bps if quote_succeeded else None
    expected_cost = quote.expected_swap_cost_usd if quote_succeeded else None
    remove_permitted = action_allowed(rpc_health, "remove")

    swap_action = (
        "swap_to_usdc"
        if mode in (ExitMode.REMOVE_TO_STABLE, ExitMode.PANIC_EXIT)
        else "swap_to_target"
    )
    # EXIT_ONLY must never convert to an arbitrary target; KILLED permits no action.
    rpc_swap_permitted = (
        action_allowed(rpc_health, "swap_to_usdc")
        if swap_action == "swap_to_usdc"
        else rpc_health in (RpcHealth.NORMAL, RpcHealth.DEGRADED)
    )

    block_reason: Optional[str] = None
    if not remove_permitted:
        block_reason = "rpc_killed"
    elif swap_requested and not quote_succeeded:
        block_reason = "quote_failed"
    elif swap_requested and expected_slippage is not None and expected_slippage > config.max_slippage_bps:
        block_reason = "slippage_limit"
    elif swap_requested and not rpc_swap_permitted:
        block_reason = "rpc_action_blocked"

    swap_allowed = swap_requested and block_reason is None
    if not swap_requested and remove_permitted:
        substate = "remove_only"
        actions = ("simulate_remove",)
    elif swap_allowed:
        substate = "paper_swap_ready"
        target = "simulate_swap_to_stable" if swap_action == "swap_to_usdc" else "simulate_swap_to_target"
        actions = ("simulate_remove", target)
    else:
        substate = "staged/limit_exit"
        actions = ("simulate_remove",) if remove_permitted else ()

    next_state = RiskState.COOLDOWN if complete else RiskState.EXITING
    return PaperActionPlan(
        mode=mode,
        paper_only=True,
        remove_simulated=remove_permitted,
        swap_requested=swap_requested,
        quote_required=quote_required,
        quote_succeeded=quote_succeeded,
        swap_allowed=swap_allowed,
        substate=substate,
        alert=block_reason is not None,
        block_reason=block_reason,
        paper_actions=actions,
        expected_slippage_bps=expected_slippage,
        actual_slippage_bps=actual_slippage_bps,
        expected_swap_cost_usd=expected_cost,
        exit_latency_loss_usd=exit_latency_loss_usd,
        post_trade_risky_inventory_ratio=post_trade_risky_inventory_ratio,
        risk_off_complete=complete,
        next_state=next_state,
    )


def cooldown_requirement(config: ExitPolicyConfig, *, reason: str) -> CooldownRequirement:
    """Return profile-specific no-churn requirements without starting a timer."""
    risk_reason = reason.lower() in {"risk", "rug", "honeypot", "contract", "kill"}
    if risk_reason:
        return CooldownRequirement(
            duration=timedelta(hours=24),
            requires_full_short_window_or_session_change=False,
            manual_release_required=True,
        )
    if config.profile.upper().startswith("RWA"):
        return CooldownRequirement(
            duration=None,
            requires_full_short_window_or_session_change=True,
            manual_release_required=False,
        )
    return CooldownRequirement(
        duration=timedelta(minutes=config.major_cooldown_minutes),
        requires_full_short_window_or_session_change=False,
        manual_release_required=False,
    )


def can_reenter(
    *,
    now: datetime,
    cooldown_ends_at: datetime,
    regime_changed: bool,
    netcover_gate_passed: bool,
    absolute_profit_gate_passed: bool,
    full_short_window_elapsed_or_session_changed: bool = True,
    manual_release_required: bool = False,
    manual_released: bool = False,
) -> bool:
    """WP-04-compatible boolean gates; NetCover math intentionally stays external."""
    if now.tzinfo is None or cooldown_ends_at.tzinfo is None:
        raise ValueError("now and cooldown_ends_at must be timezone-aware")
    return all(
        (
            now >= cooldown_ends_at,
            regime_changed,
            netcover_gate_passed,
            absolute_profit_gate_passed,
            full_short_window_elapsed_or_session_changed,
            not manual_release_required or manual_released,
        )
    )


__all__ = [
    "MAX_MAJOR_COOLDOWN_MINUTES",
    "MIN_MAJOR_COOLDOWN_MINUTES",
    "BreachDirection",
    "BreachObservation",
    "CooldownRequirement",
    "ExitDecision",
    "ExitMode",
    "ExitPolicyConfig",
    "PaperActionPlan",
    "QuoteResult",
    "RiskSignals",
    "RiskState",
    "RpcHealth",
    "action_allowed",
    "build_paper_action_plan",
    "can_reenter",
    "classify_breach",
    "cooldown_requirement",
    "evaluate_risk",
    "risk_off_complete",
    "transition_state",
]
