from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

UNISWAP_V3_FACTORY = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
AERODROME_SLIPSTREAM_FACTORY = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"
AERODROME_SLIPSTREAM_FACTORIES = (
    {"label": "initial", "factory": AERODROME_SLIPSTREAM_FACTORY},
    {"label": "gauge_caps", "factory": "0xaDe65c38CD4849aDBA595a4323a8C7DdfE89716a"},
    {"label": "gauges_v3", "factory": "0xf8f2eB4940CFE7d13603DDDD87f123820Fc061Ef"},
)
AERODROME_FACTORY_REGISTRY_SOURCE = (
    "official:https://github.com/aerodrome-finance/slipstream#deployments"
)

SELECTOR_GET_POOL_UNISWAP = "0x1698ee82"
SELECTOR_GET_POOL_AERODROME = "0x28af8d0b"
SELECTOR_DECIMALS = "0x313ce567"
SELECTOR_TOKEN0 = "0x0dfe1681"
SELECTOR_TOKEN1 = "0xd21220a7"
SELECTOR_TICK_SPACING = "0xd0c93a7c"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DEFAULT_CALL_PACE_SECS = 0.15
BASE_BLOCKS_PER_DAY = 43200.0


class PoolResolutionError(RuntimeError):
    reason = "pool_resolution_failed"


class PoolResolutionIncompleteError(PoolResolutionError):
    reason = "factory_registry_probe_incomplete"


class AmbiguousMultiFactoryPoolError(PoolResolutionError):
    reason = "ambiguous_multi_factory_pool"

    def __init__(self, valid_candidates: Sequence[Mapping[str, Any]]):
        self.valid_candidates = [dict(item) for item in valid_candidates]
        self.valid_pool_addresses = sorted({str(item["pool"]) for item in valid_candidates})
        super().__init__(
            f"{self.reason}: distinct validated pools={','.join(self.valid_pool_addresses)}"
        )


class ObservedRangeDomainError(ValueError):
    reason = "observed_range_gte_100"

    def __init__(self, evidence: Mapping[str, float | None], *, reason: str | None = None):
        self.evidence = dict(evidence)
        if reason is not None:
            self.reason = reason
        super().__init__(f"{self.reason}: {json.dumps(self.evidence, sort_keys=True)}")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return default
    return default


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_address(address: str) -> str:
    if not isinstance(address, str):
        raise TypeError("address must be a hex string")
    text = address.strip()
    if not text.startswith("0x"):
        raise ValueError(f"address missing 0x prefix: {address!r}")
    hex_part = text[2:]
    if len(hex_part) != 40:
        raise ValueError(f"address must be 20 bytes: {address!r}")
    int(hex_part, 16)
    return "0x" + hex_part.lower()


def encode_address_word(address: str) -> str:
    addr = normalize_address(address)[2:]
    return "0x" + addr.rjust(64, "0")


def encode_uint_word(value: int) -> str:
    if value < 0:
        raise ValueError("uint cannot be negative")
    return "0x" + format(value, "x").rjust(64, "0")


def encode_int_word(value: int, bits: int = 24) -> str:
    """ABI-encode a signed integer into a 32-byte word (sign-extended)."""
    if bits <= 0:
        raise ValueError("bits must be positive")
    min_value = -(1 << (bits - 1))
    max_value = (1 << (bits - 1)) - 1
    if value < min_value or value > max_value:
        raise ValueError(f"value {value} out of range for int{bits}")
    # Sign-extend to 256 bits (ABI encoding for negative ints fills with 0xff)
    if value < 0:
        value = value & ((1 << 256) - 1)
    return "0x" + format(value, "x").rjust(64, "0")


def _join_calldata(selector: str, *words: str) -> str:
    return selector + "".join(word[2:] for word in words)


def build_uniswap_get_pool_calldata(token_a: str, token_b: str, fee: int) -> str:
    return _join_calldata(
        SELECTOR_GET_POOL_UNISWAP,
        encode_address_word(token_a),
        encode_address_word(token_b),
        encode_uint_word(fee),
    )


def build_aerodrome_get_pool_calldata(token_a: str, token_b: str, tick_spacing: int) -> str:
    return _join_calldata(
        SELECTOR_GET_POOL_AERODROME,
        encode_address_word(token_a),
        encode_address_word(token_b),
        encode_int_word(tick_spacing, bits=24),
    )


def decode_address_word(data: str) -> str:
    text = data[2:] if data.startswith("0x") else data
    if len(text) < 64:
        raise ValueError(f"cannot decode address from short word: {data!r}")
    return normalize_address("0x" + text[-40:])


def decode_uint_word(data: str) -> int:
    text = data[2:] if data.startswith("0x") else data
    if not text:
        return 0
    return int(text, 16)


def reward_adjusted_cover(
    fees_quote: float,
    il_quote: float,
    apy_reward: Optional[float],
    window_days: float,
) -> Dict[str, float]:
    fees = float(fees_quote or 0.0)
    il_abs = abs(float(il_quote or 0.0))
    reward_apr = float(apy_reward or 0.0)
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    annualizer = 365.0 / window_days
    fee_apr = fees * 100.0 * annualizer
    total_income_apr = fee_apr + reward_apr
    il_apr = il_abs * 100.0 * annualizer
    yield_cover = math.inf if il_apr == 0 else total_income_apr / il_apr
    return {
        "fee_apr": fee_apr,
        "reward_apr": reward_apr,
        "total_income_apr": total_income_apr,
        "il_apr": il_apr,
        "yield_cover": yield_cover,
    }


def composite_score(rec: Mapping[str, Any]) -> float:
    if rec.get("wash_flag"):
        return 0.0
    status = rec.get("status")
    resolve_status = rec.get("resolve_status")
    if status not in (None, "OK"):
        return 0.0
    if resolve_status not in (None, "OK"):
        return 0.0

    total_income_apr_raw = float(_safe_float(rec.get("total_income_apr"), 0.0) or 0.0)
    il_apr = abs(float(_safe_float(rec.get("il_apr"), 0.0) or 0.0))
    tier = str(rec.get("tier") or "").upper()
    reserve = 3.0 if tier in {"B", "C"} else 1.0

    total_income_apr = min(total_income_apr_raw, 2000.0)
    net_apr_est = total_income_apr - il_apr - reserve

    # Saturate the score so capped incentive farms do not dominate durable pools.
    score = max(min(net_apr_est, 100.0), -100.0)
    if total_income_apr_raw > 2000.0:
        score *= 0.75

    suspects = _coerce_list(rec.get("suspect"))
    if suspects:
        score *= 0.2

    yield_cover = rec.get("yield_cover", math.inf)
    try:
        yield_cover_value = float(yield_cover)
    except (TypeError, ValueError):
        yield_cover_value = math.inf
    if yield_cover_value < 1.0:
        score *= 0.3

    return score


def _project_key(project: str) -> str:
    text = (project or "").strip().lower()
    if text == "uniswap-v3":
        return text
    if text == "aerodrome-slipstream":
        return text
    raise ValueError(f"unsupported project: {project!r}")


def _selector_and_factory(project: str) -> Tuple[str, str]:
    key = _project_key(project)
    if key == "uniswap-v3":
        return SELECTOR_GET_POOL_UNISWAP, normalize_address(UNISWAP_V3_FACTORY)
    return SELECTOR_GET_POOL_AERODROME, normalize_address(AERODROME_SLIPSTREAM_FACTORY)


def _call_pace_secs() -> float:
    value = _safe_float(os.environ.get("CALL_PACE_SECS"), DEFAULT_CALL_PACE_SECS)
    return DEFAULT_CALL_PACE_SECS if value is None else max(value, 0.0)


def _load_live_helpers() -> Dict[str, Any]:
    from scripts.lp_tier_b_level2_replay_v1_readonly import replay
    from scripts.lp_tier_c_exit_feasibility_v1_readonly import _rpc_with_retry, fetch_pool_swaps
    from scripts.lp_tier_range_policy_v1_readonly import fee_cover_ratio
    from scripts.lp_vol_range_sizer_v1_readonly import (
        daily_vol_from_closes,
        hourly_closes,
        recommend_range_pct,
    )

    return {
        "_rpc_with_retry": _rpc_with_retry,
        "fetch_pool_swaps": fetch_pool_swaps,
        "hourly_closes": hourly_closes,
        "daily_vol_from_closes": daily_vol_from_closes,
        "recommend_range_pct": recommend_range_pct,
        "replay": replay,
        "fee_cover_ratio": fee_cover_ratio,
    }


def _eth_call_hex(rpc_with_retry: Any, to_address: str, data: str) -> str:
    time.sleep(_call_pace_secs())
    result = rpc_with_retry(
        "eth_call",
        [{"to": normalize_address(to_address), "data": data}, "latest"],
    )
    if not isinstance(result, str) or not result.startswith("0x"):
        raise ValueError(f"unexpected eth_call result: {result!r}")
    return result


def _eth_block_number(rpc_with_retry: Any) -> int:
    result = rpc_with_retry("eth_blockNumber", [])
    if not isinstance(result, str) or not result.startswith("0x"):
        raise ValueError(f"unexpected eth_blockNumber result: {result!r}")
    return int(result, 16)


def _resolve_pool_once(
    rpc_with_retry: Any,
    project: str,
    token_a: str,
    token_b: str,
    fee_or_spacing: int,
    cache: MutableMapping[Tuple[str, str, str, int], str],
) -> str:
    selector, factory = _selector_and_factory(project)
    key = (factory, normalize_address(token_a), normalize_address(token_b), int(fee_or_spacing))
    if key in cache:
        return cache[key]

    if selector == SELECTOR_GET_POOL_UNISWAP:
        calldata = build_uniswap_get_pool_calldata(token_a, token_b, int(fee_or_spacing))
    else:
        calldata = build_aerodrome_get_pool_calldata(token_a, token_b, int(fee_or_spacing))

    result = _eth_call_hex(rpc_with_retry, factory, calldata)
    pool = decode_address_word(result)
    cache[key] = pool
    return pool


def _resolve_pool_at_factory(
    rpc_with_retry: Any,
    factory: str,
    token_a: str,
    token_b: str,
    tick_spacing: int,
    cache: MutableMapping[Tuple[str, str, str, int], str],
) -> List[str]:
    normalized_factory = normalize_address(factory)
    left = normalize_address(token_a)
    right = normalize_address(token_b)
    key = (normalized_factory, left, right, int(tick_spacing))
    if key not in cache:
        raw = _eth_call_hex(
            rpc_with_retry,
            normalized_factory,
            build_aerodrome_get_pool_calldata(left, right, int(tick_spacing)),
        )
        cache[key] = decode_address_word(raw)
    reverse_key = (normalized_factory, right, left, int(tick_spacing))
    if reverse_key not in cache:
        raw = _eth_call_hex(
            rpc_with_retry,
            normalized_factory,
            build_aerodrome_get_pool_calldata(right, left, int(tick_spacing)),
        )
        cache[reverse_key] = decode_address_word(raw)
    return sorted({
        pool for pool in (cache[key], cache[reverse_key]) if pool != ZERO_ADDRESS
    })


def _validate_aerodrome_candidate(
    rpc_with_retry: Any,
    pool: str,
    token_a: str,
    token_b: str,
    tick_spacing: int,
) -> Dict[str, Any]:
    """Validate contract identity before a factory result can enter the funnel."""
    normalized_pool = normalize_address(pool)
    code = rpc_with_retry("eth_getCode", [normalized_pool, "latest"])
    if not isinstance(code, str) or code.lower() in {"0x", "0x0", "0x00"}:
        return {"valid": False, "validation_reason": "missing_contract_bytecode"}
    token0 = decode_address_word(_eth_call_hex(rpc_with_retry, normalized_pool, SELECTOR_TOKEN0))
    token1 = decode_address_word(_eth_call_hex(rpc_with_retry, normalized_pool, SELECTOR_TOKEN1))
    actual_tokens = sorted((token0, token1))
    expected_tokens = sorted((normalize_address(token_a), normalize_address(token_b)))
    if actual_tokens != expected_tokens:
        return {
            "valid": False,
            "validation_reason": "token_pair_mismatch",
            "actual_tokens": actual_tokens,
        }
    decoded_tick = decode_uint_word(
        _eth_call_hex(rpc_with_retry, normalized_pool, SELECTOR_TICK_SPACING)
    )
    if decoded_tick != int(tick_spacing):
        return {
            "valid": False,
            "validation_reason": "tick_spacing_mismatch",
            "actual_tick_spacing": decoded_tick,
        }
    decimals = []
    for token in (token0, token1):
        value = decode_uint_word(_eth_call_hex(rpc_with_retry, token, SELECTOR_DECIMALS))
        if value < 0 or value > 36:
            return {
                "valid": False,
                "validation_reason": "token_decimals_out_of_range",
                "token": token,
                "decimals": value,
            }
        decimals.append(value)
    return {
        "valid": True,
        "token0": token0,
        "token1": token1,
        "dec0": decimals[0],
        "dec1": decimals[1],
        "validated_token_set": expected_tokens,
        "validated_tick_spacing": decoded_tick,
        "contract_code_bytes": (len(code) - 2) // 2,
    }


def resolve_pool_with_provenance(
    rpc_with_retry: Any,
    project: str,
    token_a: str,
    token_b: str,
    fee_or_spacing: int,
    cache: MutableMapping[Tuple[str, str, str, int], str],
) -> Dict[str, Any]:
    """Resolve only after exhaustive factory probing and identity validation.

    A partial registry view is never interpreted as uniqueness.  Repeated
    returns of the same canonical pool address are de-duplicated while every
    factory provenance entry is retained.
    """
    key = _project_key(project)
    if key == "uniswap-v3":
        pool = resolve_pool_address(
            rpc_with_retry, project, token_a, token_b, fee_or_spacing, cache
        )
        return {
            "pool": pool,
            "factory": normalize_address(UNISWAP_V3_FACTORY),
            "factory_label": "uniswap_v3_base",
            "factory_labels": ["uniswap_v3_base"],
            "factory_registry_source": "configured:uniswap_v3_base_factory",
        }

    observations: Dict[str, Dict[str, Any]] = {}
    probe_errors: List[Dict[str, str]] = []
    for item in AERODROME_SLIPSTREAM_FACTORIES:
        label = str(item["label"])
        factory = normalize_address(str(item["factory"]))
        try:
            pools = _resolve_pool_at_factory(
                rpc_with_retry, factory, token_a, token_b, fee_or_spacing, cache
            )
        except Exception as exc:
            probe_errors.append({
                "factory_label": label,
                "factory": factory,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        for pool in pools:
            canonical = normalize_address(pool)
            observation = observations.setdefault(
                canonical, {"pool": canonical, "factory_labels": [], "factories": []}
            )
            if label not in observation["factory_labels"]:
                observation["factory_labels"].append(label)
            if factory not in observation["factories"]:
                observation["factories"].append(factory)

    validations: List[Dict[str, Any]] = []
    for observation in observations.values():
        try:
            validation = _validate_aerodrome_candidate(
                rpc_with_retry,
                observation["pool"],
                token_a,
                token_b,
                fee_or_spacing,
            )
        except Exception as exc:
            probe_errors.append({
                "factory_label": ",".join(observation["factory_labels"]),
                "factory": ",".join(observation["factories"]),
                "error": f"candidate_validation:{type(exc).__name__}: {exc}",
            })
            continue
        validations.append({**observation, **validation})

    # Any UNKNOWN means other valid candidates may exist, so uniqueness has not
    # been proven and no partial answer may be used.
    if probe_errors:
        error = PoolResolutionIncompleteError(
            f"factory_registry_probe_incomplete: {json.dumps(probe_errors, sort_keys=True)}"
        )
        error.probe_errors = probe_errors
        raise error
    valid = [item for item in validations if item.get("valid")]
    if len(valid) > 1:
        raise AmbiguousMultiFactoryPoolError(valid)
    if not valid:
        invalid = [item for item in validations if not item.get("valid")]
        return {
            "pool": ZERO_ADDRESS,
            "factory": None,
            "factory_label": None,
            "factory_labels": [],
            "factory_registry_source": AERODROME_FACTORY_REGISTRY_SOURCE,
            "validation_failures": invalid,
            "not_found_reason": (
                "non_standard_pool_contract"
                if invalid else "pool_not_found_in_supported_factory"
            ),
        }
    selected = dict(valid[0])
    selected["factory"] = selected["factories"][0]
    selected["factory_label"] = selected["factory_labels"][0]
    selected["factory_registry_source"] = AERODROME_FACTORY_REGISTRY_SOURCE
    return selected


def resolve_pool_address(
    rpc_with_retry: Any,
    project: str,
    token_a: str,
    token_b: str,
    fee_or_spacing: int,
    cache: MutableMapping[Tuple[str, str, str, int], str],
) -> str:
    # Compatibility helper used by the standalone Uniswap resolver path.  The
    # production candidate path uses ``resolve_pool_with_provenance`` so all
    # Aerodrome factories are exhausted and validated before selection.
    pool = _resolve_pool_once(rpc_with_retry, project, token_a, token_b, fee_or_spacing, cache)
    if pool != ZERO_ADDRESS:
        return pool
    return _resolve_pool_once(rpc_with_retry, project, token_b, token_a, fee_or_spacing, cache)


def _read_pool_token_order_and_decimals(
    rpc_with_retry: Any,
    pool: str,
    decimals_cache: MutableMapping[str, int],
) -> Tuple[str, str, int, int]:
    token0 = decode_address_word(_eth_call_hex(rpc_with_retry, pool, SELECTOR_TOKEN0))
    token1 = decode_address_word(_eth_call_hex(rpc_with_retry, pool, SELECTOR_TOKEN1))

    def read_decimals(token: str) -> int:
        token = normalize_address(token)
        if token not in decimals_cache:
            decimals_cache[token] = decode_uint_word(_eth_call_hex(rpc_with_retry, token, SELECTOR_DECIMALS))
        return decimals_cache[token]

    dec0 = read_decimals(token0)
    dec1 = read_decimals(token1)
    return token0, token1, dec0, dec1


def _call_helper(func: Any, kwargs: Mapping[str, Any], positional_fallbacks: Sequence[Tuple[Any, ...]] = ()) -> Any:
    last_error: Optional[Exception] = None
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        try:
            return func(**kwargs)
        except TypeError as exc:
            last_error = exc
    else:
        params = signature.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            filtered = dict(kwargs)
        else:
            filtered = {k: v for k, v in kwargs.items() if k in params}
        if filtered:
            try:
                return func(**filtered)
            except TypeError as exc:
                last_error = exc

    for args in positional_fallbacks:
        try:
            return func(*args)
        except TypeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return func()


def _extract_swap_amount1(swap: Any) -> float:
    if isinstance(swap, Mapping):
        if "amount1" in swap:
            return float(_safe_float(swap.get("amount1"), 0.0) or 0.0)
        args = swap.get("args")
        if isinstance(args, Mapping) and "amount1" in args:
            return float(_safe_float(args.get("amount1"), 0.0) or 0.0)
    return 0.0


def latest_swap_cost_state(swaps: Sequence[Any]) -> Dict[str, Any]:
    """Return measured terminal price/liquidity without substituting pool TVL.

    ``fetch_pool_swaps`` already decodes both values from the Swap event.  W6
    carries them forward so NetCover can use depth evidence without another
    source or a TVL-as-liquidity approximation.  Invalid/absent evidence stays
    ``None`` and therefore fails closed downstream.
    """
    for swap in reversed(swaps):
        if not isinstance(swap, Mapping):
            continue
        args = swap.get("args") if isinstance(swap.get("args"), Mapping) else swap
        price = _safe_float(
            args.get("price", args.get("price_token1_per_token0")), None
        )
        liquidity = _safe_int(
            args.get("liquidity", args.get("active_liquidity_raw")), None
        )
        if price is None or price <= 0 or liquidity is None or liquidity <= 0:
            continue
        return {
            "last_swap_price_token1_per_token0": float(price),
            "last_swap_liquidity_raw": int(liquidity),
            "last_swap_cost_state_source": "measured:latest_decoded_swap_event",
        }
    return {
        "last_swap_price_token1_per_token0": None,
        "last_swap_liquidity_raw": None,
        "last_swap_cost_state_source": None,
    }


def _extract_replay_metrics(result: Any) -> Tuple[float, float]:
    if isinstance(result, Mapping):
        fees_quote = _safe_float(
            result.get("fees_quote", result.get("fees", result.get("fees_q"))),
            0.0,
        )
        il_quote = _safe_float(
            result.get("il_quote", result.get("il", result.get("impermanent_loss_quote"))),
            0.0,
        )
        return float(fees_quote or 0.0), float(il_quote or 0.0)
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return float(_safe_float(result[0], 0.0) or 0.0), float(_safe_float(result[1], 0.0) or 0.0)
    return 0.0, 0.0


def _fetch_swaps_for_window(
    fetch_pool_swaps: Any, pool: str, start_block: int, end_block: int, dec0: int, dec1: int
) -> List[Any]:
    # Verified signature: fetch_pool_swaps(pool, from_block, to_block, dec0, dec1)
    result = fetch_pool_swaps(pool, start_block, end_block, dec0, dec1)
    return list(result or [])


def _measure_range_and_replay(
    live: Mapping[str, Any], swaps: Sequence[Any], fee_tier: float, dec0: int, dec1: int
) -> Tuple[Optional[float], float, float]:
    if not swaps:
        return None, 0.0, 0.0

    # Verified signatures (see scripts/lp_vol_range_sizer + lp_tier_b_level2_replay):
    #   hourly_closes(swaps) -> [(idx, price)]
    #   daily_vol_from_closes(closes) -> (sigma_daily|None, n_returns)
    #   recommend_range_pct(sigma_daily, horizon_days, k=1.2) -> pct
    #   replay(swaps, *, range_pct, fee_tier, dec0, dec1, mode, ...) -> dict
    closes = live["hourly_closes"](swaps)
    sigma_daily, _n = live["daily_vol_from_closes"](closes)
    if sigma_daily is None:
        return None, 0.0, 0.0

    horizon_days = 14.0
    range_pct = _safe_float(live["recommend_range_pct"](sigma_daily, horizon_days), None)
    entry_price = _safe_float(
        swaps[0].get("price") if isinstance(swaps[0], Mapping) else None,
        None,
    )
    lower_bound = (
        entry_price * (1.0 - range_pct / 100.0)
        if entry_price is not None and range_pct is not None
        else None
    )
    evidence = {
        "measured_sigma_daily": float(sigma_daily),
        "measured_horizon_days": horizon_days,
        "measured_range_pct": range_pct,
        "measured_entry_price_token1_per_token0": entry_price,
        "measured_lower_bound_token1_per_token0": lower_bound,
    }
    if range_pct is None or not math.isfinite(range_pct):
        raise ObservedRangeDomainError(evidence, reason="observed_range_non_finite")
    if entry_price is None or entry_price <= 0.0:
        raise ObservedRangeDomainError(evidence, reason="observed_entry_price_invalid")
    if range_pct >= 100.0 or lower_bound is None or lower_bound <= 0.0:
        raise ObservedRangeDomainError(evidence)
    replay_result = live["replay"](
        swaps,
        range_pct=range_pct,
        fee_tier=float(fee_tier),
        dec0=int(dec0),
        dec1=int(dec1),
        mode="passive",
    )
    fees_quote, il_quote = _extract_replay_metrics(replay_result)
    return float(_safe_float(range_pct, 0.0) or 0.0), fees_quote, il_quote


def process_candidate(
    candidate: Mapping[str, Any],
    window_blocks: int,
    current_block: int,
    caches: MutableMapping[str, MutableMapping[Any, Any]],
    live: Mapping[str, Any],
) -> Dict[str, Any]:
    record: Dict[str, Any] = dict(candidate)
    record["resolve_status"] = "PENDING"
    record["status"] = "PENDING"
    record["resolved_pool"] = None
    record["pool"] = None
    record["wash_flag"] = False
    record["vol_onchain_per_day"] = None
    record["swap_count"] = 0
    record["fee_cover"] = None
    record["range_pct"] = None
    record["fee_apr_onchain"] = None
    record["reward_apr"] = float(_safe_float(candidate.get("apyReward"), 0.0) or 0.0)
    record["total_income_apr"] = None
    record["il_apr"] = None
    record["yield_cover"] = None
    record["composite_score"] = 0.0

    try:
        project = _project_key(str(candidate.get("project") or ""))
        tokens = _coerce_list(candidate.get("underlyingTokens"))
        if len(tokens) != 2:
            raise ValueError("underlyingTokens must contain exactly two addresses")

        token_a = normalize_address(tokens[0])
        token_b = normalize_address(tokens[1])

        fee_fraction = _safe_float(candidate.get("fee_tier"))
        if project == "uniswap-v3":
            # getPool fee arg is in hundredths-of-a-bip (uint24): 0.0005 -> 500.
            if fee_fraction is None:
                raise ValueError("fee_tier is required for uniswap-v3")
            fee_or_spacing = int(round(fee_fraction * 1_000_000))
        else:
            fee_or_spacing = _safe_int(candidate.get("tick_spacing"))
            if fee_or_spacing is None:
                raise ValueError("tick_spacing is required for aerodrome-slipstream")

        resolution = resolve_pool_with_provenance(
            live["_rpc_with_retry"],
            project,
            token_a,
            token_b,
            fee_or_spacing,
            caches["pool"],
        )
        pool = str(resolution["pool"])
        if pool == ZERO_ADDRESS:
            record["resolve_status"] = "NOT_FOUND"
            record["status"] = "NOT_FOUND"
            record["permanent_fail_closed_reason"] = resolution.get(
                "not_found_reason", "pool_not_found_in_supported_factory"
            )
            record["permanent_fail_closed_r1a_classification"] = (
                "POOL_NOT_IN_SUPPORTED_FACTORY"
            )
            record["factory_registry_source"] = resolution.get("factory_registry_source")
            record["pool_validation_failures"] = resolution.get("validation_failures", [])
            return finalize_record(record)

        token0, token1, dec0, dec1 = _read_pool_token_order_and_decimals(
            live["_rpc_with_retry"],
            pool,
            caches["decimals"],
        )

        record["resolved_pool"] = pool
        record["pool"] = pool
        record["token0"] = token0
        record["token1"] = token1
        record["dec0"] = dec0
        record["dec1"] = dec1
        record["resolve_status"] = "OK"
        record["resolved_factory"] = resolution.get("factory")
        record["resolved_factory_label"] = resolution.get("factory_label")
        record["resolved_factory_labels"] = resolution.get("factory_labels")
        record["factory_registry_source"] = resolution.get("factory_registry_source")
        record["pool_identity_validation"] = {
            "validated_token_set": resolution.get("validated_token_set"),
            "validated_tick_spacing": resolution.get("validated_tick_spacing"),
            "contract_code_bytes": resolution.get("contract_code_bytes"),
        }

        start_block = max(current_block - int(window_blocks), 0)
        swaps = _fetch_swaps_for_window(
            live["fetch_pool_swaps"], pool, start_block, current_block, dec0, dec1
        )
        swap_count = len(swaps)
        record["swap_count"] = swap_count
        record.update(latest_swap_cost_state(swaps))
        if swap_count == 0:
            record["status"] = "INSUFFICIENT_DATA"
            record["permanent_fail_closed_reason"] = "no_swaps_in_window"
            record["permanent_fail_closed_r1a_classification"] = "NO_SWAPS_IN_WINDOW"
            return finalize_record(record)

        window_days = float(window_blocks) / BASE_BLOCKS_PER_DAY
        amount1_sum = sum(abs(_extract_swap_amount1(swap)) for swap in swaps)
        vol_onchain_per_day = (amount1_sum / (10 ** dec1)) / window_days if window_days > 0 else 0.0
        record["vol_onchain_per_day"] = vol_onchain_per_day

        reported_volume = _safe_float(candidate.get("volumeUsd1d"))
        wash_flag = False
        if reported_volume is not None and reported_volume >= 10000.0:
            if swap_count == 0:
                wash_flag = True
            elif swap_count <= 1 and vol_onchain_per_day <= 1e-9:
                wash_flag = True
        record["wash_flag"] = wash_flag

        range_pct, fees_quote, il_quote = _measure_range_and_replay(
            live, swaps, fee_fraction or 0.0, dec0, dec1
        )
        record["range_pct"] = range_pct
        if range_pct is None:
            record["status"] = "INSUFFICIENT_DATA"
            record["permanent_fail_closed_reason"] = "insufficient_price_observations"
            record["permanent_fail_closed_r1a_classification"] = (
                "INSUFFICIENT_PRICE_OBSERVATIONS"
            )
            return finalize_record(record)

        fee_cover = live["fee_cover_ratio"](fees_quote, il_quote)
        record["fee_cover"] = fee_cover if fee_cover != math.inf else "inf"

        cover = reward_adjusted_cover(
            fees_quote=fees_quote,
            il_quote=il_quote,
            apy_reward=_safe_float(candidate.get("apyReward"), 0.0),
            window_days=window_days,
        )
        record["fee_apr_onchain"] = cover["fee_apr"]
        record["reward_apr"] = cover["reward_apr"]
        record["total_income_apr"] = cover["total_income_apr"]
        record["il_apr"] = cover["il_apr"]
        record["yield_cover"] = cover["yield_cover"]

        record["status"] = "OK"
        return finalize_record(record)
    except AmbiguousMultiFactoryPoolError as exc:
        record["resolve_status"] = "AMBIGUOUS"
        record["status"] = "FAIL_CLOSED"
        record["permanent_fail_closed_reason"] = exc.reason
        record["permanent_fail_closed_r1a_classification"] = (
            "MULTI_FACTORY_POOL_AMBIGUITY"
        )
        record["validated_pool_candidates"] = exc.valid_candidates
        record["error"] = str(exc)
        return finalize_record(record)
    except PoolResolutionIncompleteError as exc:
        record["resolve_status"] = "UNKNOWN"
        record["status"] = "FAIL_CLOSED"
        record["permanent_fail_closed_reason"] = exc.reason
        record["permanent_fail_closed_r1a_classification"] = (
            "FACTORY_REGISTRY_PROBE_INCOMPLETE"
        )
        record["factory_probe_errors"] = getattr(exc, "probe_errors", [])
        record["error"] = str(exc)
        return finalize_record(record)
    except ObservedRangeDomainError as exc:
        record["status"] = "FAIL_CLOSED"
        record["permanent_fail_closed_reason"] = exc.reason
        record["permanent_fail_closed_r1a_classification"] = (
            "OBSERVED_RANGE_EXCEEDS_MATH_DOMAIN"
        )
        record.update(exc.evidence)
        record["range_pct"] = exc.evidence.get("measured_range_pct")
        record["error"] = str(exc)
        return finalize_record(record)
    except Exception as exc:
        record["status"] = "ERROR"
        record["error"] = str(exc)
        return finalize_record(record)


def finalize_record(record: MutableMapping[str, Any]) -> Dict[str, Any]:
    record["composite_score"] = composite_score(record)
    return dict(record)


def _markdown_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.4f}"
    return str(value)


def render_markdown(records: Sequence[Mapping[str, Any]]) -> str:
    headers = [
        "symbol",
        "project",
        "resolved_pool",
        "dec0",
        "dec1",
        "fee_tier",
        "tier",
        "apyReward",
        "fee_apr_onchain",
        "yield_cover",
        "wash_flag",
        "composite_score",
        "status",
    ]
    lines = [
        "# LP Pool Resolve And Rank",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for rec in records:
        row = [_markdown_value(rec.get(col)) for col in headers]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)


def build_policy_config(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    config: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get("resolve_status") != "OK":
            continue
        if rec.get("status") != "OK":
            continue
        if rec.get("wash_flag"):
            continue
        pool = rec.get("resolved_pool") or rec.get("pool")
        if not pool:
            continue
        config.append(
            {
                "pool": pool,
                "dec0": rec.get("dec0"),
                "dec1": rec.get("dec1"),
                "fee_tier": rec.get("fee_tier"),
                "tier_hint": rec.get("tier"),
                "label": f"{rec.get('symbol', '?')} | {rec.get('project', '?')}",
            }
        )
    return config


def _ensure_out_dir(path_arg: Optional[str]) -> Path:
    if path_arg:
        out_dir = Path(path_arg)
    else:
        out_dir = REPO_ROOT / "reports" / "lp_pool_resolve_and_rank" / _utc_stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _read_candidates(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("candidates JSON must be a list")
    return [dict(item) for item in data]


def run_self_test() -> int:
    addr = "0x1234567890abcdef1234567890ABCDEF12345678"
    assert encode_address_word(addr) == "0x" + "0" * 24 + "1234567890abcdef1234567890abcdef12345678"
    assert encode_int_word(60, bits=24).endswith("3c".rjust(64, "0"))
    assert encode_int_word(-1, bits=24) == "0x" + "f" * 64

    uni = build_uniswap_get_pool_calldata(addr, ZERO_ADDRESS, 500)
    aero = build_aerodrome_get_pool_calldata(addr, ZERO_ADDRESS, 60)
    assert uni.startswith(SELECTOR_GET_POOL_UNISWAP)
    assert aero.startswith(SELECTOR_GET_POOL_AERODROME)
    assert len(uni) == 2 + 8 + 64 * 3
    assert len(aero) == 2 + 8 + 64 * 3

    cover = reward_adjusted_cover(0.01, -0.02, 12.0, 2.0)
    assert cover["fee_apr"] > 0
    assert cover["reward_apr"] == 12.0
    assert cover["yield_cover"] > 0

    zero_il = reward_adjusted_cover(0.01, 0.0, 0.0, 1.0)
    assert math.isinf(zero_il["yield_cover"])

    clean = {
        "status": "OK",
        "resolve_status": "OK",
        "tier": "A",
        "suspect": [],
        "wash_flag": False,
        "total_income_apr": 90.0,
        "il_apr": 10.0,
        "yield_cover": 9.0,
    }
    suspect = dict(clean, suspect=["low-liquidity"])
    wash = dict(clean, wash_flag=True)
    weak = dict(clean, total_income_apr=40.0, il_apr=80.0, yield_cover=0.5)
    extreme = dict(clean, total_income_apr=150000.0, il_apr=10.0, yield_cover=500.0)

    assert composite_score(clean) > composite_score(suspect)
    assert composite_score(wash) == 0.0
    assert composite_score(clean) > composite_score(weak)
    assert composite_score(extreme) <= composite_score(clean)

    print("self-test ok")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve LP pools on chain and rank them for range policy.")
    parser.add_argument("--candidates", help="Path to stage2_candidates.json")
    parser.add_argument("--window-blocks", type=int, default=86400, help="On-chain measurement window in blocks")
    parser.add_argument("--out", help="Output directory")
    parser.add_argument("--self-test", action="store_true", help="Run pure self-tests without network")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.candidates:
        parser.error("--candidates is required unless --self-test is set")

    live = _load_live_helpers()
    candidates = _read_candidates(args.candidates)
    current_block = _eth_block_number(live["_rpc_with_retry"])
    caches: Dict[str, MutableMapping[Any, Any]] = {
        "pool": {},
        "decimals": {},
    }

    records = [
        process_candidate(candidate, args.window_blocks, current_block, caches, live)
        for candidate in candidates
    ]
    records.sort(key=lambda rec: rec.get("composite_score", 0.0), reverse=True)

    out_dir = _ensure_out_dir(args.out)
    (out_dir / "resolve_and_rank.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    (out_dir / "resolve_and_rank.md").write_text(render_markdown(records))
    (out_dir / "policy_config.json").write_text(
        json.dumps(build_policy_config(records), indent=2, sort_keys=True) + "\n"
    )

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
