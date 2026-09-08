#!/usr/bin/env python3
"""RH-04e: in-range duration conversion (read-only, offline).

The full-range fee APR measured by the main brain (27.34%) is an UPPER BOUND:
a concentrated-liquidity position only accrues fees while the price is inside
its [tick_lower, tick_upper) range; out of range the fee is 0 while inventory
risk remains.  PRD §10.1 requires revenue to be computed on the TRUE in-range
duration, not the full-range bound.

This module converts a full-range fee EV into an effective (in-range) fee EV
using the observed in-range fraction from real price samples.  Pure and
offline: it reads a local SQLite DB read-only (or takes in-memory samples in
tests) and never touches wallets, chain state, or the network.  Money amounts
and ratios are carried as Decimal; missing inputs stay None and are never
filled with 0.

The single most important correctness rule (see
reports/rh_pivot/20260907T124500Z/COST_MODEL_PRICE_SCALE_BUG.md): the Uniswap
V3 tick is defined on the RAW token1/token0 ratio, so a decimals-normalised
(human) price must be scaled back to raw units BEFORE taking the log.
Skipping that scaling lands the tick ~280k ticks away.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Uniswap V3 tick base: price = (1.0001) ** tick on the RAW ratio.
TICK_BASE = 1.0001
_LN_TICK_BASE = math.log(TICK_BASE)
_LN_10 = math.log(10.0)


def _parse_time(value: str) -> datetime:
    """Parse an ISO-8601 sample_time (with trailing 'Z') to a datetime."""
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def tick_from_price(price_human: Any, *, dec0: int, dec1: int) -> int:
    """Invert the Uniswap V3 tick from a decimals-normalised (human) price.

    The tick is defined on the RAW token1/token0 ratio:
        raw  = price_human * 10 ** (dec1 - dec0)
        tick = ln(raw) / ln(1.0001)

    The precision scaling (10 ** (dec1 - dec0)) MUST be applied before the log;
    omitting it is the exact bug documented in COST_MODEL_PRICE_SCALE_BUG.md.
    """
    p = Decimal(str(price_human))
    if p <= 0:
        raise ValueError("price must be positive")
    ln_raw = math.log(float(p)) + (int(dec1) - int(dec0)) * _LN_10
    return int(round(ln_raw / _LN_TICK_BASE))


def in_range_fraction(samples: Sequence[Dict[str, Any]], *,
                      tick_lower: int, tick_upper: int,
                      dec0: int, dec1: int) -> Dict[str, Any]:
    """Fraction of samples whose price is inside [tick_lower, tick_upper).

    ``samples`` is a list of ``{"sample_time", "reference_mid"}`` where
    ``reference_mid`` is a decimals-normalised (human) price string, or None
    when the collector had no reading.  A None sample is SKIPPED and counted
    in ``skipped`` — it is NOT treated as out-of-range (missing data is not
    the same as being out of range), and it is excluded from the fraction
    denominator.

    Returns a dict with:
      total_samples     — number of input samples (including None ones)
      in_range_samples  — non-None samples inside the range
      fraction          — Decimal, in_range / (total - skipped); 0 if no data
      first / last      — sample_time of the first / last input sample
      skipped           — number of None samples skipped
      excursions        — maximal contiguous out-of-range runs, each
                          {"start","end","duration_secs","side"} where side is
                          "BELOW" (price fell under tick_lower) or "ABOVE"
                          (price rose to/over tick_upper).  None samples do
                          not break a run (a data gap is not a re-entry).
    """
    total = len(samples)
    skipped = 0
    in_range = 0
    points: List[tuple] = []  # (datetime, state, original_time_str)
    for s in samples:
        mid = s.get("reference_mid")
        if mid is None:
            skipped += 1
            continue
        tick = tick_from_price(mid, dec0=dec0, dec1=dec1)
        if tick < tick_lower:
            state = "BELOW"
        elif tick >= tick_upper:
            state = "ABOVE"
        else:
            state = "IN"
            in_range += 1
        points.append((_parse_time(s["sample_time"]), state, s["sample_time"]))

    denom = total - skipped
    fraction = (Decimal(in_range) / Decimal(denom)) if denom > 0 else Decimal(0)

    excursions: List[Dict[str, Any]] = []
    i, n = 0, len(points)
    while i < n:
        if points[i][1] != "IN":
            j = i
            while j < n and points[j][1] != "IN":
                j += 1
            run = points[i:j]
            excursions.append({
                "start": run[0][2],
                "end": run[-1][2],
                "duration_secs": (run[-1][0] - run[0][0]).total_seconds(),
                "side": "BELOW" if run[0][1] == "BELOW" else "ABOVE",
            })
            i = j
        else:
            i += 1

    return {
        "total_samples": total,
        "in_range_samples": in_range,
        "fraction": fraction,
        "first": samples[0]["sample_time"] if samples else None,
        "last": samples[-1]["sample_time"] if samples else None,
        "skipped": skipped,
        "excursions": excursions,
    }


def effective_fee_ev(*, full_range_fee_ev: Optional[Decimal],
                     in_range_fraction: Optional[Decimal],
                     concentration_multiplier: Optional[Decimal]) -> Optional[Decimal]:
    """Effective in-range fee EV = full_range * in_range_fraction * multiplier.

    ``concentration_multiplier`` MUST be supplied by the caller — it depends on
    range width and the liquidity distribution, which this module does not
    estimate.  It only converts.  Any None input yields None (never 0).
    """
    if (full_range_fee_ev is None or in_range_fraction is None
            or concentration_multiplier is None):
        return None
    return full_range_fee_ev * in_range_fraction * concentration_multiplier


def range_scan(samples: Sequence[Dict[str, Any]], *, center_tick: int,
               widths_ticks: Sequence[int], dec0: int,
               dec1: int) -> List[Dict[str, Any]]:
    """Scan in-range fraction across symmetric range widths around center_tick.

    For each width w the range is [center_tick - w, center_tick + w).  This is
    the empirical tool for answering "how wide should the range be": wider
    ranges are in-range more of the time but earn less fee per unit of
    liquidity; narrower ranges are the reverse.  ``fraction`` is monotonically
    non-decreasing in width (a wider range contains every narrower one).
    """
    results: List[Dict[str, Any]] = []
    for w in widths_ticks:
        tick_lower = int(center_tick) - int(w)
        tick_upper = int(center_tick) + int(w)
        r = in_range_fraction(samples, tick_lower=tick_lower,
                              tick_upper=tick_upper, dec0=dec0, dec1=dec1)
        results.append({
            "width_ticks": int(w),
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "fraction": r["fraction"],
            "excursion_count": len(r["excursions"]),
        })
    return results


def _load_samples(db_path: str) -> List[Dict[str, Any]]:
    """Read (sample_time, reference_mid) from rh_market_states, read-only."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sample_time, reference_mid FROM rh_market_states "
            "ORDER BY sample_time"
        ).fetchall()
    finally:
        con.close()
    return [{"sample_time": r[0], "reference_mid": r[1]} for r in rows]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-04e in-range fraction (read-only, offline).")
    parser.add_argument("--db", required=True,
                        help="path to scanner.db (opened read-only)")
    parser.add_argument("--tick-lower", type=int, required=True)
    parser.add_argument("--tick-upper", type=int, required=True)
    parser.add_argument("--dec0", type=int, required=True)
    parser.add_argument("--dec1", type=int, required=True)
    parser.add_argument("--out", required=True,
                        help="path to write the JSON result")
    args = parser.parse_args(argv)

    samples = _load_samples(args.db)
    result = in_range_fraction(samples, tick_lower=args.tick_lower,
                               tick_upper=args.tick_upper,
                               dec0=args.dec0, dec1=args.dec1)
    out = {
        "total_samples": result["total_samples"],
        "in_range_samples": result["in_range_samples"],
        "fraction": str(result["fraction"]),
        "first": result["first"],
        "last": result["last"],
        "skipped": result["skipped"],
        "excursions": result["excursions"],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
