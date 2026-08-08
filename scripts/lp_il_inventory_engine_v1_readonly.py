#!/usr/bin/env python3
"""Pure, read-only Uniswap-V3 inventory and IL accounting.

Price convention
----------------
``price`` and range bounds are human-unit token1 per token0.  Therefore an
inventory ``(q0, q1)`` has quote-token NAV ``q0 * price + q1``.  The generic
HODL helper accepts USD marks ``p0`` and ``p1`` for the two tokens instead.

The LP NAV entry point deliberately has only ``(state, price)`` parameters.
It values the position principal implied by liquidity and its range; fees,
rewards, swap costs and cash balances are outside this function.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


def _finite(value: float, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{name} must be > 0")
    if nonnegative and number < 0:
        raise ValueError(f"{name} must be >= 0")
    return number


@dataclass(frozen=True)
class EntryBaseline:
    """Immutable post-entry-swap, pre-mint token quantities.

    ``entry_swap_cost`` is stored solely for transaction-cost attribution.  It
    never changes HODL NAV or LP principal NAV.
    """

    q0_entry: float
    q1_entry: float
    entry_swap_cost: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "q0_entry", _finite(self.q0_entry, "q0_entry", nonnegative=True))
        object.__setattr__(self, "q1_entry", _finite(self.q1_entry, "q1_entry", nonnegative=True))
        object.__setattr__(
            self, "entry_swap_cost", _finite(self.entry_swap_cost, "entry_swap_cost", nonnegative=True)
        )


@dataclass(frozen=True)
class V3PositionState:
    """Principal-only V3 position inputs; no fee/reward fields by design."""

    liquidity: float
    price_lower: float
    price_upper: float

    def __post_init__(self) -> None:
        liquidity = _finite(self.liquidity, "liquidity", positive=True)
        lower = _finite(self.price_lower, "price_lower", positive=True)
        upper = _finite(self.price_upper, "price_upper", positive=True)
        if lower >= upper:
            raise ValueError("price_lower must be < price_upper")
        object.__setattr__(self, "liquidity", liquidity)
        object.__setattr__(self, "price_lower", lower)
        object.__setattr__(self, "price_upper", upper)


@dataclass(frozen=True)
class LPInventory:
    """Current token quantities and quote-token principal NAV."""

    q0: float
    q1: float
    nav_quote: float


def entry_baseline(q0_entry: float, q1_entry: float, entry_swap_cost: float = 0.0) -> EntryBaseline:
    """Create the immutable actual entry basket after ratio swap, before mint."""

    return EntryBaseline(q0_entry, q1_entry, entry_swap_cost)


def _bounds(entry_price: float, range_pct: float) -> tuple[float, float]:
    price = _finite(entry_price, "entry_price", positive=True)
    width = _finite(range_pct, "range_pct", positive=True)
    if width >= 100.0:
        raise ValueError("range_pct must be < 100")
    return price * (1.0 - width / 100.0), price * (1.0 + width / 100.0)


def _liquidity_for_capital(entry_price: float, capital: float, range_pct: float) -> float:
    price = _finite(entry_price, "entry_price", positive=True)
    notional = _finite(capital, "capital", positive=True)
    lower, upper = _bounds(price, range_pct)
    sqrt_p, sqrt_a, sqrt_b = math.sqrt(price), math.sqrt(lower), math.sqrt(upper)
    value_per_liquidity = price * (1.0 / sqrt_p - 1.0 / sqrt_b) + (sqrt_p - sqrt_a)
    if value_per_liquidity <= 0.0:
        raise ValueError("range produces non-positive entry value per liquidity")
    return notional / value_per_liquidity


def position_state_from_capital(entry_price: float, capital: float, range_pct: float) -> V3PositionState:
    """Construct principal-only V3 range/liquidity for a paper entry."""

    lower, upper = _bounds(entry_price, range_pct)
    return V3PositionState(_liquidity_for_capital(entry_price, capital, range_pct), lower, upper)


def paper_entry_baseline(
    entry_price: float,
    capital: float,
    range_pct: float,
    entry_swap_cost: float = 0.0,
) -> EntryBaseline:
    """Derive actual V3 entry legs for a quote-denominated paper notional.

    This uses the range's V3 amounts at ``entry_price``.  In particular it does
    not impose a synthetic 50/50 split; an arithmetically symmetric price range
    is not symmetric in square-root-price liquidity space.
    """

    position = position_state_from_capital(entry_price, capital, range_pct)
    inventory = current_inventory(position, entry_price)
    return entry_baseline(inventory.q0, inventory.q1, entry_swap_cost)


def hodl_nav(baseline: EntryBaseline, p0: float, p1: float) -> float:
    """USD NAV of the immutable entry basket at current per-token USD marks."""

    if not isinstance(baseline, EntryBaseline):
        raise TypeError("baseline must be EntryBaseline")
    price0 = _finite(p0, "p0", nonnegative=True)
    price1 = _finite(p1, "p1", nonnegative=True)
    return baseline.q0_entry * price0 + baseline.q1_entry * price1


def _state_values(state: V3PositionState | Mapping[str, float]) -> tuple[float, float, float]:
    if isinstance(state, V3PositionState):
        return state.liquidity, state.price_lower, state.price_upper
    if not isinstance(state, Mapping):
        raise TypeError("state must be V3PositionState or a mapping")
    try:
        validated = V3PositionState(
            liquidity=state["liquidity"],
            price_lower=state["price_lower"],
            price_upper=state["price_upper"],
        )
    except KeyError as exc:
        raise ValueError(f"missing principal state field: {exc.args[0]}") from exc
    return validated.liquidity, validated.price_lower, validated.price_upper


def current_inventory(state: V3PositionState | Mapping[str, float], price: float) -> LPInventory:
    """Return V3 principal inventory at the current token1/token0 price."""

    liquidity, lower, upper = _state_values(state)
    current = _finite(price, "price", positive=True)
    sqrt_a, sqrt_b = math.sqrt(lower), math.sqrt(upper)
    if current <= lower:
        q0 = liquidity * (1.0 / sqrt_a - 1.0 / sqrt_b)
        q1 = 0.0
    elif current >= upper:
        q0 = 0.0
        q1 = liquidity * (sqrt_b - sqrt_a)
    else:
        sqrt_p = math.sqrt(current)
        q0 = liquidity * (1.0 / sqrt_p - 1.0 / sqrt_b)
        q1 = liquidity * (sqrt_p - sqrt_a)
    return LPInventory(q0=q0, q1=q1, nav_quote=q0 * current + q1)


def lp_nav_ex_fee(state: V3PositionState | Mapping[str, float], price: float) -> float:
    """Quote-token NAV of LP principal only; fee/reward inputs are not accepted."""

    return current_inventory(state, price).nav_quote


def il_usd(lp_nav_ex_fee_value: float, hodl_nav_value: float) -> float:
    """IL in USD: LP principal NAV minus immutable-basket HODL NAV."""

    lp_value = _finite(lp_nav_ex_fee_value, "lp_nav_ex_fee", nonnegative=True)
    hodl_value = _finite(hodl_nav_value, "hodl_nav", nonnegative=True)
    return lp_value - hodl_value


def il_pct(il_usd_value: float, hodl_nav_value: float) -> float:
    """IL fraction (not percentage points), with an explicit zero-denominator error."""

    loss = _finite(il_usd_value, "il_usd")
    hodl_value = _finite(hodl_nav_value, "hodl_nav", nonnegative=True)
    if hodl_value == 0.0:
        raise ZeroDivisionError("IL percentage is undefined when HODL NAV is zero")
    return loss / hodl_value


def pnl_vs_usdc(current_total_nav: float, entry_capital_usd: float) -> float:
    """Capital-preservation PnL in USD."""

    current = _finite(current_total_nav, "current_total_nav", nonnegative=True)
    entry = _finite(entry_capital_usd, "entry_capital_usd", nonnegative=True)
    return current - entry


def alpha_vs_hodl(current_total_nav: float, hodl_nav_value: float) -> float:
    """USD alpha of total current NAV versus the immutable entry basket."""

    current = _finite(current_total_nav, "current_total_nav", nonnegative=True)
    hodl_value = _finite(hodl_nav_value, "hodl_nav", nonnegative=True)
    return current - hodl_value
