#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Mapping, Sequence
REPO_ROOT = "/opt/lpbot/lp-bot-v3-origin-check"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID  # noqa: E402
Q96 = 1 << 96
FEE_SCALE = 1_000_000
MIN_TICK = -887272
MAX_TICK = 887272
MIN_SQRT_RATIO = 4295128739
MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342
REQUIRED_POOL_KEYS = ("sqrt_price_x96", "current_tick", "tick_spacing",
                      "fee_pips", "liquidity")
@dataclass(frozen=True)
class TickRange:
    tick_lower: int
    tick_upper: int
    liquidity_net: int
_TICK_CONSTANTS = tuple(int(x, 16) for x in (
    "fffcb933bd6fad37aa2d162d1a594001 fff97272373d413259a46990580e213a "
    "fff2e50f5f656932ef12357cf3c7fdcc ffe5caca7e10e4e61c3624eaa0941cd0 "
    "ffcb9843d60f6159c9db58835c926644 ff973b41fa98c081472e6896dfb254c0 "
    "ff2ea16466c96a3843ec78b326b52861 fe5dee046a99a2a811c461f1969c3053 "
    "fcbe86c7900a88aedcffc83b479aa3a4 f987a7253ac413176f2b074cf7815e54 "
    "f3392b0822b70005940c7a398e4b70f3 e7159475a2c29b7443b29c7fa6e889d9 "
    "d097f3bdfd2022b8845ad8f792aa5825 a9f746462d870fdf8a65dc1f90e061e5 "
    "70d869a156d2a1b890bb3df62baf32f7 31be135f97d08fd981231505542fcfa6 "
    "9aa508b5b7a84e1c677de54f3e99bc9 5d6af8dedb81196699c329225ee604 "
    "2216e584f5fa1ea926041bedfe98 48a170391f7dc42444e8fa2").split())
def sqrt_price_x96_at_tick(tick: int) -> int:
    if not MIN_TICK <= tick <= MAX_TICK:
        raise ValueError("tick outside Uniswap V3 bounds")
    ratio = 1 << 128
    a = abs(tick)
    if a & 1:
        ratio = _TICK_CONSTANTS[0]
    for bit in range(1, len(_TICK_CONSTANTS)):
        if a & (1 << bit):
            ratio = (ratio * _TICK_CONSTANTS[bit]) >> 128
    if tick > 0:
        ratio = ((1 << 256) - 1) // ratio
    return (ratio >> 32) + bool(ratio & ((1 << 32) - 1))
def tick_at_sqrt_price_x96(sqrt_price_x96: int) -> int:
    if sqrt_price_x96 < MIN_SQRT_RATIO or sqrt_price_x96 > MAX_SQRT_RATIO:
        raise ValueError("sqrt price outside Uniswap V3 bounds")
    lo, hi = MIN_TICK, MAX_TICK + 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if sqrt_price_x96_at_tick(mid) <= sqrt_price_x96:
            lo = mid
        else:
            hi = mid
    return lo
def _check_delta_inputs(a: int, b: int, liquidity: int) -> None:
    if a <= 0 or b <= 0 or a > b or liquidity < 0:
        raise ValueError("invalid delta inputs")
def amount0_delta(a: int, b: int, liquidity: int, round_up: bool) -> int:
    _check_delta_inputs(a, b, liquidity)
    n, d = liquidity * (b - a) * Q96, a * b
    return (n + d - 1) // d if round_up else n // d
def amount1_delta(a: int, b: int, liquidity: int, round_up: bool) -> int:
    _check_delta_inputs(a, b, liquidity)
    n = liquidity * (b - a)
    return (n + Q96 - 1) // Q96 if round_up else n // Q96
def _coerce_ticks(tick_data: Sequence[TickRange]) -> list[TickRange]:
    out = []
    for item in tick_data:
        if isinstance(item, TickRange):
            out.append(item)
        elif isinstance(item, Mapping):
            out.append(TickRange(int(item["tick_lower"]),
                                 int(item["tick_upper"]),
                                 int(item["liquidity_net"])))
        else:
            raise TypeError("tick_data entries must be TickRange or mappings")
    return out
def _tick_events(tick_data: Sequence[TickRange]) -> tuple[dict[int, int], bool]:
    events: dict[int, int] = {}
    has_range = False
    for row in _coerce_ticks(tick_data):
        if row.tick_lower > row.tick_upper:
            raise ValueError("tick_lower must not exceed tick_upper")
        if row.tick_lower == row.tick_upper:
            events[row.tick_lower] = events.get(row.tick_lower, 0) + row.liquidity_net
        else:
            has_range = True
            events[row.tick_lower] = events.get(row.tick_lower, 0) + row.liquidity_net
            events[row.tick_upper] = events.get(row.tick_upper, 0) - row.liquidity_net
    return events, has_range
def _next_sqrt_price(current: int, liquidity: int, amount: int,
                     zero_for_one: bool) -> int:
    if amount <= 0 or liquidity <= 0:
        return current
    if zero_for_one:
        numerator = liquidity * Q96 * current
        return (numerator + liquidity * Q96 + amount * current - 1) // (liquidity * Q96 + amount * current)
    return current + (amount * Q96) // liquidity
def _price_impact(sqrt_price: int, amount_in: int, amount_out: int,
                  fee_paid: int, zero_for_one: bool) -> tuple[Decimal, Decimal]:
    net_in = amount_in - fee_paid
    if net_in <= 0 or amount_out <= 0:
        return Decimal(0), Decimal("10000")
    with localcontext() as ctx:
        ctx.prec = 80
        effective = Decimal(amount_out) / Decimal(net_in)
        raw_price = (Decimal(sqrt_price) / Decimal(Q96)) ** 2
        spot = raw_price if zero_for_one else Decimal(1) / raw_price
        impact = (spot - effective) / spot * Decimal(10000)
    return effective, max(Decimal(0), impact)
def simulate_exit_swap(*, sqrt_price_x96: int, current_tick: int,
                       tick_spacing: int, fee_pips: int, liquidity: int,
                       tick_data: Sequence[TickRange], amount_in: int,
                       zero_for_one: bool) -> dict:
    if amount_in < 0 or liquidity < 0 or tick_spacing <= 0:
        raise ValueError("invalid swap inputs")
    if not 0 <= fee_pips < FEE_SCALE:
        raise ValueError("fee_pips must be below 1,000,000")
    if sqrt_price_x96 <= 0:
        raise ValueError("sqrt price must be positive")
    rows = _coerce_ticks(tick_data)
    events, has_range = _tick_events(rows)
    if rows and not has_range and not any(t.tick_lower == current_tick for t in rows):
        has_context = bool(events)
    else:
        has_context = any(t.tick_lower <= current_tick <= t.tick_upper for t in rows)
    current = int(sqrt_price_x96)
    active = int(liquidity)
    remaining = int(amount_in)
    output = 0
    fee_paid = 0
    crossed = 0
    exhausted = False
    while remaining > 0:
        candidates = []
        for tick in events:
            boundary = sqrt_price_x96_at_tick(tick)
            if zero_for_one and boundary <= current:
                candidates.append((boundary, tick))
            elif not zero_for_one and boundary > current:
                candidates.append((boundary, tick))
        if not candidates or not has_context or active <= 0:
            exhausted = True
            break
        target, boundary_tick = (max(candidates) if zero_for_one else min(candidates))
        if target == current:
            change = events.pop(boundary_tick)
            active = active - change if zero_for_one else active + change
            crossed += 1
            continue
        net_available = remaining * (FEE_SCALE - fee_pips) // FEE_SCALE
        if net_available <= 0:
            fee_paid += remaining
            remaining = 0
            break
        needed = (amount0_delta(target, current, active, True)
                  if zero_for_one else amount1_delta(current, target, active, True))
        if net_available >= needed:
            net_used = needed
            gross_fee = (((net_used * fee_pips + FEE_SCALE - fee_pips - 1)
                          // (FEE_SCALE - fee_pips))
                         if fee_pips else 0)
            gross_used = net_used + gross_fee
            if gross_used > remaining:
                gross_used = remaining
                net_used = remaining - (remaining * fee_pips // FEE_SCALE)
                gross_fee = remaining - net_used
            next_price = target
        else:
            net_used = net_available
            gross_used = remaining
            gross_fee = remaining - net_used
            next_price = _next_sqrt_price(current, active, net_used, zero_for_one)
        if zero_for_one:
            output += amount1_delta(next_price, current, active, False)
        else:
            output += amount0_delta(current, next_price, active, False)
        remaining -= gross_used
        fee_paid += gross_fee
        current = next_price
        if next_price == target:
            change = events.pop(boundary_tick)
            active = active - change if zero_for_one else active + change
            crossed += 1
    if remaining > 0:
        exhausted = True
    effective, impact = _price_impact(sqrt_price_x96, amount_in, output,
                                      fee_paid, zero_for_one)
    return {"amount_out": output, "sqrt_price_after": current,
            "tick_after": tick_at_sqrt_price_x96(current),
            "ticks_crossed": crossed, "liquidity_exhausted": exhausted,
            "effective_price": effective, "price_impact_bps": impact,
            "fee_paid": fee_paid}
def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    return value if isinstance(value, Decimal) else Decimal(str(value))
def _state_factors(pool_state: Mapping[str, Any], zero_for_one: bool):
    """Return (input_price, input_decimals), or None when either is not
    explicitly provided. No lenient defaults: a missing price or decimals
    must surface as PRICE_OR_DECIMALS, never as Decimal(1) / 0."""
    sqrt_price = int(pool_state["sqrt_price_x96"])
    dec0 = pool_state.get("token0_decimals", pool_state.get("decimals0"))
    dec1 = pool_state.get("token1_decimals", pool_state.get("decimals1"))
    p0 = _decimal(pool_state.get("token0_price_usd"))
    p1 = _decimal(pool_state.get("token1_price_usd"))
    explicit = _decimal(pool_state.get("input_price_usd"))
    if explicit is None and p0 is None and p1 is None:
        return None
    if zero_for_one:
        if dec0 is None:
            return None
        input_decimals = int(dec0)
    else:
        if dec1 is None:
            return None
        input_decimals = int(dec1)
    if explicit is not None:
        return explicit, input_decimals
    if zero_for_one:
        if p0 is not None:
            return p0, input_decimals
        if dec1 is None:
            return None
        with localcontext() as ctx:
            ctx.prec = 80
            raw01 = (Decimal(sqrt_price) / Decimal(Q96)) ** 2
            human01 = raw01 * (Decimal(10) ** int(dec0)) / (Decimal(10) ** int(dec1))
            return p1 * human01, input_decimals
    if p1 is not None:
        return p1, input_decimals
    if dec0 is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        raw01 = (Decimal(sqrt_price) / Decimal(Q96)) ** 2
        human01 = raw01 * (Decimal(10) ** int(dec0)) / (Decimal(10) ** int(dec1))
        return p0 / human01, input_decimals
def _unavailable() -> dict:
    return {"max_exit_usd": None, "impact_at_size_bps": None,
            "sufficient": False, "reason": "INPUTS_UNAVAILABLE: EXIT_QUOTE"}
def _missing_keys(pool_state: Mapping[str, Any]) -> list[str]:
    return sorted(k for k in REQUIRED_POOL_KEYS if k not in pool_state)
def _missing_keys_result(missing: list[str]) -> dict:
    return {"max_exit_usd": None, "impact_at_size_bps": None,
            "sufficient": False, "reason": "INPUTS_UNAVAILABLE: MISSING_KEYS",
            "missing_keys": missing}
def _price_or_decimals_unavailable() -> dict:
    return {"max_exit_usd": None, "impact_at_size_bps": None,
            "sufficient": False,
            "reason": "INPUTS_UNAVAILABLE: PRICE_OR_DECIMALS"}
def _misspelled_direction_key(pool_state: Mapping[str, Any]) -> str | None:
    """Return a pool_state key that looks like a misspelled `zero_for_one`.

    RH-02av: a misspelled direction key must surface as
    INPUTS_UNAVAILABLE, never be silently swallowed into **pool_state and
    read back as the default direction.
    """
    for key in pool_state:
        if key == "zero_for_one":
            continue
        normalized = str(key).lower().replace("_", "").replace("-", "")
        if normalized in ("zeroforone", "zerofor1"):
            return key
    return None
def exit_depth_for_size(*, position_value_usd: Decimal,
                        max_impact_bps: Decimal, **pool_state) -> dict:
    misspelled = _misspelled_direction_key(pool_state)
    if misspelled is not None:
        return {"max_exit_usd": None, "impact_at_size_bps": None,
                "sufficient": False,
                "reason": (f"INPUTS_UNAVAILABLE: MISPELLED_DIRECTION_KEY: "
                           f"{misspelled} (expected zero_for_one)")}
    ticks = pool_state.get("tick_data")
    if not ticks:
        return _unavailable()
    missing = _missing_keys(pool_state)
    if missing:
        return _missing_keys_result(missing)
    try:
        position = _decimal(position_value_usd)
        impact_limit = _decimal(max_impact_bps)
        if position is None or impact_limit is None or position <= 0 or impact_limit < 0:
            return _unavailable()
        zero_for_one = bool(pool_state.get("zero_for_one", True))
        # RH-02av: mark whether the direction came from the caller or from
        # the default, so a defaulted direction is visible, not silent.
        direction_source = ("explicit" if "zero_for_one" in pool_state
                            else "defaulted")
        factors = _state_factors(pool_state, zero_for_one)
        if factors is None:
            return _price_or_decimals_unavailable()
        input_price, input_decimals = factors
        if input_price <= 0:
            return _price_or_decimals_unavailable()
        with localcontext() as ctx:
            ctx.prec = 80
            scale = Decimal(10) ** input_decimals
            target_raw = int((position * scale / input_price).to_integral_value(rounding="ROUND_FLOOR"))
        if target_raw <= 0:
            return _unavailable()
        def quote(raw_amount: int) -> dict:
            return simulate_exit_swap(
                sqrt_price_x96=int(pool_state["sqrt_price_x96"]),
                current_tick=int(pool_state["current_tick"]),
                tick_spacing=int(pool_state["tick_spacing"]),
                fee_pips=int(pool_state["fee_pips"]),
                liquidity=int(pool_state["liquidity"]),
                tick_data=ticks, amount_in=raw_amount,
                zero_for_one=zero_for_one)
        full = quote(target_raw)
        if full["liquidity_exhausted"]:
            # The pool cannot absorb the full size: a computed answer, not a
            # missing input. Binary-search the largest exitable amount.
            lo, hi = 0, target_raw
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                if quote(mid)["liquidity_exhausted"]:
                    hi = mid
                else:
                    lo = mid
            max_exitable = lo
            if max_exitable > 0:
                chosen = quote(max_exitable)
                with localcontext() as ctx:
                    ctx.prec = 80
                    max_usd = Decimal(max_exitable) * input_price / scale
                impact = chosen["price_impact_bps"]
            else:
                max_usd = Decimal(0)
                impact = None
            return {"max_exit_usd": max_usd,
                    "impact_at_size_bps": impact,
                    "sufficient": False,
                    "reason": "COMPUTED_FAIL: LIQUIDITY_EXHAUSTED",
                    "direction_source": direction_source}
        if full["price_impact_bps"] <= impact_limit:
            return {"max_exit_usd": position,
                    "impact_at_size_bps": full["price_impact_bps"],
                    "sufficient": True, "reason": "EXIT_DEPTH_OK",
                    "direction_source": direction_source}
        lo, hi = 0, target_raw
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            trial = quote(mid)
            if (not trial["liquidity_exhausted"]
                    and trial["price_impact_bps"] <= impact_limit):
                lo = mid
            else:
                hi = mid
        chosen = quote(lo) if lo else {"price_impact_bps": Decimal(0)}
        with localcontext() as ctx:
            ctx.prec = 80
            max_usd = Decimal(lo) * input_price / scale
        return {"max_exit_usd": max_usd,
                "impact_at_size_bps": chosen["price_impact_bps"],
                "sufficient": max_usd >= position,
                "reason": "EXIT_DEPTH_OK" if max_usd >= position
                else "EXIT_DEPTH_INSUFFICIENT",
                "direction_source": direction_source}
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return _unavailable()
def measured_exit_depth_cap(position_value_usd: Decimal | None = None,
                            max_impact_bps: Decimal = Decimal("100"),
                            **pool_state) -> Decimal | None:
    """Return a measured cap, or None whenever a quote cannot be proven."""
    if not pool_state.get("tick_data"):
        return None
    if _missing_keys(pool_state):
        return None
    amount = position_value_usd or pool_state.pop("position_value_usd", None)
    if amount is None:
        amount = Decimal("1e18")
    result = exit_depth_for_size(position_value_usd=_decimal(amount),
                                 max_impact_bps=_decimal(max_impact_bps),
                                 **pool_state)
    return result["max_exit_usd"] if result["max_exit_usd"] is not None else None
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-state-json", required=True)
    parser.add_argument("--position-usd", required=True)
    parser.add_argument("--max-impact-bps", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raw = json.loads(Path(args.pool_state_json).read_text())
    state = raw.get("pool_state", raw)
    result = exit_depth_for_size(
        position_value_usd=Decimal(args.position_usd),
        max_impact_bps=Decimal(args.max_impact_bps), **state)
    Path(args.out).write_text(json.dumps(result, indent=2, default=str) + "\n")
if __name__ == "__main__":
    main()
