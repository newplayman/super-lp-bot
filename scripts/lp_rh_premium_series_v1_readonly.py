"""Offline premium time-series statistics for RH LP evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Optional


LVR_COEFFICIENT_MODEL = Decimal("0.50")
TEN_THOUSAND = Decimal("10000")
ZERO = Decimal("0")


def _as_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def premium_bps(chain_price: Any, reference_price: Any) -> Optional[Decimal]:
    """Return chain-vs-reference premium in basis points."""
    chain = _as_decimal(chain_price)
    reference = _as_decimal(reference_price)
    if chain is None or reference is None or chain <= ZERO or reference <= ZERO:
        return None
    return (chain / reference - Decimal(1)) * TEN_THOUSAND


def _parse_time(value: Any) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _seconds_between(later: datetime, earlier: datetime) -> Decimal:
    delta = later - earlier
    whole_seconds = delta.days * 86400 + delta.seconds
    return Decimal(whole_seconds) + Decimal(delta.microseconds) / Decimal(1000000)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _percentile(values: list[Decimal], fraction: Decimal) -> Decimal:
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _sign(value: Decimal) -> int:
    # Zero is deliberately part of the positive-sign bucket.
    return 1 if value >= ZERO else -1


def _empty_statistics(n_total: int, n_usable: int, n_skipped: int,
                      status: str) -> dict[str, Any]:
    return {
        "n_total": n_total,
        "n_usable": n_usable,
        "n_skipped": n_skipped,
        "status": status,
        "mean_bps": None,
        "median_bps": None,
        "stdev_bps": None,
        "p05_bps": None,
        "p95_bps": None,
        "max_abs_bps": None,
        "zero_crossings": None,
        "sign_stability": None,
        "persistence_frac": None,
        "half_life_secs": None,
        "n_distinct_reference": None,
        "reference_quantum_bps": None,
        "reference_spread_bps": None,
        "resolution_floor_bps": None,
    }


def _half_life(usable: list[tuple[datetime, Decimal]]) -> Optional[Decimal]:
    if len(usable) < 2:
        return None
    previous = [item[1] for item in usable[:-1]]
    current = [item[1] for item in usable[1:]]
    denominator = sum((value * value for value in previous), ZERO)
    if denominator == ZERO:
        return None
    rho = sum((left * right for left, right in zip(previous, current)), ZERO)
    rho /= denominator
    if not (ZERO < rho < Decimal(1)):
        return None
    intervals = [
        _seconds_between(usable[index][0], usable[index - 1][0])
        for index in range(1, len(usable))
    ]
    median_interval = _median(intervals)
    return -Decimal(2).ln() / rho.ln() * median_interval


def _resolution_fields(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute reference-resolution fields from the usable samples.

    The resolution floor is the data source's noise floor: the smallest
    reference-price step (quantum) plus the median bid/ask spread. A premium
    signal that does not rise above this floor cannot be classified.
    """
    reference_prices: list[Decimal] = []
    spreads: list[Decimal] = []
    for sample in samples:
        reference = _as_decimal(sample.get("reference_price"))
        if reference is not None and reference > ZERO:
            reference_prices.append(reference)
        bid = _as_decimal(sample.get("reference_bid"))
        ask = _as_decimal(sample.get("reference_ask"))
        if bid is not None and ask is not None and bid > ZERO and ask > ZERO:
            mid = (bid + ask) / Decimal(2)
            if mid > ZERO:
                spreads.append((ask - bid) / mid * TEN_THOUSAND)
    distinct = sorted(set(reference_prices))
    n_distinct = len(distinct)
    quantum: Optional[Decimal] = None
    if n_distinct >= 2:
        steps = [distinct[i + 1] - distinct[i] for i in range(n_distinct - 1)]
        min_step = min(steps)
        median_reference = _median(distinct)
        if median_reference > ZERO:
            quantum = min_step / median_reference * TEN_THOUSAND
    spread: Optional[Decimal] = _median(spreads) if spreads else None
    if quantum is None and spread is None:
        floor: Optional[Decimal] = None
    else:
        floor = (quantum or ZERO) + (spread or ZERO)
    return {
        "n_distinct_reference": n_distinct,
        "reference_quantum_bps": quantum,
        "reference_spread_bps": spread,
        "resolution_floor_bps": floor,
    }


def series_stats(
    samples: Any,
    *,
    min_samples: int = 30,
    persistence_threshold_bps: Decimal = Decimal("10"),
) -> dict[str, Any]:
    """Compute descriptive and persistence statistics from price samples."""
    sample_list = list(samples or [])
    n_total = len(sample_list)
    usable: list[tuple[datetime, Decimal, dict[str, Any]]] = []
    n_skipped = 0
    for sample in sample_list:
        if not isinstance(sample, dict):
            n_skipped += 1
            continue
        premium = premium_bps(sample.get("chain_price"), sample.get("reference_price"))
        if premium is None:
            n_skipped += 1
            continue
        try:
            sample_time = _parse_time(sample.get("sample_time"))
        except (TypeError, ValueError, OverflowError):
            n_skipped += 1
            continue
        usable.append((sample_time, premium, sample))

    usable.sort(key=lambda item: item[0])
    n_usable = len(usable)
    if n_usable == 0:
        return _empty_statistics(n_total, n_usable, n_skipped, "INPUTS_UNAVAILABLE")
    if n_usable < min_samples:
        return _empty_statistics(n_total, n_usable, n_skipped, "INSUFFICIENT_SAMPLES")

    values = [item[1] for item in usable]
    mean = sum(values, ZERO) / Decimal(n_usable)
    variance = sum(((value - mean) ** 2 for value in values), ZERO)
    stdev = (variance / Decimal(n_usable)).sqrt()
    signs = [_sign(value) for value in values]
    zero_crossings = sum(
        left != right for left, right in zip(signs, signs[1:])
    )
    positive_count = signs.count(1)
    negative_count = signs.count(-1)
    sign_stability = Decimal(max(positive_count, negative_count)) / Decimal(n_usable)
    threshold = _as_decimal(persistence_threshold_bps)
    if threshold is None:
        threshold = Decimal("10")
    persistent_count = sum(abs(value) > threshold for value in values)

    return {
        "n_total": n_total,
        "n_usable": n_usable,
        "n_skipped": n_skipped,
        "status": "COMPUTED",
        "mean_bps": mean,
        "median_bps": _median(values),
        "stdev_bps": stdev,
        "p05_bps": _percentile(values, Decimal("0.05")),
        "p95_bps": _percentile(values, Decimal("0.95")),
        "max_abs_bps": max(abs(value) for value in values),
        "zero_crossings": zero_crossings,
        "sign_stability": sign_stability,
        "persistence_frac": Decimal(persistent_count) / Decimal(n_usable),
        "half_life_secs": _half_life(usable),
        **_resolution_fields([item[2] for item in usable]),
    }


def premium_regime(stats: dict[str, Any]) -> str:
    """Classify a computed series without treating unknown data as benign."""
    status = stats.get("status")
    if status != "COMPUTED":
        return status
    # A constant reference is NOT on its own a reason to refuse: if the chain
    # price swings 100 bps against a still reference, the premium swings 100 bps
    # and that is real, measurable LVR exposure.  Verified on live data that the
    # resolution check below catches both real cases (SGOV stdev 0.107 vs floor
    # 0.995, AMC 39.19 vs 79.29) while leaving SPY/QQQ/NVDA/GLD classified.
    resolution_floor_bps = stats.get("resolution_floor_bps")
    stdev_bps = stats.get("stdev_bps")
    if resolution_floor_bps is None:
        return "INSUFFICIENT_RESOLUTION"
    if stdev_bps is not None and stdev_bps <= resolution_floor_bps:
        return "INSUFFICIENT_RESOLUTION"
    n_usable = stats["n_usable"]
    if (
        stats["sign_stability"] >= Decimal("0.9")
        and stats["zero_crossings"] <= Decimal(n_usable) * Decimal("0.02")
    ):
        return "PERSISTENT_OFFSET"
    if (
        stats["zero_crossings"] >= Decimal(n_usable) * Decimal("0.1")
        and stats["half_life_secs"] is not None
    ):
        return "MEAN_REVERTING"
    return "UNSTABLE"


def lvr_haircut_frac(stats: dict[str, Any], regime: str) -> Optional[Decimal]:
    """Return the modelled fee haircut for the classified premium regime."""
    if regime == "INSUFFICIENT_RESOLUTION":
        return None
    if regime == "MEAN_REVERTING":
        stdev = stats.get("stdev_bps")
        if stdev is None:
            return None
        return min(Decimal(1), stdev / TEN_THOUSAND * LVR_COEFFICIENT_MODEL)
    if regime == "PERSISTENT_OFFSET":
        return Decimal(0)
    return None


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-json", required=True, help="input JSON file")
    parser.add_argument("--out", required=True, help="output JSON file")
    args = parser.parse_args()
    with Path(args.samples_json).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    samples = raw.get("samples", []) if isinstance(raw, dict) else raw
    stats = series_stats(samples)
    stats["regime"] = premium_regime(stats)
    stats["lvr_haircut_frac"] = lvr_haircut_frac(stats, stats["regime"])
    output = json.dumps(stats, ensure_ascii=False, indent=2, default=_json_default)
    Path(args.out).write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
