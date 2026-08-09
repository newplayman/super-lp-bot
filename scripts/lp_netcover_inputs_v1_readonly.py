#!/usr/bin/env python3
"""Assemble the nine horizon-USD inputs consumed by the WP-04 NetCover gate.

This module is pure/read-only.  It deliberately does not make RPC calls and it
does not invent missing market evidence.  A caller may enrich a scanner record
with measured pool state first; absent horizon, volatility, depth, or reward
conversion evidence remains ``None`` so ``apply_netcover_gate`` rejects it.

The calculations reuse the already-tested cost-sensitivity and swap-cost
building blocks.  INV-GATE-01 thresholds remain owned by
``lp_netcover_engine_v1_readonly`` and are not changed here.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Mapping

from scripts.lp_cost_sensitivity_v1_readonly import (  # exact WP-04 assembly math
    HOURS_PER_YEAR,
    _swap_components,
    price_from_sqrt_x96,
)
from scripts.lp_netcover_engine_v1_readonly import REWARD_HAIRCUTS
from scripts.lp_portfolio_allocator_v1_readonly import M1_MIN_POSITION_USD
from scripts.lp_swap_cost_model_v1_readonly import exit_conversion_cost_usd


NETCOVER_INPUT_FIELDS = (
    "fee_ev_usd",
    "reward_ev_usd",
    "il_ev_usd",
    "entry_cost_usd",
    "exit_cost_usd",
    "gas_usd",
    "slippage_usd",
    "reward_conversion_cost_usd",
    "exit_latency_loss_usd",
)

PROFILE_HORIZONS_HOURS = {
    "PASSIVE": frozenset({7.0 * 24.0, 14.0 * 24.0, 30.0 * 24.0}),
    "TACTICAL": frozenset({6.0, 12.0, 24.0, 72.0}),
}

# Same committed historical Base observation used by lp_cost_sensitivity.
# Unknown chains stay unavailable; they are never assigned Base's value.
HISTORICAL_GAS_USD = {"base": 0.0795}
HISTORICAL_GAS_SOURCES = {
    "base": (
        "historical_observation:"
        "reports/strategy_evidence_r4b_active_liquidity_corrected_replay/"
        "20260612_090000/active_liquidity_corrected_replay_matrix.jsonl"
    )
}

ESTABLISHED_FEE_HAIRCUT = 0.65
NEW_OR_AGE_UNKNOWN_FEE_HAIRCUT = 0.40
EXIT_LATENCY_LOSS_APR_PCT_MODEL = 0.50
LVR_COEFFICIENT_MODEL = 0.50

INPUT_SEMANTICS = {
    "fee_ev_usd": "model_estimate",
    "reward_ev_usd": "model_estimate",
    "il_ev_usd": "model_estimate",
    "entry_cost_usd": "model_estimate",
    "exit_cost_usd": "model_estimate",
    "gas_usd": "historical_observation",
    "slippage_usd": "model_estimate",
    "reward_conversion_cost_usd": "model_estimate",
    "exit_latency_loss_usd": "model_estimate",
}

INPUT_SOURCES = {
    "fee_ev_usd": "model_estimate:conservative_fee_apr_horizon",
    "reward_ev_usd": "model_estimate:reward_apr_horizon",
    "il_ev_usd": "model_estimate:il_apr_horizon_with_sigma_evidence",
    "entry_cost_usd": "model_estimate:lp_swap_cost_model_v1_readonly._swap_components",
    "exit_cost_usd": "model_estimate:lp_swap_cost_model_v1_readonly._swap_components",
    "gas_usd": None,  # chain-specific historical source is selected below
    "slippage_usd": "model_estimate:lp_swap_cost_model_v1_readonly._swap_components",
    "reward_conversion_cost_usd": (
        "model_estimate:lp_swap_cost_model_v1_readonly.exit_conversion_cost_usd"
    ),
    "exit_latency_loss_usd": "model_estimate:free_rpc_exit_latency_apr_horizon",
}

_STABLE_REWARD_SYMBOLS = frozenset({"USDC", "USDT", "DAI", "PYUSD", "USDE", "EURC"})
_MAJOR_REWARD_SYMBOLS = frozenset({"ETH", "WETH", "BTC", "WBTC", "CBBTC", "SOL"})
_KNOWN_REWARD_TOKEN_CATEGORIES = {
    # Base AERO, present in the current scanner universe.
    "0x940181a94a35a4569e4529a3cdfb74e38fd98631": "protocol",
}

_BASE_STABLE_TOKENS = frozenset({
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2",  # USDT
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",  # DAI
})


def _number(value: Any, *, positive: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0 or (positive and number <= 0.0):
        return None
    return number


def _first_number(record: Mapping[str, Any], *keys: str, positive: bool = False) -> float | None:
    for key in keys:
        value = _number(record.get(key), positive=positive)
        if value is not None:
            return value
    return None


def profile_kind(record: Mapping[str, Any]) -> str | None:
    """Return PASSIVE/TACTICAL without selecting a horizon on the pool's behalf."""
    raw = str(record.get("profile") or record.get("strategy_profile") or "").upper()
    if raw in {"PASSIVE", "PASSIVE_CL", "EMISSION"}:
        return "PASSIVE"
    if raw in {"TACTICAL", "RWA_SESSION", "REWARDED_CLMM"}:
        return "TACTICAL"
    project = str(record.get("project") or "").lower()
    if project in {"aerodrome-slipstream", "uniswap-v3", "uniswap-v4"}:
        return "PASSIVE"
    if project in {"orca", "raydium", "raydium-clmm", "orca-whirlpool"}:
        return "TACTICAL"
    return None


def holding_horizon_hours(record: Mapping[str, Any]) -> float | None:
    """Read H chosen by the profile/ER stage and validate its PRD discrete set."""
    profile = profile_kind(record)
    if profile is None:
        return None
    hours = _first_number(
        record,
        "holding_horizon_hours",
        "profile_horizon_hours",
        "er_horizon_hours",
        positive=True,
    )
    if hours is None:
        days = _first_number(
            record,
            "holding_horizon_days",
            "profile_horizon_days",
            "er_horizon_days",
            positive=True,
        )
        hours = days * 24.0 if days is not None else None
    if hours is None or hours not in PROFILE_HORIZONS_HOURS[profile]:
        return None
    return hours


def reward_category(record: Mapping[str, Any]) -> str | None:
    """Classify only explicit or allowlisted reward evidence; unknown is closed."""
    explicit = str(record.get("reward_category") or "").strip().lower()
    aliases = {
        "stable": "stablecoin",
        "stablecoin": "stablecoin",
        "major": "major",
        "protocol": "protocol",
        "protocol_token": "protocol",
        "new": "new_token",
        "new_token": "new_token",
        "points": "points",
    }
    if explicit in aliases:
        return aliases[explicit]
    if record.get("reward_is_points") is True:
        return "points"
    symbol = str(record.get("reward_token_symbol") or "").strip().upper()
    if symbol in _STABLE_REWARD_SYMBOLS:
        return "stablecoin"
    if symbol in _MAJOR_REWARD_SYMBOLS:
        return "major"
    tokens = record.get("rewardTokens") or record.get("reward_tokens") or ()
    if isinstance(tokens, str):
        tokens = (tokens,)
    categories = {
        _KNOWN_REWARD_TOKEN_CATEGORIES.get(str(token).lower())
        for token in tokens
    }
    categories.discard(None)
    return next(iter(categories)) if len(categories) == 1 else None


def _pool_price(record: Mapping[str, Any]) -> float | None:
    sqrt_price = _first_number(record, "sqrtPriceX96", "sqrt_price_x96", positive=True)
    dec0 = _first_number(record, "dec0")
    dec1 = _first_number(record, "dec1")
    if sqrt_price is None or dec0 is None or dec1 is None:
        return None
    try:
        price = price_from_sqrt_x96(int(sqrt_price), dec0=int(dec0), dec1=int(dec1))
    except (OverflowError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0.0 else None


def _pool_cost_state(record: Mapping[str, Any]) -> tuple[float, int, int] | None:
    """Normalize measured pair price so token1 is a USD-stable quote asset."""
    dec0 = _first_number(record, "dec0")
    dec1 = _first_number(record, "dec1")
    if dec0 is None or dec1 is None:
        return None
    direct = _first_number(record, "price_usd", "pool_price_usd", positive=True)
    if direct is not None:
        return direct, int(dec0), int(dec1)

    pair_price = _first_number(
        record, "last_swap_price_token1_per_token0", positive=True
    )
    if pair_price is None:
        pair_price = _pool_price(record)
    if pair_price is None:
        return None
    token0 = str(record.get("token0") or "").lower()
    token1 = str(record.get("token1") or "").lower()
    if token1 in _BASE_STABLE_TOKENS:
        return pair_price, int(dec0), int(dec1)
    if token0 in _BASE_STABLE_TOKENS:
        return 1.0 / pair_price, int(dec1), int(dec0)
    return None


def _swap_costs(record: Mapping[str, Any], size_usd: float) -> dict[str, float | None]:
    l_raw = _first_number(
        record,
        "l_active_raw",
        "active_liquidity_raw",
        "l_active_raw_historical",
        "last_swap_liquidity_raw",
        positive=True,
    )
    state = _pool_cost_state(record)
    fee_tier = _first_number(record, "fee_tier")
    if l_raw is None or state is None or fee_tier is None:
        return {key: None for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}
    price, dec0, dec1 = state
    try:
        # Reuse the exact component split exercised by cost sensitivity.
        components = _swap_components(
            size_usd,
            SimpleNamespace(
                l_active_raw_historical=l_raw,
                price_usd=price,
                fee_tier=fee_tier,
                dec0=int(dec0),
                dec1=int(dec1),
            ),
        )
    except (ArithmeticError, ValueError):
        return {key: None for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}
    return {key: components[key] for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}


def _reward_conversion_cost(
    record: Mapping[str, Any], reward_ev_usd: float | None, category: str | None
) -> float | None:
    if reward_ev_usd is None:
        return None
    if reward_ev_usd == 0.0:
        return 0.0
    if category == "points":
        # Points carry a zero income haircut and are not a swappable token.
        return 0.0
    l_raw = _first_number(record, "reward_conversion_l_active_raw", positive=True)
    price = _first_number(record, "reward_conversion_price_usd", positive=True)
    fee_tier = _first_number(record, "reward_conversion_fee_tier")
    dec0 = _first_number(record, "reward_conversion_dec0")
    dec1 = _first_number(record, "reward_conversion_dec1")
    if None in (l_raw, price, fee_tier, dec0, dec1):
        return None
    side = str(record.get("reward_conversion_side") or "sell_base")
    if side not in {"buy_base", "sell_base"}:
        return None
    try:
        return exit_conversion_cost_usd(
            reward_ev_usd,
            l_raw,
            price,
            fee_tier,
            int(dec0),
            int(dec1),
            side,
        )
    except (ArithmeticError, ValueError):
        return None


def assemble_netcover_inputs(
    source: Mapping[str, Any],
    *,
    position_usd: float = M1_MIN_POSITION_USD,
) -> dict[str, Any]:
    """Return a copy with all nine USD keys and auditable semantics attached."""
    record = dict(source)
    size = _number(position_usd, positive=True)
    if size is None:
        raise ValueError("position_usd must be finite and positive")
    horizon = holding_horizon_hours(record)
    fraction = horizon / HOURS_PER_YEAR if horizon is not None else None

    fee_24h = _first_number(record, "fee_apr_24h", "fee_apr_onchain")
    fee_7d = _first_number(record, "fee_apr_7d", "apyBase")
    age_is_established = record.get("is_new_pool") is False
    fee_haircut = ESTABLISHED_FEE_HAIRCUT if age_is_established else NEW_OR_AGE_UNKNOWN_FEE_HAIRCUT
    fee_ev = (
        size * min(fee_24h, fee_7d) * fee_haircut / 100.0 * fraction
        if None not in (fee_24h, fee_7d, fraction)
        else None
    )

    reward_apr = _first_number(record, "reward_apr", "apyReward")
    category = reward_category(record) if reward_apr not in (None, 0.0) else None
    haircut = REWARD_HAIRCUTS.get(category) if category is not None else None
    reward_ev = (
        size * reward_apr / 100.0 * fraction
        if reward_apr is not None and fraction is not None and (reward_apr == 0.0 or haircut is not None)
        else None
    )

    # Prefer the pair-price volatility carried from multi-window replay.  The
    # generic screener ``sigma`` can describe headline APR dispersion instead.
    sigma = _first_number(record, "sigma_pair", "sigma_daily", "sigma")
    il_apr = _first_number(record, "il_apr", "expected_il_apr_pct")
    il_ev = (
        size * il_apr / 100.0 * fraction
        if sigma is not None and il_apr is not None and fraction is not None
        else None
    )

    costs = _swap_costs(record, size)
    chain = str(record.get("chain") or record.get("network") or "").strip().lower()
    gas = HISTORICAL_GAS_USD.get(chain)
    reward_conversion = _reward_conversion_cost(record, reward_ev, category)
    exit_latency = (
        size * EXIT_LATENCY_LOSS_APR_PCT_MODEL / 100.0 * fraction
        if fraction is not None
        else None
    )

    calculated = {
        "fee_ev_usd": fee_ev,
        "reward_ev_usd": reward_ev,
        "il_ev_usd": il_ev,
        **costs,
        "gas_usd": gas,
        "reward_conversion_cost_usd": reward_conversion,
        "exit_latency_loss_usd": exit_latency,
    }
    # This scanner assembly boundary accepts only values calculated above from
    # raw evidence.  In particular, an upstream record carrying explicit USD
    # values (including zero) cannot bypass missing sigma/depth/horizon evidence.
    # Independently preassembled records can still be evaluated by WP-04's
    # engine directly; they are deliberately not trusted by this live scanner
    # adapter because their provenance cannot be verified here.
    field_semantics: dict[str, str | None] = {}
    for field in NETCOVER_INPUT_FIELDS:
        value = calculated[field]
        record[field] = value
        semantics = INPUT_SEMANTICS[field] if value is not None else None
        source_label = (
            HISTORICAL_GAS_SOURCES.get(chain)
            if field == "gas_usd"
            else INPUT_SOURCES[field]
        )
        record[f"{field}_semantics"] = semantics
        record[f"{field}_source"] = source_label if value is not None else None
        field_semantics[field] = semantics
    record.update({
        "capital_usd": size,
        "holding_horizon_hours": horizon,
        "netcover_profile": profile_kind(record),
        "fee_apr_haircut": fee_haircut,
        "reward_category": category,
        "lvr_coefficient": LVR_COEFFICIENT_MODEL,
        "netcover_input_semantics": field_semantics,
        "gas_usd_source": HISTORICAL_GAS_SOURCES.get(chain),
        "netcover_input_position_source": "M1_MIN_POSITION_USD",
        "netcover_input_assembly_source": (
            "lp_netcover_inputs_v1_readonly:raw_evidence_calculated_only"
        ),
    })
    # A positive calculated reward EV always requires a classified category;
    # zero-reward records do not need to override WP-04's irrelevant default.
    if haircut is not None:
        record["reward_haircut"] = haircut
    if all(record[field] is not None for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")):
        record["round_trip_cost_usd"] = (
            record["entry_cost_usd"] + record["exit_cost_usd"] + record["slippage_usd"]
        )
    else:
        record["round_trip_cost_usd"] = None
    return record


def assemble_records(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [assemble_netcover_inputs(record) for record in records]
