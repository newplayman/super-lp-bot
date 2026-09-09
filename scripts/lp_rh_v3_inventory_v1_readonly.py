"""Decimal-precise initial inventory for a Uniswap V3 range position."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext


@dataclass(frozen=True)
class V3Inventory:
    amount0_raw: Decimal
    amount1_raw: Decimal
    liquidity_raw: Decimal
    reconstructed_usd: Decimal
    amount0_human: Decimal
    amount1_human: Decimal


def _decimal(value, name):
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite Decimal-compatible value") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite")
    return number


def _decimal_places(value, name):
    number = _decimal(value, name)
    if number < 0 or number != number.to_integral_value():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(number)


def inventory_for_position(
    *,
    position_usd,
    entry_price,
    range_pct,
    dec0,
    dec1,
    quote_usd_per_token1=None,
):
    """Return the two legs a V3 range position actually holds at open."""

    if quote_usd_per_token1 is None:
        raise ValueError("quote_usd_per_token1 must be provided")

    position = _decimal(position_usd, "position_usd")
    price = _decimal(entry_price, "entry_price")
    width = _decimal(range_pct, "range_pct")
    quote = _decimal(quote_usd_per_token1, "quote_usd_per_token1")
    decimals0 = _decimal_places(dec0, "dec0")
    decimals1 = _decimal_places(dec1, "dec1")

    if position <= 0:
        raise ValueError("position_usd must be > 0")
    if price <= 0:
        raise ValueError("entry_price must be > 0")
    if width <= 0:
        raise ValueError("range_pct must be > 0")
    if width >= 100:
        raise ValueError("range_pct must be < 100")
    if quote <= 0:
        raise ValueError("quote_usd_per_token1 must be > 0")

    with localcontext() as ctx:
        ctx.prec = 60
        one = Decimal(1)
        hundred = Decimal(100)

        sqrt_p = price.sqrt()
        sqrt_pa = (price * (one - width / hundred)).sqrt()
        sqrt_pb = (price * (one + width / hundred)).sqrt()

        amount0_per_liquidity = (sqrt_pb - sqrt_p) / (sqrt_p * sqrt_pb)
        amount1_per_liquidity = sqrt_p - sqrt_pa

        unit_value = (
            amount0_per_liquidity * price + amount1_per_liquidity
        ) * quote
        if unit_value <= 0:
            raise ValueError("range produces non-positive unit value")

        liquidity_human = position / unit_value
        amount0_human = liquidity_human * amount0_per_liquidity
        amount1_human = liquidity_human * amount1_per_liquidity

        scale0 = Decimal(10) ** decimals0
        scale1 = Decimal(10) ** decimals1
        amount0_raw = amount0_human * scale0
        amount1_raw = amount1_human * scale1
        liquidity_raw = liquidity_human * (scale0 * scale1).sqrt()
        reconstructed_usd = (
            amount0_human * price + amount1_human
        ) * quote

        return V3Inventory(
            amount0_raw=amount0_raw,
            amount1_raw=amount1_raw,
            liquidity_raw=liquidity_raw,
            reconstructed_usd=reconstructed_usd,
            amount0_human=amount0_human,
            amount1_human=amount1_human,
        )


@dataclass(frozen=True)
class V3PositionValue:
    value_usd: Decimal
    amount0_human: Decimal
    amount1_human: Decimal


def position_value_at(
    *,
    price,
    liquidity_human,
    entry_price,
    range_pct,
    quote_usd_per_token1,
):
    """Mark a v3 range position to market at ``price``."""

    if quote_usd_per_token1 is None:
        raise ValueError("quote_usd_per_token1 must be provided")

    current_price = _decimal(price, "price")
    liquidity = _decimal(liquidity_human, "liquidity_human")
    entry = _decimal(entry_price, "entry_price")
    width = _decimal(range_pct, "range_pct")
    quote = _decimal(quote_usd_per_token1, "quote_usd_per_token1")

    if current_price <= 0:
        raise ValueError("price must be > 0")
    if liquidity <= 0:
        raise ValueError("liquidity_human must be > 0")
    if entry <= 0:
        raise ValueError("entry_price must be > 0")
    if width <= 0:
        raise ValueError("range_pct must be > 0")
    if width >= 100:
        raise ValueError("range_pct must be < 100")
    if quote <= 0:
        raise ValueError("quote_usd_per_token1 must be > 0")

    with localcontext() as ctx:
        ctx.prec = 80
        one = Decimal(1)
        hundred = Decimal(100)

        lower = entry * (one - width / hundred)
        upper = entry * (one + width / hundred)
        sqrt_pa = lower.sqrt()
        sqrt_pb = upper.sqrt()
        sqrt_p = current_price.sqrt()

        if current_price <= lower:
            amount0_human = (
                liquidity * (sqrt_pb - sqrt_pa)
                / (sqrt_pa * sqrt_pb)
            )
            amount1_human = Decimal(0)
        elif current_price >= upper:
            amount0_human = Decimal(0)
            amount1_human = liquidity * (sqrt_pb - sqrt_pa)
        else:
            amount0_human = (
                liquidity * (sqrt_pb - sqrt_p)
                / (sqrt_p * sqrt_pb)
            )
            amount1_human = liquidity * (sqrt_p - sqrt_pa)

        value_usd = (
            amount0_human * current_price + amount1_human
        ) * quote

        return V3PositionValue(
            value_usd=value_usd,
            amount0_human=amount0_human,
            amount1_human=amount1_human,
        )
