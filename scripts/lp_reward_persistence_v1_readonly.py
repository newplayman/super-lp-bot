#!/usr/bin/env python3
"""Conservative reward-persistence evidence for the read-only LP funnel.

DefiLlama's enriched history fields describe *total* APY, not reward-only
history.  They are therefore a limited surrogate, never measured persistence.
Only scanner-owned, time-ordered observations may produce the trusted 24-hour
grade.  This module is pure: it does not open SQLite or make network requests.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


MIN_REWARD_OBSERVATION_HOURS = 24.0
MAX_REWARD_OBSERVATION_GAP_HOURS = 0.5
REWARD_OBSERVATION_POSITIVE_APR_PCT = 0.0

SURROGATE_MIN_COUNT_DAYS = 30.0
SURROGATE_HISTORY_TO_CURRENT_MIN = 0.50
SURROGATE_STRONG_FACTOR = 0.25
SURROGATE_EFFECTIVE_HOURS = 6.0

SURROGATE_STRONG = "SURROGATE_STRONG"
SURROGATE_WEAK = "SURROGATE_WEAK"
SURROGATE_ABSENT = "SURROGATE_ABSENT"


def finite_number(value: Any, *, nonnegative: bool = False) -> float | None:
    """Return a finite numeric value while excluding booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        return None
    return number


def _reward_apr(record: Mapping[str, Any]) -> float | None:
    raw = record.get("apyReward")
    if raw is None:
        raw = record.get("reward_apr", 0.0)
    return finite_number(raw)


def reward_persistence_surrogate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Classify DefiLlama snapshot evidence without claiming measurement.

    ``apyMean30d`` is the mean of total APY and ``apyBase7d`` is a seven-day
    base-APY estimate.  Their difference is deliberately labelled a mismatched-
    window proxy.  A strong surrogate receives only the minimum 6h credibility
    factor (6/24 = 0.25); it can never become the trusted 24h grade.
    """
    reward = _reward_apr(record)
    fields = {
        "apy": finite_number(record.get("apy"), nonnegative=True),
        "apy_base": finite_number(record.get("apyBase"), nonnegative=True),
        "apy_reward": reward,
        "apy_mean_30d": finite_number(record.get("apyMean30d"), nonnegative=True),
        "apy_base_7d": finite_number(record.get("apyBase7d"), nonnegative=True),
        "apy_pct_1d": finite_number(record.get("apyPct1D")),
        "apy_pct_7d": finite_number(record.get("apyPct7D")),
        "apy_pct_30d": finite_number(record.get("apyPct30D")),
        "count": finite_number(record.get("count"), nonnegative=True),
    }
    historical_keys = (
        "apy_mean_30d", "apy_base_7d", "apy_pct_1d", "apy_pct_7d",
        "apy_pct_30d", "count",
    )
    # One generic total-APY field alone is not enough to claim even a weak
    # reward-specific surrogate.  Require at least two independent enriched
    # clues; otherwise retain the original absent/fail-closed semantics.
    usable_history = sum(fields[key] is not None for key in historical_keys) >= 2

    if reward is None or reward < 0.0:
        return {
            "tier": SURROGATE_ABSENT,
            "entry_eligible": False,
            "score_factor": 0.0,
            "effective_duration_hours": None,
            "reason": "REWARD_APR_INVALID",
            "evidence_source": "absent",
            "inputs": fields,
        }
    if reward == 0.0:
        return {
            "tier": SURROGATE_ABSENT,
            "entry_eligible": True,
            "score_factor": 1.0,
            "effective_duration_hours": None,
            "reason": None,
            "evidence_source": "absent",
            "inputs": fields,
        }

    mean30 = fields["apy_mean_30d"]
    base7 = fields["apy_base_7d"]
    pct30 = fields["apy_pct_30d"]
    count = fields["count"]
    base_now = fields["apy_base"]
    total_now = fields["apy"]
    if total_now is None:
        total_now = (base_now or 0.0) + reward

    complete = None not in (mean30, base7, pct30, count)
    historical_reward_proxy = (
        max(float(mean30) - float(base7), 0.0) if complete else None
    )
    same_order = bool(
        historical_reward_proxy is not None
        and historical_reward_proxy >= SURROGATE_HISTORY_TO_CURRENT_MIN * reward
    )
    not_collapsed = bool(pct30 is not None and pct30 >= -float(total_now))
    old_enough = bool(count is not None and count >= SURROGATE_MIN_COUNT_DAYS)
    fields.update({
        "current_total_apy": total_now,
        "historical_reward_proxy_mismatched_windows": historical_reward_proxy,
        "history_to_current_min": SURROGATE_HISTORY_TO_CURRENT_MIN,
        "same_order": same_order,
        "thirty_day_total_apy_not_collapsed": not_collapsed,
        "count_old_enough": old_enough,
    })

    if complete and same_order and not_collapsed and old_enough:
        return {
            "tier": SURROGATE_STRONG,
            "entry_eligible": True,
            "score_factor": SURROGATE_STRONG_FACTOR,
            "effective_duration_hours": SURROGATE_EFFECTIVE_HOURS,
            "reason": None,
            "evidence_source": "surrogate_defillama",
            "inputs": fields,
        }
    if usable_history:
        failed = []
        if not complete:
            failed.append("incomplete_required_history")
        if complete and not same_order:
            failed.append("historical_reward_proxy_below_half_current")
        if complete and not not_collapsed:
            failed.append("total_apy_collapsed_vs_30d")
        if complete and not old_enough:
            failed.append("count_below_30")
        return {
            "tier": SURROGATE_WEAK,
            "entry_eligible": False,
            "score_factor": 0.0,
            "effective_duration_hours": None,
            "reason": "REWARD_PERSISTENCE_SURROGATE_WEAK",
            "evidence_source": "surrogate_defillama",
            "inputs": {**fields, "failed_conditions": failed},
        }
    return {
        "tier": SURROGATE_ABSENT,
        "entry_eligible": False,
        "score_factor": 0.0,
        "effective_duration_hours": None,
        "reason": "REWARD_PERSISTENCE_MISSING",
        "evidence_source": "absent",
        "inputs": fields,
    }


def _utc_datetime(value: datetime | str) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str) else value
    )
    if parsed.tzinfo is None:
        raise ValueError("reward observation timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def reward_high_duration_from_observations(
    observations: Iterable[Mapping[str, Any]],
    *,
    cutoff: datetime | str,
    max_gap_hours: float = MAX_REWARD_OBSERVATION_GAP_HOURS,
    positive_apr_pct: float = REWARD_OBSERVATION_POSITIVE_APR_PCT,
) -> dict[str, Any]:
    """Measure the contiguous positive-reward suffix strictly before cutoff."""
    cutoff_dt = _utc_datetime(cutoff)
    if max_gap_hours <= 0.0:
        raise ValueError("max_gap_hours must be positive")
    eligible: dict[datetime, float | None] = {}
    for row in observations:
        try:
            observed_at = _utc_datetime(row["as_of"])
        except (KeyError, TypeError, ValueError):
            continue
        if observed_at >= cutoff_dt:
            continue
        eligible[observed_at] = finite_number(row.get("apy_reward"))
    ordered = sorted(eligible.items())
    empty = {
        "duration_hours": None,
        "sample_count": 0,
        "first_as_of": None,
        "last_as_of": None,
        "status": "INSUFFICIENT_OBSERVATIONS",
    }
    if not ordered:
        return empty

    max_gap_seconds = float(max_gap_hours) * 3600.0
    last_time, last_reward = ordered[-1]
    if (cutoff_dt - last_time).total_seconds() > max_gap_seconds:
        return {**empty, "status": "STALE_OBSERVATIONS", "last_as_of": last_time.isoformat()}
    if last_reward is None or last_reward <= positive_apr_pct:
        return {
            "duration_hours": 0.0,
            "sample_count": 1,
            "first_as_of": last_time.isoformat(),
            "last_as_of": last_time.isoformat(),
            "status": "REWARD_NOT_HIGH",
        }

    suffix = [(last_time, last_reward)]
    newer_time = last_time
    for observed_at, reward in reversed(ordered[:-1]):
        if (newer_time - observed_at).total_seconds() > max_gap_seconds:
            break
        if reward is None or reward <= positive_apr_pct:
            break
        suffix.append((observed_at, reward))
        newer_time = observed_at
    suffix.reverse()
    if len(suffix) < 2:
        return {
            "duration_hours": None,
            "sample_count": 1,
            "first_as_of": suffix[0][0].isoformat(),
            "last_as_of": suffix[-1][0].isoformat(),
            "status": "INSUFFICIENT_OBSERVATIONS",
        }
    duration = (suffix[-1][0] - suffix[0][0]).total_seconds() / 3600.0
    return {
        "duration_hours": duration,
        "sample_count": len(suffix),
        "first_as_of": suffix[0][0].isoformat(),
        "last_as_of": suffix[-1][0].isoformat(),
        "status": "CONTIGUOUS_HIGH",
    }


__all__ = [
    "MAX_REWARD_OBSERVATION_GAP_HOURS",
    "MIN_REWARD_OBSERVATION_HOURS",
    "SURROGATE_ABSENT",
    "SURROGATE_STRONG",
    "SURROGATE_STRONG_FACTOR",
    "SURROGATE_WEAK",
    "reward_high_duration_from_observations",
    "reward_persistence_surrogate",
]
