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

SELECTOR_GET_POOL_UNISWAP = "0x1698ee82"
SELECTOR_GET_POOL_AERODROME = "0x28af8d0b"
SELECTOR_DECIMALS = "0x313ce567"
SELECTOR_TOKEN0 = "0x0dfe1681"
SELECTOR_TOKEN1 = "0xd21220a7"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DEFAULT_CALL_PACE_SECS = 0.15
BASE_BLOCKS_PER_DAY = 43200.0


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


def resolve_pool_address(
    rpc_with_retry: Any,
    project: str,
    token_a: str,
    token_b: str,
    fee_or_spacing: int,
    cache: MutableMapping[Tuple[str, str, str, int], str],
) -> str:
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

    range_pct = live["recommend_range_pct"](sigma_daily, 14)
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

        pool = resolve_pool_address(
            live["_rpc_with_retry"],
            project,
            token_a,
            token_b,
            fee_or_spacing,
            caches["pool"],
        )
        if pool == ZERO_ADDRESS:
            record["resolve_status"] = "NOT_FOUND"
            record["status"] = "NOT_FOUND"
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

        start_block = max(current_block - int(window_blocks), 0)
        swaps = _fetch_swaps_for_window(
            live["fetch_pool_swaps"], pool, start_block, current_block, dec0, dec1
        )
        swap_count = len(swaps)
        record["swap_count"] = swap_count

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
