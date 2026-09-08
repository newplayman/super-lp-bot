#!/usr/bin/env python3
"""RH-04c: offline markout and adverse-selection diagnostics.

Markouts are reference marks at registered future horizons, not an unbiased
LVR estimate or a second NAV ledger.  Each horizon remains an independent
field; callers must not add the same fill across horizons.
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Optional, Sequence

REPO_ROOT = "/opt/lpbot/lp-bot-v3-origin-check"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Reuse the repository's money-input guard used by the RH NAV ledger.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_pnl_v1_readonly import _as_decimal as _repo_as_decimal  # noqa: E402


PREREGISTERED_WINDOWS = (30, 300, 1800)


def _money(value: Any, field: str) -> Decimal:
    """Return a Decimal without ever converting a binary floating value."""
    if isinstance(value, str):
        return Decimal(value)
    return _repo_as_decimal(field, value)


def _window(value: Any) -> int:
    """Validate and normalize one registered window."""
    if isinstance(value, bool):
        raise ValueError("WINDOW_NOT_PREREGISTERED")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or value not in PREREGISTERED_WINDOWS:
        raise ValueError("WINDOW_NOT_PREREGISTERED")
    return value


def markout(*, delta_base: Decimal, delta_quote: Decimal,
            ref_base_usd_future: Optional[Decimal],
            ref_quote_usd_future: Optional[Decimal]) -> Optional[Decimal]:
    """Compute ``Δbase*future_base_usd + Δquote*future_quote_usd``.

    A missing future reference leaves the sample incomplete.  In particular,
    no current or stale price is substituted.
    """
    if ref_base_usd_future is None or ref_quote_usd_future is None:
        return None
    base_delta = _money(delta_base, "delta_base")
    quote_delta = _money(delta_quote, "delta_quote")
    base_price = _money(ref_base_usd_future, "ref_base_usd_future")
    quote_price = _money(ref_quote_usd_future, "ref_quote_usd_future")
    return base_delta * base_price + quote_delta * quote_price


def as_signed(markout_value: Optional[Decimal]) -> Optional[Decimal]:
    """Return signed adverse selection: ``AS_signed = -markout``."""
    if markout_value is None:
        return None
    return -_money(markout_value, "markout_value")


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _fill_delta(fill: Any, name: str) -> Any:
    for candidate in (name, name.replace("delta_", "") + "_delta"):
        try:
            return _field(fill, candidate)
        except (KeyError, AttributeError):
            pass
    raise KeyError(name)


def _invoke_lookup(price_lookup: Any, fill: Any, window: int) -> Any:
    """Call common offline lookup shapes without changing the public API."""
    if isinstance(price_lookup, Mapping):
        if window in price_lookup:
            return price_lookup[window]
        return price_lookup.get(str(window))
    if not callable(price_lookup):
        raise TypeError("PRICE_LOOKUP_NOT_CALLABLE")

    try:
        parameters = list(inspect.signature(price_lookup).parameters.values())
    except (TypeError, ValueError):
        return price_lookup(fill, window)
    positional = [p for p in parameters
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    names = {p.name.lower(): p for p in parameters}
    if "fill" in names and "window" in names:
        return price_lookup(fill=fill, window=window)
    if "window" in names and names["window"].kind == names["window"].KEYWORD_ONLY:
        return (price_lookup(window=window) if not positional
                else price_lookup(fill, window=window))
    if any(p.kind == p.VAR_POSITIONAL for p in parameters):
        return price_lookup(fill, window)
    if len(positional) >= 2:
        first, second = positional[0].name.lower(), positional[1].name.lower()
        if "window" in first or "delta" in first:
            return price_lookup(window, fill)
        if "fill" in second or "row" in second:
            return price_lookup(window, fill)
        return price_lookup(fill, window)
    if len(positional) == 1:
        name = positional[0].name.lower()
        return price_lookup(window if any(x in name for x in ("window", "delta", "second"))
                            else fill)
    return price_lookup()


def _references(value: Any, window: int) -> tuple[Any, Any]:
    """Extract a future base/quote pair from a lookup result."""
    if value is None:
        return None, None
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError("PRICE_LOOKUP_INVALID")
        return value[0], value[1]
    if not isinstance(value, Mapping):
        try:
            return (getattr(value, "ref_base_usd_future"),
                    getattr(value, "ref_quote_usd_future"))
        except AttributeError as exc:
            raise ValueError("PRICE_LOOKUP_INVALID") from exc

    base_keys = ("ref_base_usd_future", "base_usd", "base", "reference_base_usd")
    quote_keys = ("ref_quote_usd_future", "quote_usd", "quote", "reference_quote_usd")
    base = next((value[k] for k in base_keys if k in value), None)
    quote = next((value[k] for k in quote_keys if k in value), None)
    if any(k in value for k in base_keys + quote_keys):
        return base, quote
    nested = value.get(window, value.get(str(window)))
    if nested is None:
        return None, None
    return _references(nested, window)


def markout_profile(fill: Any, *, price_lookup: Any) -> dict[str, Any]:
    """Return one independent markout field for each registered window.

    ``price_lookup`` is normally ``(fill, window) -> (base_usd, quote_usd)``;
    a mapping or a one-argument window lookup is also accepted for offline
    fixtures.  Missing future references are listed as incomplete windows.
    """
    delta_base = _fill_delta(fill, "delta_base")
    delta_quote = _fill_delta(fill, "delta_quote")
    profile: dict[str, Any] = {}
    incomplete: list[int] = []
    for registered_window in PREREGISTERED_WINDOWS:
        looked_up = _invoke_lookup(price_lookup, fill, _window(registered_window))
        future_base, future_quote = _references(looked_up, registered_window)
        value = markout(delta_base=delta_base, delta_quote=delta_quote,
                        ref_base_usd_future=future_base,
                        ref_quote_usd_future=future_quote)
        profile[str(registered_window)] = value
        if value is None:
            incomplete.append(registered_window)
    profile["incomplete_windows"] = incomplete
    return profile


def lp_share_of_fill(*, pool_amount: Decimal, lp_liquidity: Decimal,
                     active_liquidity: Decimal) -> Decimal:
    """Return this LP's share of a pool fill before markout is calculated."""
    active = _money(active_liquidity, "active_liquidity")
    if active <= 0:
        raise ValueError("ACTIVE_LIQUIDITY_INVALID")
    return (_money(pool_amount, "pool_amount")
            * _money(lp_liquidity, "lp_liquidity") / active)


def aggregate(profiles: Sequence[Mapping[str, Any]], *, window: Any) -> dict[str, Any]:
    """Aggregate one window only; never add markouts across windows.

    ``n`` and the mean use complete samples.  Incomplete samples are reported
    separately and are never replaced with a stale price or a zero markout.
    """
    registered_window = _window(window)
    values = [profile.get(str(registered_window)) for profile in profiles]
    complete = [_money(value, f"window_{registered_window}")
                for value in values if value is not None]
    total = sum(complete, Decimal("0"))
    n = len(complete)
    return {
        "n": n,
        "sum": total,
        "mean": total / Decimal(n) if n else None,
        "positive_count": sum(1 for value in complete if value > 0),
        "negative_count": sum(1 for value in complete if value < 0),
        "incomplete_count": len(values) - n,
    }


def _embedded_lookup(fill: Mapping[str, Any], window: int) -> Any:
    """Read future references embedded in a JSON fill for the offline CLI."""
    for key in ("future_refs", "references", "ref_by_window", "prices"):
        if key in fill:
            container = fill[key]
            if isinstance(container, Mapping):
                return container.get(window, container.get(str(window)))
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Offline RH markout profile")
    parser.add_argument("--fills-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.fills_json, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    fills = payload.get("fills", []) if isinstance(payload, Mapping) else payload
    profiles = [markout_profile(fill, price_lookup=_embedded_lookup)
                for fill in fills]
    result = {
        "profiles": profiles,
        "aggregates": {str(window): aggregate(profiles, window=window)
                        for window in PREREGISTERED_WINDOWS},
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(_jsonable(result), handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
