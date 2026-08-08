#!/usr/bin/env python3
"""Full-cost opportunity economics for M0 shadow LP decisions.

This module is pure and read-only.  It deliberately keeps ``GrossFeeCover`` as
a diagnostic while ``NetCover`` and the absolute-profit check are the entry
gates.  No wallet, signing, transaction, approval, or broadcast capability is
present.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


# INV-GATE-01: PRD v2.1 initial thresholds.  They may not be relaxed to create
# more opportunities; a future change requires an evidenced Shadow calibration.
NETCOVER_SHADOW = 1.0
NETCOVER_TINY_LIVE = 1.5
SAFETY_MULTIPLE = 5.0
MIN_PROFIT_USD = 1.0

# INV-TVLSHARE-01 runtime constants.
POSITION_TVL_SHARE = 0.0005
ACTIVE_SHARE_LIMIT = 0.02
HARD_POSITION_TVL_SHARE = 0.001

REWARD_HAIRCUTS = {
    "stablecoin": 0.90,
    "major": 0.75,
    "protocol": 0.50,
    "new_token": 0.25,
    "points": 0.0,
}


def _amount(name: str, value: Any, *, positive: bool = False) -> float:
    """Validate an economic amount, failing closed on invalid model inputs."""
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        op = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be finite and {op}")
    return result


def _haircut_value(haircuts: float | Mapping[str, Any]) -> float:
    if isinstance(haircuts, Mapping):
        category = str(haircuts.get("category") or "")
        if not category or category not in haircuts:
            raise ValueError("haircut mapping requires category and its numeric value")
        value = _amount("reward_haircut", haircuts[category])
    else:
        value = _amount("reward_haircut", haircuts)
    if value > 1.0:
        raise ValueError("reward_haircut must be in [0, 1]")
    return value


def adjusted_income_ev(
    fee_ev: float,
    reward_ev: float,
    haircuts: float | Mapping[str, Any],
) -> float:
    """Conservative fee EV plus reward EV after its explicit haircut."""
    fee = _amount("fee_ev", fee_ev)
    reward = _amount("reward_ev", reward_ev)
    return fee + reward * _haircut_value(haircuts)


def expected_risk_cost(
    il: float,
    lvr: float,
    entry_cost: float,
    exit_cost: float,
    gas: float,
    slippage: float,
    reward_conv: float,
    exit_latency: float,
) -> float:
    """Sum every PRD v2.1 risk/cost component in one consistent currency."""
    components = {
        "il": il,
        "lvr": lvr,
        "entry_cost": entry_cost,
        "exit_cost": exit_cost,
        "gas": gas,
        "slippage": slippage,
        "reward_conv": reward_conv,
        "exit_latency": exit_latency,
    }
    return sum(_amount(name, value) for name, value in components.items())


def gross_fee_cover(conservative_fee_ev: float, expected_il: float) -> float:
    """Diagnostic only; never use this function's result as an entry gate."""
    fee = _amount("conservative_fee_ev", conservative_fee_ev)
    il = _amount("expected_il", expected_il)
    if il == 0:
        return math.inf if fee > 0 else 0.0
    return fee / il


def netcover(income: float, cost: float) -> float:
    income_value = _amount("adjusted_income_ev", income)
    cost_value = _amount("expected_risk_cost", cost)
    if cost_value == 0:
        return math.inf if income_value > 0 else 0.0
    return income_value / cost_value


@dataclass(frozen=True)
class NetCoverEstimate:
    conservative_fee_ev: float
    haircut_reward_ev: float
    adjusted_income_ev: float
    expected_il: float
    expected_lvr_model: float
    entry_cost: float
    exit_cost: float
    gas: float
    slippage: float
    reward_conversion_cost: float
    exit_latency_loss_model: float
    expected_risk_cost: float
    gross_fee_cover_diagnostic: float
    netcover: float
    shadow_candidate: bool
    tiny_live_candidate: bool
    semantics: Mapping[str, str] = field(default_factory=lambda: {
        "gross_fee_cover_diagnostic": "diagnostic_only_not_an_entry_gate",
        "expected_lvr_model": "model_estimate: expected_il multiplied by configured coefficient",
        "exit_latency_loss_model": "model_estimate: free-RPC detect+build+submit+confirm latency loss",
    })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_netcover(
    *,
    fee_ev: float,
    reward_ev: float,
    reward_haircut: float | Mapping[str, Any],
    expected_il: float,
    lvr_coefficient: float,
    entry_cost: float,
    exit_cost: float,
    gas: float,
    slippage: float,
    reward_conversion_cost: float,
    exit_latency_loss: float,
) -> NetCoverEstimate:
    """Build an auditable NetCover record, including model-estimate semantics."""
    fee = _amount("fee_ev", fee_ev)
    reward = _amount("reward_ev", reward_ev)
    haircut = _haircut_value(reward_haircut)
    il = _amount("expected_il", expected_il)
    lvr_coeff = _amount("lvr_coefficient", lvr_coefficient)
    lvr = il * lvr_coeff
    income = fee + reward * haircut
    risk = expected_risk_cost(
        il, lvr, entry_cost, exit_cost, gas, slippage,
        reward_conversion_cost, exit_latency_loss,
    )
    cover = netcover(income, risk)
    return NetCoverEstimate(
        conservative_fee_ev=fee,
        haircut_reward_ev=reward * haircut,
        adjusted_income_ev=income,
        expected_il=il,
        expected_lvr_model=lvr,
        entry_cost=_amount("entry_cost", entry_cost),
        exit_cost=_amount("exit_cost", exit_cost),
        gas=_amount("gas", gas),
        slippage=_amount("slippage", slippage),
        reward_conversion_cost=_amount("reward_conversion_cost", reward_conversion_cost),
        exit_latency_loss_model=_amount("exit_latency_loss", exit_latency_loss),
        expected_risk_cost=risk,
        gross_fee_cover_diagnostic=gross_fee_cover(fee, il),
        netcover=cover,
        shadow_candidate=cover >= NETCOVER_SHADOW,
        tiny_live_candidate=cover >= NETCOVER_TINY_LIVE,
    )


@dataclass(frozen=True)
class AbsoluteProfitDecision:
    allowed: bool
    expected_net_profit_usd: float
    round_trip_cost_usd: float
    required_profit_usd: float
    reason: str


def absolute_profit_gate(
    expected_net_profit_h: float,
    round_trip_cost: float,
    *,
    min_profit_usd: float = MIN_PROFIT_USD,
    safety_multiple: float = SAFETY_MULTIPLE,
) -> AbsoluteProfitDecision:
    """INV-COST-01: enforce absolute economics regardless of displayed APR."""
    profit = _amount("expected_net_profit_h", expected_net_profit_h)
    round_trip = _amount("round_trip_cost", round_trip_cost)
    minimum = _amount("min_profit_usd", min_profit_usd)
    multiple = _amount("safety_multiple", safety_multiple, positive=True)
    required = max(minimum, multiple * round_trip)
    allowed = profit >= required
    return AbsoluteProfitDecision(
        allowed=allowed,
        expected_net_profit_usd=profit,
        round_trip_cost_usd=round_trip,
        required_profit_usd=required,
        reason="PASS" if allowed else "INV-COST-01_EXPECTED_NET_PROFIT_TOO_LOW",
    )


def position_cap_usd(
    tier_configured_max: float,
    pool_tvl: float,
    active_liquidity_notional: float,
    *,
    active_share_limit: float = ACTIVE_SHARE_LIMIT,
) -> float:
    """INV-TVLSHARE-01 runtime cap; never substitute a static sizing table."""
    tier_cap = _amount("tier_configured_max", tier_configured_max, positive=True)
    tvl = _amount("pool_tvl", pool_tvl, positive=True)
    active = _amount("active_liquidity_notional", active_liquidity_notional, positive=True)
    active_share = _amount("active_share_limit", active_share_limit, positive=True)
    if active_share > 1.0:
        raise ValueError("active_share_limit must be <= 1")
    # The 0.05% ordinary term is stricter than the separate 0.10% hard ceiling.
    return min(tier_cap, tvl * POSITION_TVL_SHARE, active * active_share,
               tvl * HARD_POSITION_TVL_SHARE)


_GATE_INPUT_KEYS = (
    "fee_ev_usd", "reward_ev_usd", "il_ev_usd", "entry_cost_usd",
    "exit_cost_usd", "gas_usd", "slippage_usd",
    "reward_conversion_cost_usd", "exit_latency_loss_usd",
)


def apply_netcover_gate(
    records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    reward_haircut: float | Mapping[str, Any] = REWARD_HAIRCUTS["protocol"],
    lvr_coefficient: float = 0.5,
) -> list[dict[str, Any]]:
    """Attach a fail-closed full-cost Shadow gate to scanner-style records.

    All nine horizon-dollar inputs in ``_GATE_INPUT_KEYS`` must be explicit.
    This avoids silently treating missing gas/slippage/latency as zero.  LVR is
    intentionally the PRD's initial model estimate (IL × configured coefficient),
    not a duplicated IL formula.
    """
    output: list[dict[str, Any]] = []
    for source in records:
        rec = dict(source)
        missing = [key for key in _GATE_INPUT_KEYS if rec.get(key) is None]
        if missing:
            rec.update({
                "risk_usd": None,
                "expected_net_yield_usd": None,
                "expected_net_yield_pct": None,
                "netcover_ratio": None,
                "netcover": None,
                "netcover_pass": False,
                "rejection_reason": "NETCOVER_INPUT_MISSING:" + ",".join(missing),
            })
            output.append(rec)
            continue
        try:
            estimate = evaluate_netcover(
                fee_ev=rec["fee_ev_usd"],
                reward_ev=rec["reward_ev_usd"],
                reward_haircut=rec.get("reward_haircut", reward_haircut),
                expected_il=rec["il_ev_usd"],
                lvr_coefficient=rec.get("lvr_coefficient", lvr_coefficient),
                entry_cost=rec["entry_cost_usd"],
                exit_cost=rec["exit_cost_usd"],
                gas=rec["gas_usd"],
                slippage=rec["slippage_usd"],
                reward_conversion_cost=rec["reward_conversion_cost_usd"],
                exit_latency_loss=rec["exit_latency_loss_usd"],
            )
        except ValueError as exc:
            rec.update({
                "risk_usd": None,
                "expected_net_yield_usd": None,
                "expected_net_yield_pct": None,
                "netcover_ratio": None,
                "netcover": None,
                "netcover_pass": False,
                "rejection_reason": f"NETCOVER_INPUT_INVALID:{exc}",
            })
            output.append(rec)
            continue
        capital = rec.get("capital_usd")
        net_yield = estimate.adjusted_income_ev - estimate.expected_risk_cost
        net_yield_pct = None
        if capital is not None:
            try:
                capital_value = _amount("capital_usd", capital, positive=True)
                net_yield_pct = net_yield / capital_value * 100.0
            except ValueError:
                pass
        rec.update({
            "lvr_ev_usd": estimate.expected_lvr_model,
            "risk_usd": estimate.expected_risk_cost,
            "expected_net_yield_usd": net_yield,
            "expected_net_yield_pct": net_yield_pct,
            "netcover_ratio": estimate.netcover,
            "netcover": estimate.netcover,
            "netcover_pass": estimate.shadow_candidate,
            "rejection_reason": None if estimate.shadow_candidate else "NETCOVER_BELOW_SHADOW",
            "netcover_semantics": dict(estimate.semantics),
        })
        output.append(rec)
    return output


__all__ = [
    "ACTIVE_SHARE_LIMIT", "HARD_POSITION_TVL_SHARE", "MIN_PROFIT_USD",
    "NETCOVER_SHADOW", "NETCOVER_TINY_LIVE", "POSITION_TVL_SHARE",
    "REWARD_HAIRCUTS", "SAFETY_MULTIPLE", "AbsoluteProfitDecision",
    "NetCoverEstimate", "absolute_profit_gate", "adjusted_income_ev",
    "apply_netcover_gate", "evaluate_netcover", "expected_risk_cost",
    "gross_fee_cover", "netcover", "position_cap_usd",
]
