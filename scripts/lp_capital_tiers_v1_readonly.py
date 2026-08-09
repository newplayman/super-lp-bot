#!/usr/bin/env python3
"""Frozen PRD v2.1 capital-tier configuration (pure/read-only)."""
from __future__ import annotations

import math


# PRD v2.1 section 2.1: the static TVL floor is only a coarse-screen input.
# Final sizing remains the runtime INV-TVLSHARE-01 PositionCap calculation.
CAPITAL_TIER_TVL_MIN_USD = {
    "M1": 150_000.0,
    "M2": 200_000.0,
    "M3": 500_000.0,
    "M4": 1_000_000.0,
}

# PRD v2.1 section 2.1 ``TierConfiguredMax`` row.
CAPITAL_TIER_CONFIGURED_MAX_USD = {
    "M1": 60.0,
    "M2": 75.0,
    "M3": 200.0,
    "M4": 500.0,
}

DEFAULT_CAPITAL_TIER = "M1"
CAPITAL_TIERS = tuple(CAPITAL_TIER_TVL_MIN_USD)


def normalize_capital_tier(value: object) -> str:
    tier = str(value or DEFAULT_CAPITAL_TIER).strip().upper()
    if tier not in CAPITAL_TIER_TVL_MIN_USD:
        raise ValueError(f"unknown capital tier: {value!r}")
    return tier


def coarse_tvl_min_usd(tier: object, tightening_override: object = None) -> float:
    """Return the PRD floor, allowing an override to tighten but never relax it."""
    floor = CAPITAL_TIER_TVL_MIN_USD[normalize_capital_tier(tier)]
    if tightening_override is None:
        return floor
    try:
        override = float(tightening_override)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_tvl tightening override must be finite and positive") from exc
    if not math.isfinite(override) or override <= 0.0:
        raise ValueError("min_tvl tightening override must be finite and positive")
    return max(floor, override)


__all__ = [
    "CAPITAL_TIERS",
    "CAPITAL_TIER_CONFIGURED_MAX_USD",
    "CAPITAL_TIER_TVL_MIN_USD",
    "DEFAULT_CAPITAL_TIER",
    "coarse_tvl_min_usd",
    "normalize_capital_tier",
]
