#!/usr/bin/env python3
"""Fail-closed A/B/C stock-token LP policy and M1 sizing helpers.

This module contains no RPC or wallet code.  It turns explicit evidence into
an auditable decision and deliberately treats a missing field as a rejection.
Tier C replaces NetCover with seven stricter evidence gates; it does not bypass
the terminal conjunction.
"""
from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_netcover_engine_v1_readonly import (
    HARD_POSITION_TVL_SHARE,
    POSITION_TVL_SHARE,
    absolute_profit_gate,
)
from scripts.lp_stock_tier_c_shadow_v1_readonly import MIN_SAMPLES


STOCK_COARSE_TVL_MIN_USD = 20_000.0
DEPTH_SHARE = 0.02
C_MAX_EXIT_SLIPPAGE_BPS = 200.0
C_MIN_TOKEN_AGE_DAYS = 7.0
C_MIN_PERSISTENCE_HOURS = 48.0
C_SINGLE_HOLDER_MAX_PCT = 10.0
C_SINGLE_POSITION_MAX_USD = 5.0
C_TOTAL_EXPOSURE_MAX_USD = 20.0

TIER_CONFIG = {
    "A": {"budget_usd": 50.0, "position_max_usd": 50.0},
    "B": {"budget_usd": 30.0, "position_max_usd": 30.0},
    "C": {"budget_usd": C_TOTAL_EXPOSURE_MAX_USD,
          "position_max_usd": C_SINGLE_POSITION_MAX_USD},
}


def _finite(name: str, value: Any, *, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} requires finite numeric evidence") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"{name} requires finite numeric evidence")
    return number


def _strict_true(source: Mapping[str, Any], key: str) -> bool:
    return source.get(key) is True


@dataclass(frozen=True)
class PositionDecision:
    tier: str
    candidate: bool
    position_cap_usd: float
    tier_cap_usd: float
    tvl_share_cap_usd: float
    depth_share_cap_usd: float
    hard_tvl_share_ok: bool
    absolute_profit_pass: bool
    expected_net_profit_usd: float | None
    required_profit_usd: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_position(
    *,
    tier: str,
    tvl_usd: Any,
    exit_depth_usd: Any,
    expected_net_profit_usd: Any,
    round_trip_cost_usd: Any,
) -> PositionDecision:
    """Apply E5 sizing and the absolute-profit gate.

    ``exit_depth_usd`` must be an explicit measured depth.  A DefiLlama TVL or
    volume is not silently substituted for it.  Therefore unresolved pools get
    a defensible position of 0 U rather than a guessed size.
    """
    normalized = str(tier).upper()
    if normalized not in TIER_CONFIG:
        raise ValueError(f"unknown stock tier {tier!r}")
    tier_cap = TIER_CONFIG[normalized]["position_max_usd"]
    try:
        tvl = _finite("tvl_usd", tvl_usd, minimum=0.0)
        depth = _finite("exit_depth_usd", exit_depth_usd, minimum=0.0)
        profit = _finite("expected_net_profit_usd", expected_net_profit_usd)
        round_trip = _finite("round_trip_cost_usd", round_trip_cost_usd, minimum=0.0)
    except ValueError as exc:
        return PositionDecision(
            tier=normalized, candidate=False, position_cap_usd=0.0,
            tier_cap_usd=tier_cap, tvl_share_cap_usd=0.0,
            depth_share_cap_usd=0.0, hard_tvl_share_ok=False,
            absolute_profit_pass=False, expected_net_profit_usd=None,
            required_profit_usd=None, reason=f"FAIL_CLOSED:{exc}",
        )

    tvl_cap = tvl * POSITION_TVL_SHARE
    depth_cap = depth * DEPTH_SHARE
    cap = min(tier_cap, tvl_cap, depth_cap, tvl * HARD_POSITION_TVL_SHARE)
    hard_ok = tvl > 0.0 and cap / tvl <= HARD_POSITION_TVL_SHARE
    profit_gate = absolute_profit_gate(profit, round_trip)
    coarse_ok = tvl >= STOCK_COARSE_TVL_MIN_USD
    candidate = coarse_ok and cap > 0.0 and hard_ok and profit_gate.allowed
    if not coarse_ok:
        reason = "STOCK_COARSE_TVL_BELOW_20000"
    elif cap <= 0.0:
        reason = "NO_MEASURED_EXIT_DEPTH"
    elif not hard_ok:
        reason = "HARD_TVL_SHARE_EXCEEDED"
    else:
        reason = profit_gate.reason
    return PositionDecision(
        tier=normalized, candidate=candidate, position_cap_usd=cap,
        tier_cap_usd=tier_cap, tvl_share_cap_usd=tvl_cap,
        depth_share_cap_usd=depth_cap, hard_tvl_share_ok=hard_ok,
        absolute_profit_pass=profit_gate.allowed,
        expected_net_profit_usd=profit,
        required_profit_usd=profit_gate.required_profit_usd,
        reason=reason,
    )


def evaluate_ab_gate(tier: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve all existing gates; tier B additionally requires dual-vol proof."""
    normalized = str(tier).upper()
    if normalized not in {"A", "B"}:
        raise ValueError("evaluate_ab_gate only accepts A or B")
    gates = {
        "existing_terminal_conjunction": _strict_true(
            evidence, "existing_terminal_conjunction"),
        "instrument_normalized": _strict_true(evidence, "instrument_normalized"),
        "absolute_profit": _strict_true(evidence, "absolute_profit_pass"),
    }
    if normalized == "B":
        gates["dual_volatility_tightened"] = _strict_true(
            evidence, "dual_volatility_tightened_pass")
    passed = all(gates.values())
    return {
        "tier": normalized,
        "gates": gates,
        "passed": passed,
        "reason": "PASS" if passed else "FAIL_CLOSED:" + ",".join(
            name for name, ok in gates.items() if not ok),
    }


def evaluate_c_gate(
    evidence: Mapping[str, Any], *, current_c_exposure_usd: Any = 0.0,
) -> dict[str, Any]:
    """Evaluate the seven conjunctive Tier-C gates from TP-E E4.

    The 10% single-holder threshold is intentionally stricter than the legacy
    top-10-holder 40% locked-reject policy.  Pool vaults may only be excluded
    when their identities were independently verified.
    """
    failures: list[str] = []
    details: dict[str, Any] = {}

    exit_ok = evidence.get("exit_verdict") == "EXITABLE_CLEAN"
    details["1_exit_feasibility"] = exit_ok

    try:
        holder_pct = _finite("largest_holder_pct", evidence.get("largest_holder_pct"), minimum=0.0)
        holder_ok = (holder_pct <= C_SINGLE_HOLDER_MAX_PCT and
                     _strict_true(evidence, "pool_vaults_verified_and_excluded"))
    except ValueError:
        holder_pct, holder_ok = None, False
    details["2_holder_concentration"] = holder_ok

    sell_ok = (
        _strict_true(evidence, "sell_simulation_ok")
        and evidence.get("known_honeypot") is False
        and evidence.get("sell_tax_pct") == 0
        and evidence.get("simulation_broadcast_count") == 0
    )
    details["3_sell_simulation"] = sell_ok

    try:
        persistence_hours = _finite(
            "yield_persistence_hours", evidence.get("yield_persistence_hours"), minimum=0.0)
        persistence_samples = int(evidence.get("yield_persistence_samples"))
        persistence_ok = (
            persistence_hours >= C_MIN_PERSISTENCE_HOURS
            and persistence_samples >= MIN_SAMPLES
            and _strict_true(evidence, "yield_persistence_threshold_held")
        )
    except (ValueError, TypeError):
        persistence_hours, persistence_ok = None, False
    details["4_yield_persistence"] = persistence_ok

    try:
        age_days = _finite("counter_token_age_days", evidence.get("counter_token_age_days"), minimum=0.0)
        age_ok = age_days >= C_MIN_TOKEN_AGE_DAYS
    except ValueError:
        age_days, age_ok = None, False
    details["5_counter_token_age"] = age_ok

    try:
        position = _finite("position_usd", evidence.get("position_usd"), minimum=0.0)
    except ValueError:
        position = None
    try:
        depth = _finite("exit_depth_usd", evidence.get("exit_depth_usd"), minimum=0.0)
        slippage = _finite("exit_slippage_bps", evidence.get("exit_slippage_bps"), minimum=0.0)
        depth_ok = (position is not None and depth > 0
                    and position <= depth * DEPTH_SHARE
                    and slippage <= C_MAX_EXIT_SLIPPAGE_BPS)
    except ValueError:
        depth, slippage, depth_ok = None, None, False
    details["6_position_vs_depth"] = depth_ok

    try:
        exposure = _finite("current_c_exposure_usd", current_c_exposure_usd, minimum=0.0)
        budget_ok = (
            position is not None
            and position <= C_SINGLE_POSITION_MAX_USD
            and exposure + position <= C_TOTAL_EXPOSURE_MAX_USD
        )
    except ValueError:
        exposure, budget_ok = None, False
    details["7_budget_caps"] = budget_ok

    for name, ok in details.items():
        if not ok:
            failures.append(name)
    return {
        "tier": "C",
        "passed": not failures,
        "terminal_conjunction_complete": len(details) == 7,
        "gates": details,
        "failures": failures,
        "reason": "PASS" if not failures else "FAIL_CLOSED:" + ",".join(failures),
        "thresholds": {
            "single_holder_max_pct": C_SINGLE_HOLDER_MAX_PCT,
            "yield_persistence_min_hours": C_MIN_PERSISTENCE_HOURS,
            "counter_token_min_age_days": C_MIN_TOKEN_AGE_DAYS,
            "exit_slippage_max_bps": C_MAX_EXIT_SLIPPAGE_BPS,
            "position_depth_share_max": DEPTH_SHARE,
            "single_position_max_usd": C_SINGLE_POSITION_MAX_USD,
            "total_exposure_max_usd": C_TOTAL_EXPOSURE_MAX_USD,
        },
        "evidence": {
            "largest_holder_pct": holder_pct,
            "yield_persistence_hours": persistence_hours,
            "counter_token_age_days": age_days,
            "position_usd": position,
            "exit_depth_usd": depth,
            "exit_slippage_bps": slippage,
            "current_c_exposure_usd": exposure,
        },
    }


__all__ = [
    "C_SINGLE_POSITION_MAX_USD", "C_TOTAL_EXPOSURE_MAX_USD",
    "STOCK_COARSE_TVL_MIN_USD", "TIER_CONFIG", "evaluate_ab_gate",
    "evaluate_c_gate", "evaluate_position",
]
