"""Offline, Decimal-based organic-volume checks for Uniswap V3 swap events.

The nominal volume of one event is ``abs(amount1)``.  This is a proxy
denominated in token1 and is not comparable across pools with different
tokens or prices.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _direction(amount0: Any, amount1: Any) -> Optional[str]:
    a0 = _decimal(amount0)
    a1 = _decimal(amount1)
    if a0 is None or a1 is None:
        return None
    if a0 < 0 < a1:
        return "BUY0"
    if a0 > 0 > a1:
        return "SELL0"
    return None


def swap_direction(event: dict) -> Optional[str]:
    """Return BUY0/SELL0 only when amount0 and amount1 have opposite signs."""
    if not isinstance(event, dict):
        return None
    return _direction(event.get("amount0"), event.get("amount1"))


def _event_volume(event: Any) -> Optional[tuple[str, Decimal]]:
    if not isinstance(event, dict) or event.get("sender") is None:
        return None
    amount1 = _decimal(event.get("amount1"))
    if amount1 is None:
        return None
    return str(event["sender"]).lower(), abs(amount1)


def _empty_concentration(n_events: int = 0) -> dict:
    return {
        "n_events": n_events,
        "n_unique_senders": 0,
        "top1_share": None,
        "top5_share": None,
        "hhi": None,
        "status": "INPUTS_UNAVAILABLE",
    }


def participant_concentration(events: list[dict]) -> dict:
    """Aggregate proxy volume by lower-cased sender and calculate HHI."""
    n_events = len(events) if isinstance(events, list) else 0
    if not events or not isinstance(events, list):
        return _empty_concentration(n_events)

    by_sender: defaultdict[str, Decimal] = defaultdict(Decimal)
    for event in events:
        item = _event_volume(event)
        if item is None:
            return _empty_concentration(n_events)
        sender, volume = item
        by_sender[sender] += volume

    total = sum(by_sender.values(), Decimal("0"))
    if total <= 0:
        return _empty_concentration(n_events)
    shares = sorted((value / total for value in by_sender.values()), reverse=True)
    return {
        "n_events": n_events,
        "n_unique_senders": len(by_sender),
        "top1_share": shares[0],
        "top5_share": sum(shares[:5], Decimal("0")),
        "hhi": sum((share * share for share in shares), Decimal("0")),
        "status": "COMPUTED",
    }


def _empty_round_trip(n_events: int = 0) -> dict:
    return {
        "pair_count": 0,
        "round_trip_volume": None,
        "total_volume": None,
        "round_trip_share": None,
        "status": "INPUTS_UNAVAILABLE",
        "_matched_by_sender": {},
        "_by_sender": {},
        "n_events": n_events,
        "n_unique_senders": 0,
    }


def _round_trip_analysis(events: list[dict], window_blocks: int) -> dict:
    n_events = len(events) if isinstance(events, list) else 0
    if not events or not isinstance(events, list):
        return _empty_round_trip(n_events)

    usable = []
    by_sender: defaultdict[str, Decimal] = defaultdict(Decimal)
    for index, event in enumerate(events):
        item = _event_volume(event)
        if item is None:
            return _empty_round_trip(n_events)
        sender, volume = item
        by_sender[sender] += volume
        block = event.get("block") if isinstance(event, dict) else None
        try:
            block = int(block)
        except (TypeError, ValueError):
            block = None
        usable.append((block, index, event, sender, volume))

    total = sum(by_sender.values(), Decimal("0"))
    ordered = sorted(
        usable,
        key=lambda row: (row[0] is None, row[0] if row[0] is not None else 0, row[1]),
    )
    pending: defaultdict[str, dict[str, list[tuple[int, Decimal]]]] = defaultdict(
        lambda: {"BUY0": [], "SELL0": []}
    )
    matched_by_sender: defaultdict[str, Decimal] = defaultdict(Decimal)
    pair_count = 0
    round_trip = Decimal("0")
    try:
        window = max(0, int(window_blocks))
    except (TypeError, ValueError):
        window = 50

    for block, _index, event, sender, volume in ordered:
        direction = swap_direction(event)
        if direction is None or block is None:
            continue
        opposite = "SELL0" if direction == "BUY0" else "BUY0"
        candidates = pending[sender][opposite]
        match_index = None
        for candidate_index in range(len(candidates) - 1, -1, -1):
            old_block, _old_volume = candidates[candidate_index]
            if block - old_block <= window:
                match_index = candidate_index
                break
        if match_index is None:
            pending[sender][direction].append((block, volume))
            continue
        _old_block, old_volume = candidates.pop(match_index)
        leg = min(volume, old_volume)
        # A matched pair has two legs; each leg is capped at the smaller leg.
        pair_volume = leg * Decimal("2")
        pair_count += 1
        round_trip += pair_volume
        matched_by_sender[sender] += pair_volume

    share = round_trip / total if total > 0 else None
    if share is not None:
        share = min(Decimal("1"), max(Decimal("0"), share))
    return {
        "pair_count": pair_count,
        "round_trip_volume": round_trip,
        "total_volume": total,
        "round_trip_share": share,
        "status": "COMPUTED",
        "_matched_by_sender": dict(matched_by_sender),
        "_by_sender": dict(by_sender),
        "n_events": n_events,
        "n_unique_senders": len(by_sender),
    }


def round_trip_volume(events: list[dict], *, window_blocks: int = 50) -> dict:
    """Pair opposite directions once per event within the block window."""
    result = _round_trip_analysis(events, window_blocks)
    return {key: value for key, value in result.items() if not key.startswith("_")}


def _empty_organic(n_events: int = 0) -> dict:
    return {
        "total_volume": None,
        "round_trip_volume": None,
        "concentration_excess_volume": None,
        "organic_volume": None,
        "organic_fraction": None,
        "n_events": n_events,
        "n_unique_senders": 0,
        "status": "INPUTS_UNAVAILABLE",
        "notes": None,
    }


def organic_volume_estimate(
    events: list[dict],
    *,
    window_blocks: int = 50,
    max_single_sender_share: Decimal = Decimal("0.25"),
    min_events: int = 50,
) -> dict:
    """Estimate organic proxy volume after wash and concentration haircuts."""
    n_events = len(events) if isinstance(events, list) else 0
    if not events or not isinstance(events, list):
        return _empty_organic(n_events)

    analysis = _round_trip_analysis(events, window_blocks)
    total = analysis["total_volume"]
    if total is None or total <= 0:
        return _empty_organic(n_events)

    by_sender = analysis["_by_sender"]
    matched = analysis["_matched_by_sender"]
    remaining = {
        sender: max(volume - matched.get(sender, Decimal("0")), Decimal("0"))
        for sender, volume in by_sender.items()
    }
    remaining_total = sum(remaining.values(), Decimal("0"))
    threshold = _decimal(max_single_sender_share)
    if threshold is None:
        return _empty_organic(n_events)
    concentration_excess = Decimal("0")
    if remaining_total > 0:
        for volume in remaining.values():
            concentration_excess += max(volume - threshold * remaining_total, Decimal("0"))
    organic = max(remaining_total - concentration_excess, Decimal("0"))
    fraction = organic / total
    fraction = min(Decimal("1"), max(Decimal("0"), fraction))
    try:
        minimum = int(min_events)
    except (TypeError, ValueError):
        minimum = 50
    status = "INSUFFICIENT_SAMPLES" if 0 < n_events < minimum else "COMPUTED"
    if status != "COMPUTED":
        fraction = None
    return {
        "total_volume": total,
        "round_trip_volume": analysis["round_trip_volume"],
        "concentration_excess_volume": concentration_excess,
        "organic_volume": organic,
        "organic_fraction": fraction,
        "n_events": n_events,
        "n_unique_senders": analysis["n_unique_senders"],
        "status": status,
        "notes": "Round-trip volume is removed before sender concentration excess is calculated.",
    }


def apply_organic_haircut(
    fee_apr_pct: Optional[Decimal], organic_fraction: Optional[Decimal]
) -> Optional[Decimal]:
    """Multiply fee APR by the verified organic fraction, or return None."""
    if fee_apr_pct is None or organic_fraction is None:
        return None
    fee = _decimal(fee_apr_pct)
    fraction = _decimal(organic_fraction)
    if fee is None or fraction is None:
        return None
    return fee * fraction


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline organic-volume estimate")
    parser.add_argument("--events-json", required=True, help="JSON file containing swap events")
    parser.add_argument("--out", required=True, help="Output JSON file")
    args = parser.parse_args()
    with Path(args.events_json).open("r", encoding="utf-8") as handle:
        events = json.load(handle, parse_float=Decimal, parse_int=int)
    result = organic_volume_estimate(events)
    Path(args.out).write_text(
        json.dumps(result, default=_json_default, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
