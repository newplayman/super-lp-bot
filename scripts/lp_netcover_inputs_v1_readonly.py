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
from scripts.lp_capital_tiers_v1_readonly import (
    CAPITAL_TIER_CONFIGURED_MAX_USD,
    DEFAULT_CAPITAL_TIER,
    normalize_capital_tier,
)
from scripts.lp_netcover_engine_v1_readonly import (
    ACTIVE_SHARE_LIMIT,
    HARD_POSITION_TVL_SHARE,
    NETCOVER_MODEL_AMM_CONSTANT_PRODUCT,
    NETCOVER_MODEL_CLMM,
    POSITION_TVL_SHARE,
    PROTOCOL_TYPE_AMM_CONSTANT_PRODUCT,
    PROTOCOL_TYPE_CLMM,
    REWARD_HAIRCUTS,
    position_cap_usd,
)
from scripts.lp_portfolio_allocator_v1_readonly import M1_MIN_POSITION_USD
from scripts.lp_universe_screener_v1_readonly import reward_persistence_gate
from scripts.lp_swap_cost_model_v1_readonly import exit_conversion_cost_usd
from scripts.lp_solana_token_constants_v1_readonly import STABLE_MINTS as SOLANA_STABLE_MINTS
from scripts.lp_v3_fee_share import position_liquidity_raw
from scripts.lp_vol_range_sizer_v1_readonly import recommend_range_pct


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

# fee_apr_7d is an annualized observation over a seven-day evidence window.  The
# reference horizon below anchors only the range/share comparison.  Both fees
# and CL gauge emissions accrue over the actual holding horizon and are
# allocated by the position's in-range liquidity weight, so both income terms
# retain H/8760 and receive the same share(range(H))/share(range(H_ref)) factor.
FEE_EVIDENCE_REFERENCE_HOURS = 7.0 * 24.0

# ADD-1 task B: above this annualized fixed drag, move only upward through the
# profile's frozen discrete horizon set.  This is a modelling annotation and
# horizon selection rule, not a NetCover acceptance threshold.
DRAG_APR_MAX = 15.0

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

# Full-range AMMs have no volatility-sized range to restrain the horizon.  H
# therefore improves income against fixed costs monotonically; cap it so H
# cannot become a free optimisation lever.
AMM_HOLDING_HORIZON_MAX_HOURS = 720.0

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
    "fee_ev_usd": (
        "model_estimate:fee_apr_horizon_vol_range_raw_liquidity_share"
    ),
    "reward_ev_usd": "model_estimate:reward_apr_horizon_vol_range_raw_liquidity_share",
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

# Stable quote evidence is chain-specific.  An omitted or unknown chain must
# never inherit Base token semantics.
_STABLE_TOKENS_BY_CHAIN = {
    "base": _BASE_STABLE_TOKENS,
    "solana": frozenset(mint.lower() for mint in SOLANA_STABLE_MINTS),
}


def _stable_tokens(record: Mapping[str, Any]) -> frozenset[str]:
    chain = str(record.get("chain") or "").strip().lower()
    return _STABLE_TOKENS_BY_CHAIN.get(chain, frozenset())


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


def _horizon_label(hours: float) -> str:
    return str(int(hours)) if float(hours).is_integer() else str(hours)


def _fixed_drag_apr_pct(
    *, fee_tier: float, gas_usd: float, position_usd: float, horizon_hours: float
) -> float:
    """Annualized one-off round-trip fee + gas drag; fee_tier is a fraction."""
    return (
        (2.0 * fee_tier + gas_usd / position_usd)
        / (horizon_hours / HOURS_PER_YEAR)
        * 100.0
    )


def select_drag_adjusted_horizon(
    *,
    profile: str,
    er_horizon_hours: float,
    fee_tier: float | None,
    gas_usd: float | None,
    position_usd: float = M1_MIN_POSITION_USD,
) -> dict[str, Any]:
    """Apply ADD-1 task B without using H as a continuous score knob.

    The ER candidate remains authoritative when its fixed-cost drag is already
    tolerable or when drag evidence is unavailable.  Otherwise the smallest
    *higher* legal profile H at/below ``DRAG_APR_MAX`` is selected.  If even the
    maximum legal H remains high, evaluation continues with an explicit flag.
    """
    kind = str(profile).upper()
    legal = sorted(PROFILE_HORIZONS_HOURS.get(kind, ()))
    original = _number(er_horizon_hours, positive=True)
    if original is None or original not in legal:
        raise ValueError("ER horizon must belong to the profile discrete set")
    tier = _number(fee_tier)
    gas = _number(gas_usd)
    size = _number(position_usd, positive=True)
    base = {
        "holding_horizon_hours": original,
        "holding_horizon_source": "ER_policy",
        "drag_apr_pct": None,
        "drag_apr_max_pct": DRAG_APR_MAX,
        "high_drag_flag": False,
    }
    if tier is None or gas is None or size is None:
        return base

    initial_drag = _fixed_drag_apr_pct(
        fee_tier=tier, gas_usd=gas, position_usd=size, horizon_hours=original
    )
    if initial_drag <= DRAG_APR_MAX:
        base["drag_apr_pct"] = initial_drag
        return base

    candidates = [hours for hours in legal if hours > original]
    selected = original
    selected_drag = initial_drag
    for hours in candidates:
        drag = _fixed_drag_apr_pct(
            fee_tier=tier, gas_usd=gas, position_usd=size, horizon_hours=hours
        )
        selected, selected_drag = hours, drag
        if drag <= DRAG_APR_MAX:
            break
    base.update({
        "holding_horizon_hours": selected,
        "holding_horizon_source": (
            f"drag_adjusted(from={_horizon_label(original)})"
            if selected != original else "ER_policy"
        ),
        "drag_apr_pct": selected_drag,
        "high_drag_flag": selected_drag > DRAG_APR_MAX,
    })
    return base


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
    if project in {
        "orca",
        "orca-dex",
        "orca-whirlpool",
        "raydium",
        "raydium-amm",
        "raydium-clmm",
    }:
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


def amm_holding_horizon_hours(record: Mapping[str, Any]) -> float | None:
    """Read an AMM horizon, enforcing FIX-E2's non-negotiable 720h cap."""
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
    if hours is None or hours > AMM_HOLDING_HORIZON_MAX_HOURS:
        return None
    return hours


def constant_product_il_fraction(price_ratio: Any) -> float:
    """Return signed v2 IL relative to HODL for ``k=P_exit/P_entry``.

    The analytic expression is ``2*sqrt(k)/(1+k)-1``.  It is zero at k=1
    and non-positive elsewhere; callers convert its magnitude to a positive
    NetCover risk cost.
    """
    k = _number(price_ratio, positive=True)
    if k is None:
        raise ValueError("price_ratio must be finite and positive")
    value = 2.0 * math.sqrt(k) / (1.0 + k) - 1.0
    if not math.isfinite(value) or value > 1e-15:
        raise ValueError("constant-product IL result is invalid")
    return min(value, 0.0)


def _amm_price_ratio(record: Mapping[str, Any]) -> float | None:
    """Accept only an explicitly measured horizon price ratio."""
    source = str(record.get("amm_price_ratio_source") or "")
    if not source.startswith("measured:"):
        return None
    ratio = _first_number(record, "amm_price_ratio", positive=True)
    if ratio is not None:
        return ratio
    entry = _first_number(record, "amm_entry_price", positive=True)
    exit_ = _first_number(record, "amm_exit_price", positive=True)
    return exit_ / entry if entry is not None and exit_ is not None else None


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
    if dec0 is None or dec1 is None:
        return None
    if sqrt_price is not None:
        try:
            price = price_from_sqrt_x96(int(sqrt_price), dec0=int(dec0), dec1=int(dec1))
        except (OverflowError, ValueError):
            return None
    else:
        sqrt_price_x64 = _first_number(record, "sqrt_price_x64", positive=True)
        if sqrt_price_x64 is None:
            return None
        ratio = sqrt_price_x64 / float(1 << 64)
        price = ratio * ratio * (10.0 ** (int(dec0) - int(dec1)))
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
    stable_tokens = _stable_tokens(record)
    if token1 in stable_tokens:
        return pair_price, int(dec0), int(dec1)
    if token0 in stable_tokens:
        return 1.0 / pair_price, int(dec1), int(dec0)
    return None


def _range_aware_fee_ev(
    record: Mapping[str, Any],
    *,
    size_usd: float,
    horizon_hours: float | None,
    fee_apr_pct: float | None,
    fee_haircut: float,
    scanner_measured_evidence: Mapping[str, Any] | None,
) -> tuple[float | None, dict[str, float | None]]:
    """Model FeeEV from a fixed 7d evidence anchor and raw-liquidity density.

    ``fee_apr_pct * size`` is already a return-on-LP-capital quantity, so an
    absolute pool share must not be multiplied into it a second time.  Instead
    canonical position liquidity provides a *relative* share adjustment versus
    the same 50U position at the seven-day evidence range.  This preserves the
    observed APR anchor while making wider H ranges earn lower fee density.
    """
    metadata: dict[str, float | None] = {
        "fee_capture_reference_horizon_hours": FEE_EVIDENCE_REFERENCE_HOURS,
        "fee_capture_reference_range_pct": None,
        "fee_capture_target_range_pct": None,
        "fee_capture_reference_share": None,
        "fee_capture_target_share": None,
        "fee_capture_share_ratio": None,
        "fee_capture_evidence_apr_pct": fee_apr_pct,
        "fee_capture_haircut": fee_haircut,
        "active_liquidity_notional_usd": None,
    }
    # Generic DefiLlama ``sigma`` may be headline APR dispersion.  Fee density
    # accepts only pair-price volatility measured by the multi-window path.
    sigma = _first_number(record, "sigma_pair", "sigma_daily", positive=True)
    if horizon_hours is None or fee_apr_pct is None or sigma is None:
        return None, metadata

    target_range = recommend_range_pct(sigma, horizon_hours / 24.0)
    reference_range = recommend_range_pct(
        sigma, FEE_EVIDENCE_REFERENCE_HOURS / 24.0
    )
    metadata["fee_capture_target_range_pct"] = target_range
    metadata["fee_capture_reference_range_pct"] = reference_range
    # Canonical liquidity math takes sqrt(p_lo); a >=100% half-range is not a
    # valid two-sided CL position.  Do not clamp it into a more favorable band.
    if not (
        math.isfinite(target_range)
        and math.isfinite(reference_range)
        and 0.0 < target_range < 100.0
        and 0.0 < reference_range < 100.0
    ):
        return None, metadata

    # Main-pool price/L must come from the internal decoded-swap path or the
    # scanner's own slot0/liquidity reads.  In particular, a candidate-supplied
    # ``price_usd`` plus liquidity cannot make FeeEV calculable.
    state_record = dict(record)
    for key in ("price_usd", "pool_price_usd"):
        state_record.pop(key, None)
    swap_provenance = record.get("last_swap_cost_state_source") == (
        "measured:latest_decoded_swap_event"
    )
    live_provenance = (
        str(record.get("sqrt_price_x96_source") or "").startswith(
            "measured:pool.slot0"
        )
        and str(record.get("l_active_raw_source") or "").startswith(
            "measured:pool.liquidity"
        )
    )
    solana_live_provenance = (
        str(record.get("sqrt_price_x64_source") or "")
        == "measured:pool.sqrt_price_x64"
        and str(record.get("l_active_raw_source") or "")
        == "measured:pool.liquidity"
    )
    if swap_provenance:
        l_active = _first_number(record, "last_swap_liquidity_raw", positive=True)
        for key in (
            "l_active_raw", "active_liquidity_raw", "l_active_raw_historical",
            "sqrtPriceX96", "sqrt_price_x96",
        ):
            state_record.pop(key, None)
    elif live_provenance or solana_live_provenance:
        l_active = _first_number(record, "l_active_raw", positive=True)
        for key in (
            "last_swap_price_token1_per_token0", "last_swap_liquidity_raw",
        ):
            state_record.pop(key, None)
    else:
        return None, metadata
    state = _pool_cost_state(state_record)
    position_quote = size_usd
    if state is None and scanner_measured_evidence:
        quote_usd = _number(scanner_measured_evidence.get("token1_usd"), positive=True)
        pair_price = _first_number(
            state_record, "last_swap_price_token1_per_token0", positive=True
        )
        dec0 = _first_number(state_record, "dec0")
        dec1 = _first_number(state_record, "dec1")
        if None not in (quote_usd, pair_price, dec0, dec1):
            state = (float(pair_price), int(dec0), int(dec1))
            position_quote = size_usd / float(quote_usd)
    if l_active is None or state is None:
        return None, metadata
    price, dec0, dec1 = state
    try:
        l_reference = position_liquidity_raw(
            position_quote, price, reference_range, dec0, dec1
        )
        l_target = position_liquidity_raw(
            position_quote, price, target_range, dec0, dec1
        )
        if not all(
            math.isfinite(value) and value > 0.0
            for value in (l_reference, l_target)
        ):
            return None, metadata
        reference_share = l_reference / (l_active + l_reference)
        target_share = l_target / (l_active + l_target)
        share_ratio = target_share / reference_share
        fee_anchor = (
            size_usd
            * fee_apr_pct
            * fee_haircut
            / 100.0
            * (horizon_hours / HOURS_PER_YEAR)
        )
        fee_ev = fee_anchor * share_ratio
        active_liquidity_notional_usd = l_active / l_target * size_usd
    except (ArithmeticError, OverflowError, ValueError):
        return None, metadata
    if not all(
        math.isfinite(value) and value >= 0.0
        for value in (
            reference_share,
            target_share,
            share_ratio,
            fee_ev,
            active_liquidity_notional_usd,
        )
    ):
        return None, metadata
    metadata.update({
        "fee_capture_reference_share": reference_share,
        "fee_capture_target_share": target_share,
        "fee_capture_share_ratio": share_ratio,
        "active_liquidity_notional_usd": active_liquidity_notional_usd,
    })
    return fee_ev, metadata


def _swap_costs(
    record: Mapping[str, Any],
    size_usd: float,
    scanner_measured_evidence: Mapping[str, Any] | None = None,
) -> dict[str, float | None]:
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
    quote_usd = None
    if state is None and scanner_measured_evidence:
        quote_usd = _number(scanner_measured_evidence.get("token1_usd"), positive=True)
        pair_price = _first_number(
            record, "last_swap_price_token1_per_token0", positive=True
        )
        dec0 = _first_number(record, "dec0")
        dec1 = _first_number(record, "dec1")
        if None not in (quote_usd, pair_price, dec0, dec1):
            state = (float(pair_price), int(dec0), int(dec1))
    if l_raw is None or state is None or fee_tier is None:
        return {key: None for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}
    price, dec0, dec1 = state
    try:
        notional_quote = size_usd / quote_usd if quote_usd is not None else size_usd
        # Reuse the exact component split exercised by cost sensitivity.
        components = _swap_components(
            notional_quote,
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
    if quote_usd is not None:
        components = {key: value * quote_usd for key, value in components.items()}
    return {key: components[key] for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}


def _reward_conversion_cost(
    record: Mapping[str, Any],
    reward_ev_usd: float | None,
    category: str | None,
    scanner_measured_evidence: Mapping[str, Any] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "reward_conversion_route_costs": [],
        "reward_conversion_selected_route_id": None,
        "reward_conversion_route_selection_rule": None,
    }
    if reward_ev_usd is None:
        return None, metadata
    if reward_ev_usd == 0.0:
        return 0.0, metadata
    if category == "points":
        # Points carry a zero income haircut and are not a swappable token.
        return 0.0, metadata
    if scanner_measured_evidence is not None:
        if not scanner_measured_evidence.get("complete"):
            return None, metadata
        routes = scanner_measured_evidence.get("aero_reward_routes")
        if not isinstance(routes, list) or not routes:
            return None, metadata
        measured_costs = []
        for route in routes:
            if not isinstance(route, Mapping):
                return None, metadata
            required = {
                "route_id", "pool", "factory", "token0", "token1", "dec0", "dec1",
                "fee_tier", "pair_price_token1_per_token0", "l_active_raw",
                "observed_block", "measurement_source", "executable", "tick_spacing",
            }
            if not required <= set(route):
                return None, metadata
            if not str(route["measurement_source"]).startswith(
                "measured:scanner_internal_rpc:"
            ):
                return None, metadata
            if not route.get("executable"):
                return None, metadata
            token0 = str(route["token0"]).lower()
            token1 = str(route["token1"]).lower()
            pair_price = _number(route["pair_price_token1_per_token0"], positive=True)
            l_route = _number(route["l_active_raw"], positive=True)
            fee_route = _number(route["fee_tier"])
            dec0_route = _number(route["dec0"])
            dec1_route = _number(route["dec1"])
            if None in (pair_price, l_route, fee_route, dec0_route, dec1_route):
                return None, metadata
            if token0 == next(iter(_KNOWN_REWARD_TOKEN_CATEGORIES)) and token1 in _BASE_STABLE_TOKENS:
                normalized_price = float(pair_price)
                normalized_dec0, normalized_dec1 = int(dec0_route), int(dec1_route)
            elif token1 == next(iter(_KNOWN_REWARD_TOKEN_CATEGORIES)) and token0 in _BASE_STABLE_TOKENS:
                normalized_price = 1.0 / float(pair_price)
                normalized_dec0, normalized_dec1 = int(dec1_route), int(dec0_route)
            else:
                return None, metadata
            try:
                cost = exit_conversion_cost_usd(
                    reward_ev_usd,
                    float(l_route),
                    normalized_price,
                    float(fee_route),
                    normalized_dec0,
                    normalized_dec1,
                    "sell_base",
                )
            except (ArithmeticError, ValueError):
                return None, metadata
            measured_costs.append({
                "route_id": str(route["route_id"]),
                "pool": str(route["pool"]),
                "status": "MEASURED_EXECUTABLE",
                "observed_block": route["observed_block"],
                "measured_conversion_cost_usd": cost,
            })
        executable = [
            item for item in measured_costs
            if item["measured_conversion_cost_usd"] is not None
        ]
        metadata["reward_conversion_route_costs"] = measured_costs
        if not executable:
            return None, metadata
        selected = max(
            executable,
            key=lambda item: (float(item["measured_conversion_cost_usd"]), item["route_id"]),
        )
        metadata["reward_conversion_selected_route_id"] = selected["route_id"]
        metadata["reward_conversion_route_selection_rule"] = (
            "highest_measured_conversion_cost_across_all_preregistered_executable_routes"
        )
        return float(selected["measured_conversion_cost_usd"]), metadata
    l_raw = _first_number(record, "reward_conversion_l_active_raw", positive=True)
    price = _first_number(record, "reward_conversion_price_usd", positive=True)
    fee_tier = _first_number(record, "reward_conversion_fee_tier")
    dec0 = _first_number(record, "reward_conversion_dec0")
    dec1 = _first_number(record, "reward_conversion_dec1")
    if None in (l_raw, price, fee_tier, dec0, dec1):
        return None, metadata
    side = str(record.get("reward_conversion_side") or "sell_base")
    if side not in {"buy_base", "sell_base"}:
        return None, metadata
    try:
        return exit_conversion_cost_usd(
            reward_ev_usd,
            l_raw,
            price,
            fee_tier,
            int(dec0),
            int(dec1),
            side,
        ), metadata
    except (ArithmeticError, ValueError):
        return None, metadata


def assemble_clmm_netcover_inputs(
    source: Mapping[str, Any],
    *,
    position_usd: float = M1_MIN_POSITION_USD,
    scanner_measured_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the CLMM vol-sized-range path; reject cross-model misuse."""
    record = dict(source)
    if str(record.get("protocol_type") or "").strip().lower() != PROTOCOL_TYPE_CLMM:
        raise ValueError("CLMM assembler requires protocol_type=clmm")
    # Caller-supplied route claims are untrusted and must not survive assembly.
    # Live evidence arrives only through the separate scanner-internal argument
    # after fixed-block RPC identity/state validation; a self-declared
    # ``complete`` field therefore cannot reopen the 518f8db evidence boundary.
    for key in (
        "reward_conversion_routes",
        "reward_conversion_route_costs",
        "reward_conversion_selected_route_id",
        "reward_conversion_route_selection_rule",
    ):
        record.pop(key, None)
    size = _number(position_usd, positive=True)
    if size is None:
        raise ValueError("position_usd must be finite and positive")
    horizon = holding_horizon_hours(record)
    fraction = horizon / HOURS_PER_YEAR if horizon is not None else None

    fee_24h = _first_number(record, "fee_apr_24h", "fee_apr_onchain")
    fee_7d = _first_number(record, "fee_apr_7d", "apyBase")
    age_is_established = record.get("is_new_pool") is False
    fee_haircut = ESTABLISHED_FEE_HAIRCUT if age_is_established else NEW_OR_AGE_UNKNOWN_FEE_HAIRCUT
    fee_evidence_apr = (
        min(fee_24h, fee_7d) if None not in (fee_24h, fee_7d) else None
    )
    fee_ev, fee_capture_metadata = _range_aware_fee_ev(
        record,
        size_usd=size,
        horizon_hours=horizon,
        fee_apr_pct=fee_evidence_apr,
        fee_haircut=fee_haircut,
        scanner_measured_evidence=scanner_measured_evidence,
    )

    reward_apr = _first_number(record, "reward_apr", "apyReward")
    category = reward_category(record) if reward_apr not in (None, 0.0) else None
    category_haircut = REWARD_HAIRCUTS.get(category) if category is not None else None
    persistence = reward_persistence_gate(record)
    persistence_haircut = float(persistence["score_factor"])
    haircut = (
        float(category_haircut) * persistence_haircut
        if category_haircut is not None else None
    )
    share_ratio = fee_capture_metadata["fee_capture_share_ratio"]
    # Slipstream gauge emissions, like fees, are distributed by in-range CL
    # liquidity weight.  Reward haircut remains an engine concern; this input
    # assembler applies only actual elapsed time and the shared range penalty.
    reward_ev = (
        size * reward_apr / 100.0 * fraction * share_ratio
        if reward_apr is not None
        and fraction is not None
        and share_ratio is not None
        and (reward_apr == 0.0 or category_haircut is not None)
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

    costs = _swap_costs(record, size, scanner_measured_evidence)
    chain = str(record.get("chain") or record.get("network") or "").strip().lower()
    gas = HISTORICAL_GAS_USD.get(chain)
    reward_conversion, reward_route_metadata = _reward_conversion_cost(
        record, reward_ev, category, scanner_measured_evidence
    )
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
        "protocol_type": PROTOCOL_TYPE_CLMM,
        "netcover_model_path": NETCOVER_MODEL_CLMM,
        "netcover_profile": profile_kind(record),
        "fee_apr_haircut": fee_haircut,
        "reward_category": category,
        "reward_category_haircut": category_haircut,
        "reward_persistence_haircut": persistence_haircut,
        "reward_persistence_evidence_source": persistence["evidence_source"],
        "reward_persistence_status": persistence["status"],
        "lvr_coefficient": LVR_COEFFICIENT_MODEL,
        "netcover_input_semantics": field_semantics,
        "gas_usd_source": HISTORICAL_GAS_SOURCES.get(chain),
        "netcover_input_position_source": "M1_MIN_POSITION_USD",
        "netcover_input_assembly_source": (
            "lp_netcover_inputs_v1_readonly:raw_evidence_calculated_only"
        ),
    })
    record.update(fee_capture_metadata)
    # INV-TVLSHARE-01: the coarse TVL tier is never final sizing.  Recompute
    # investable notional from this cycle's trusted active-L evidence, then
    # persist the cap and the separate 0.10% hard-ceiling verification.
    try:
        capital_tier = normalize_capital_tier(
            record.get("capital_tier") or DEFAULT_CAPITAL_TIER
        )
    except ValueError:
        capital_tier = None
    pool_tvl = _first_number(record, "tvlUsd", "tvl_usd", "tvl", positive=True)
    active_notional = _number(
        record.get("active_liquidity_notional_usd"), positive=True
    )
    tier_max = (
        CAPITAL_TIER_CONFIGURED_MAX_USD[capital_tier]
        if capital_tier is not None
        else None
    )
    cap = None
    hard_share = None
    hard_ok = False
    if None not in (tier_max, pool_tvl, active_notional):
        try:
            cap = position_cap_usd(tier_max, pool_tvl, active_notional)
            hard_share = cap / pool_tvl
            hard_ok = hard_share <= HARD_POSITION_TVL_SHARE
        except ValueError:
            cap = None
    cap_pass = bool(cap is not None and cap >= size and hard_ok)
    if cap is None:
        cap_reason = "INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"
    elif not hard_ok:
        cap_reason = "INV-TVLSHARE-01_HARD_TVL_SHARE_EXCEEDED"
    elif cap < size:
        cap_reason = "INV-TVLSHARE-01_POSITION_CAP_BELOW_M1_MIN"
    else:
        cap_reason = "PASS"
    record.update({
        "capital_tier": capital_tier,
        "tier_configured_max_usd": tier_max,
        "position_requested_usd": size,
        "position_investable_usd": min(size, cap) if cap is not None else None,
        "position_cap_usd": cap,
        "position_cap_tvl_share": hard_share,
        "position_cap_regular_tvl_share_limit": POSITION_TVL_SHARE,
        "position_cap_active_share_limit": ACTIVE_SHARE_LIMIT,
        "position_cap_hard_tvl_share_limit": HARD_POSITION_TVL_SHARE,
        "position_cap_hard_tvl_share_ok": hard_ok,
        "position_cap_pass": cap_pass,
        "position_cap_reason": cap_reason,
        "active_liquidity_notional_usd_source": (
            "measured:current_active_L_over_target_range"
            if active_notional is not None
            else None
        ),
    })
    record.update(reward_route_metadata)
    if scanner_measured_evidence:
        record["scanner_measured_cross_pool_evidence"] = dict(scanner_measured_evidence)
        if scanner_measured_evidence.get("token1_usd") is not None:
            record["measured_token1_usd"] = scanner_measured_evidence["token1_usd"]
            record["measured_token1_usd_source"] = scanner_measured_evidence.get(
                "token1_usd_source"
            )
    # A positive calculated reward EV always requires a classified category;
    # zero-reward records do not need to override WP-04's irrelevant default.
    if haircut is not None:
        # The engine remains the sole multiplication point.  This attached
        # value combines category reliability with persistence credibility;
        # conversion cost above intentionally remains based on gross reward EV.
        record["reward_haircut"] = haircut
    if all(record[field] is not None for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")):
        record["round_trip_cost_usd"] = (
            record["entry_cost_usd"] + record["exit_cost_usd"] + record["slippage_usd"]
        )
    else:
        record["round_trip_cost_usd"] = None

    reasons = list(record.get("permanent_fail_closed_reasons") or ())
    primary = record.get("permanent_fail_closed_reason") or (
        scanner_measured_evidence.get("permanent_fail_closed_reason")
        if scanner_measured_evidence else None
    )
    if primary and primary not in reasons:
        reasons.append(str(primary))
    token0 = str(record.get("token0") or "").lower()
    token1 = str(record.get("token1") or "").lower()
    if any(costs[field] is None for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")):
        if (
            token0
            and token1
            and token0 not in _stable_tokens(record)
            and token1 not in _stable_tokens(record)
            and _first_number(
                record, "last_swap_price_token1_per_token0", positive=True
            ) is not None
            and _first_number(
                record, "last_swap_liquidity_raw", "l_active_raw", positive=True
            ) is not None
        ):
            reasons.append("no_measured_usd_quote_route")
    if reward_ev not in (None, 0.0) and reward_conversion is None:
        reasons.append("reward_conversion_route_unavailable")
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        record["permanent_fail_closed_reasons"] = reasons
        record["permanent_fail_closed_reason"] = str(primary or reasons[0])
        if not record.get("permanent_fail_closed_r1a_classification"):
            if "no_measured_usd_quote_route" in reasons:
                record["permanent_fail_closed_r1a_classification"] = (
                    "NO_MEASURED_USD_QUOTE_AND_REWARD_CONVERSION_DEPTH"
                )
            elif "reward_conversion_route_unavailable" in reasons:
                record["permanent_fail_closed_r1a_classification"] = (
                    "MISSING_REWARD_CONVERSION_EVIDENCE"
                )
    return record


def _amm_swap_costs(
    *, size_usd: float, pool_tvl_usd: float | None, fee_tier: float | None
) -> dict[str, float | None]:
    """Conservative balanced-reserve v2 round-trip cost model in USD."""
    if pool_tvl_usd is None or fee_tier is None or not 0.0 <= fee_tier < 1.0:
        return {key: None for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}
    reserve_leg = pool_tvl_usd / 2.0
    if reserve_leg <= 0.0:
        return {key: None for key in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")}
    amount_after_fee = size_usd * (1.0 - fee_tier)
    amount_out = reserve_leg * amount_after_fee / (reserve_leg + amount_after_fee)
    one_way_slippage = max(amount_after_fee - amount_out, 0.0)
    return {
        "entry_cost_usd": size_usd * fee_tier,
        "exit_cost_usd": size_usd * fee_tier,
        "slippage_usd": 2.0 * one_way_slippage,
    }


def assemble_amm_netcover_inputs(
    source: Mapping[str, Any],
    *,
    position_usd: float = M1_MIN_POSITION_USD,
    scanner_measured_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble FIX-E2's full-range constant-product AMM model path.

    There is deliberately no range, out-of-range event, concentration uplift,
    or CLMM share-ratio term.  Fee APR is diluted only by adding this position
    to the whole-pool LP capital: ``pool_tvl / (pool_tvl + size)``.
    """
    record = dict(source)
    if (
        str(record.get("protocol_type") or "").strip().lower()
        != PROTOCOL_TYPE_AMM_CONSTANT_PRODUCT
    ):
        raise ValueError(
            "AMM assembler requires protocol_type=amm_constant_product"
        )
    for key in (
        "reward_conversion_routes",
        "reward_conversion_route_costs",
        "reward_conversion_selected_route_id",
        "reward_conversion_route_selection_rule",
    ):
        record.pop(key, None)

    size = _number(position_usd, positive=True)
    if size is None:
        raise ValueError("position_usd must be finite and positive")
    horizon = amm_holding_horizon_hours(record)
    fraction = horizon / HOURS_PER_YEAR if horizon is not None else None
    raw_horizon = _first_number(
        record, "holding_horizon_hours", "profile_horizon_hours", "er_horizon_hours",
        positive=True,
    )
    if raw_horizon is None:
        raw_days = _first_number(
            record, "holding_horizon_days", "profile_horizon_days", "er_horizon_days",
            positive=True,
        )
        raw_horizon = raw_days * 24.0 if raw_days is not None else None

    pool_tvl = _first_number(record, "tvlUsd", "tvl_usd", "tvl", positive=True)
    pool_tvl_source = str(
        record.get("tvl_usd_source")
        or record.get("tvlUsd_source")
        or "source_record:tvlUsd"
    )
    dilution = (
        pool_tvl / (pool_tvl + size) if pool_tvl is not None else None
    )
    fee_24h = _first_number(record, "fee_apr_24h", "fee_apr_onchain")
    fee_7d = _first_number(record, "fee_apr_7d", "apyBase")
    fee_apr = min(fee_24h, fee_7d) if None not in (fee_24h, fee_7d) else None
    fee_haircut = (
        ESTABLISHED_FEE_HAIRCUT
        if record.get("is_new_pool") is False
        else NEW_OR_AGE_UNKNOWN_FEE_HAIRCUT
    )
    fee_ev = (
        size * fee_apr / 100.0 * fee_haircut * fraction * dilution
        if None not in (fee_apr, fraction, dilution)
        else None
    )

    reward_apr = _first_number(record, "reward_apr", "apyReward")
    category = reward_category(record) if reward_apr not in (None, 0.0) else None
    category_haircut = REWARD_HAIRCUTS.get(category) if category is not None else None
    persistence = reward_persistence_gate(record)
    persistence_haircut = float(persistence["score_factor"])
    haircut = (
        float(category_haircut) * persistence_haircut
        if category_haircut is not None else None
    )
    reward_ev = (
        size * reward_apr / 100.0 * fraction * dilution
        if reward_apr is not None
        and fraction is not None
        and dilution is not None
        and (reward_apr == 0.0 or category_haircut is not None)
        else None
    )

    ratio = _amm_price_ratio(record)
    il_signed = None
    il_ev = None
    if ratio is not None and horizon is not None:
        try:
            il_signed = constant_product_il_fraction(ratio)
            il_ev = size * -il_signed
        except ValueError:
            il_signed = None
            il_ev = None

    fee_tier = _first_number(record, "fee_tier")
    costs = _amm_swap_costs(
        size_usd=size, pool_tvl_usd=pool_tvl, fee_tier=fee_tier
    )
    chain = str(record.get("chain") or record.get("network") or "").strip().lower()
    gas = HISTORICAL_GAS_USD.get(chain)
    reward_conversion, reward_route_metadata = _reward_conversion_cost(
        record, reward_ev, category, scanner_measured_evidence
    )
    exit_latency = (
        size * EXIT_LATENCY_LOSS_APR_PCT_MODEL / 100.0 * fraction
        if fraction is not None else None
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
    amm_sources = {
        "fee_ev_usd": "model_estimate:amm_fee_apr_horizon_whole_pool_dilution",
        "reward_ev_usd": "model_estimate:reward_apr_horizon_whole_pool_dilution",
        "il_ev_usd": "model_estimate:constant_product_analytic_il_from_measured_price_ratio",
        "entry_cost_usd": "model_estimate:constant_product_balanced_reserve_cost",
        "exit_cost_usd": "model_estimate:constant_product_balanced_reserve_cost",
        "slippage_usd": "model_estimate:constant_product_balanced_reserve_cost",
        "gas_usd": HISTORICAL_GAS_SOURCES.get(chain),
        "reward_conversion_cost_usd": INPUT_SOURCES["reward_conversion_cost_usd"],
        "exit_latency_loss_usd": INPUT_SOURCES["exit_latency_loss_usd"],
    }
    field_semantics: dict[str, str | None] = {}
    for field in NETCOVER_INPUT_FIELDS:
        value = calculated[field]
        record[field] = value
        semantics = INPUT_SEMANTICS[field] if value is not None else None
        record[f"{field}_semantics"] = semantics
        record[f"{field}_source"] = amm_sources[field] if value is not None else None
        field_semantics[field] = semantics

    tier_raw = record.get("capital_tier") or DEFAULT_CAPITAL_TIER
    try:
        capital_tier = normalize_capital_tier(tier_raw)
    except ValueError:
        capital_tier = None
    tier_max = (
        CAPITAL_TIER_CONFIGURED_MAX_USD[capital_tier]
        if capital_tier is not None else None
    )
    cap = None
    hard_share = None
    if None not in (tier_max, pool_tvl):
        try:
            cap = position_cap_usd(float(tier_max), float(pool_tvl), float(pool_tvl))
            hard_share = cap / float(pool_tvl)
        except ValueError:
            cap = None
    hard_ok = bool(hard_share is not None and hard_share <= HARD_POSITION_TVL_SHARE)
    cap_pass = bool(cap is not None and cap >= size and hard_ok)
    if cap is None:
        cap_reason = "INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"
    elif not hard_ok:
        cap_reason = "INV-TVLSHARE-01_HARD_TVL_SHARE_EXCEEDED"
    elif cap < size:
        cap_reason = "INV-TVLSHARE-01_POSITION_CAP_BELOW_M1_MIN"
    else:
        cap_reason = "PASS"

    record.update({
        "capital_usd": size,
        "holding_horizon_hours": horizon,
        "amm_holding_horizon_max_hours": AMM_HOLDING_HORIZON_MAX_HOURS,
        "amm_horizon_cap_reason": (
            "PASS"
            if horizon is not None
            else (
                "AMM_HORIZON_EXCEEDS_720H"
                if raw_horizon is not None and raw_horizon > AMM_HOLDING_HORIZON_MAX_HOURS
                else "AMM_HORIZON_MISSING_OR_INVALID"
            )
        ),
        "protocol_type": PROTOCOL_TYPE_AMM_CONSTANT_PRODUCT,
        "netcover_model_path": NETCOVER_MODEL_AMM_CONSTANT_PRODUCT,
        "netcover_profile": "AMM_FULL_RANGE",
        "amm_no_range_model": True,
        "amm_price_ratio": ratio,
        "amm_il_fraction_signed": il_signed,
        "amm_position_dilution_factor": dilution,
        "fee_apr_haircut": fee_haircut,
        "fee_capture_reference_horizon_hours": None,
        "fee_capture_reference_range_pct": None,
        "fee_capture_target_range_pct": None,
        "fee_capture_reference_share": None,
        "fee_capture_target_share": None,
        "fee_capture_share_ratio": None,
        "active_liquidity_notional_usd": pool_tvl,
        "active_liquidity_notional_usd_source": (
            f"amm_whole_pool_tvl:{pool_tvl_source}" if pool_tvl is not None else None
        ),
        "reward_category": category,
        "reward_category_haircut": category_haircut,
        "reward_persistence_haircut": persistence_haircut,
        "reward_persistence_evidence_source": persistence["evidence_source"],
        "reward_persistence_status": persistence["status"],
        "lvr_coefficient": LVR_COEFFICIENT_MODEL,
        "netcover_input_semantics": field_semantics,
        "gas_usd_source": HISTORICAL_GAS_SOURCES.get(chain),
        "netcover_input_position_source": "M1_MIN_POSITION_USD",
        "netcover_input_assembly_source": (
            "lp_netcover_inputs_v1_readonly:amm_constant_product_explicit_evidence"
        ),
        "capital_tier": capital_tier,
        "tier_configured_max_usd": tier_max,
        "position_requested_usd": size,
        "position_investable_usd": min(size, cap) if cap is not None else None,
        "position_cap_usd": cap,
        "position_cap_tvl_share": hard_share,
        "position_cap_regular_tvl_share_limit": POSITION_TVL_SHARE,
        "position_cap_active_share_limit": ACTIVE_SHARE_LIMIT,
        "position_cap_hard_tvl_share_limit": HARD_POSITION_TVL_SHARE,
        "position_cap_hard_tvl_share_ok": hard_ok,
        "position_cap_pass": cap_pass,
        "position_cap_reason": cap_reason,
    })
    record.update(reward_route_metadata)
    if haircut is not None:
        record["reward_haircut"] = haircut
    if all(costs[field] is not None for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")):
        record["round_trip_cost_usd"] = sum(
            float(costs[field])
            for field in ("entry_cost_usd", "exit_cost_usd", "slippage_usd")
        )
    else:
        record["round_trip_cost_usd"] = None

    reasons = list(record.get("permanent_fail_closed_reasons") or ())
    if horizon is None:
        reasons.append(str(record["amm_horizon_cap_reason"]))
    if ratio is None:
        reasons.append("AMM_MEASURED_PRICE_RATIO_MISSING")
    if pool_tvl is None:
        reasons.append("AMM_POOL_TVL_MISSING")
    if reward_ev not in (None, 0.0) and reward_conversion is None:
        reasons.append("reward_conversion_route_unavailable")
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        record["permanent_fail_closed_reasons"] = reasons
        record["permanent_fail_closed_reason"] = reasons[0]
    return record


def _invalid_protocol_record(source: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(source)
    for field in NETCOVER_INPUT_FIELDS:
        record[field] = None
        record[f"{field}_semantics"] = None
        record[f"{field}_source"] = None
    record.update({
        "netcover_model_path": None,
        "netcover_input_semantics": {field: None for field in NETCOVER_INPUT_FIELDS},
        "permanent_fail_closed_reason": "NETCOVER_PROTOCOL_TYPE_INVALID",
        "permanent_fail_closed_reasons": ["NETCOVER_PROTOCOL_TYPE_INVALID"],
    })
    return record


def assemble_netcover_inputs(
    source: Mapping[str, Any],
    *,
    position_usd: float = M1_MIN_POSITION_USD,
    scanner_measured_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch exclusively by explicit ``protocol_type``; unknown is closed."""
    protocol_type = str(source.get("protocol_type") or "").strip().lower()
    if protocol_type == PROTOCOL_TYPE_CLMM:
        return assemble_clmm_netcover_inputs(
            source,
            position_usd=position_usd,
            scanner_measured_evidence=scanner_measured_evidence,
        )
    if protocol_type == PROTOCOL_TYPE_AMM_CONSTANT_PRODUCT:
        return assemble_amm_netcover_inputs(
            source,
            position_usd=position_usd,
            scanner_measured_evidence=scanner_measured_evidence,
        )
    return _invalid_protocol_record(source)


def assemble_records(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [assemble_netcover_inputs(record) for record in records]
