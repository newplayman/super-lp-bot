#!/usr/bin/env python3
"""RH size-interval classification: what happens when q_min > q_max (T31).

T31 forensics: ``q_min`` / ``q_max`` exist only as SQLite columns
(``scripts.lp_rh_store_v1_readonly``: the table DDL and the
``rh_economic_evaluations`` field set).  No module computes an economic
feasibility interval from them, and nothing handles ``q_min > q_max``.

The use-case expectation: "the economic feasibility interval is empty, a
legal 0 configuration" -- an EMPTY interval is a normal, explainable
RESULT, not an error and not ``INPUTS_UNAVAILABLE``.  The PRD status name
is ``SIZE_INTERVAL_EMPTY``.

Why the distinction matters: an empty interval means "this pool is not
profitable at any position size" -- a computed conclusion.  Merging it into
``INPUTS_UNAVAILABLE`` would read as missing data and send operators to
fetch data instead of switching pools.

All values are ``Decimal``.  Pure offline: no I/O beyond the file named on
the command line.  Not wired into netcover or the terminal gate (that is
the next package).
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Statuses for which a position size can actually be chosen.  The two
# non-actionable statuses are NOT synonyms: SIZE_INTERVAL_EMPTY is a
# computed conclusion (switch pools), INPUTS_UNAVAILABLE is missing data
# (go fetch it).  Callers must read ``status``, not just this boolean.
ACTIONABLE_STATUSES = frozenset({"COMPUTED", "SIZE_INTERVAL_POINT"})


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce int/float/str/Decimal to Decimal; None/bool/bad input -> None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value))
    except Exception:
        return None


def size_interval(*, q_min: Any, q_max: Any) -> dict:
    """Classify the economic feasibility interval [q_min, q_max].

    Returns {"status", "q_min", "q_max", "width", "reason"}:
      * either bound None -> status="INPUTS_UNAVAILABLE", width is None
        (None, NOT 0 -- unknown is distinct from zero width);
      * q_min > q_max     -> status="SIZE_INTERVAL_EMPTY", width =
        q_max - q_min (negative, reported as-is); a computed conclusion,
        not missing data;
      * q_min == q_max    -> status="SIZE_INTERVAL_POINT", width == 0;
        legal: exactly one feasible size;
      * q_min < q_max     -> status="COMPUTED", width > 0.
    """
    lo = _to_decimal(q_min)
    hi = _to_decimal(q_max)
    if lo is None or hi is None:
        return {
            "status": "INPUTS_UNAVAILABLE",
            "q_min": lo,
            "q_max": hi,
            "width": None,
            "reason": "q_min or q_max missing; no interval can be computed",
        }
    if lo > hi:
        return {
            "status": "SIZE_INTERVAL_EMPTY",
            "q_min": lo,
            "q_max": hi,
            "width": hi - lo,
            "reason": (
                f"q_min={lo} > q_max={hi}: no feasible position size; "
                "computed conclusion, not missing data"
            ),
        }
    if lo == hi:
        return {
            "status": "SIZE_INTERVAL_POINT",
            "q_min": lo,
            "q_max": hi,
            "width": Decimal(0),
            "reason": f"q_min == q_max == {lo}: exactly one feasible size",
        }
    return {
        "status": "COMPUTED",
        "q_min": lo,
        "q_max": hi,
        "width": hi - lo,
        "reason": f"q_min={lo} < q_max={hi}: feasible interval",
    }


def is_actionable(interval: Mapping[str, Any]) -> bool:
    """True only for COMPUTED and SIZE_INTERVAL_POINT.

    SIZE_INTERVAL_EMPTY and INPUTS_UNAVAILABLE are both False -- but they
    mean different things: EMPTY is a computed conclusion (this pool is not
    profitable at any size; switch pools), UNAVAILABLE is missing data (go
    fetch it).  Callers should read ``interval["status"]``, not just this
    boolean.
    """
    return interval.get("status") in ACTIONABLE_STATUSES


def clamp_to_interval(size: Any, interval: Mapping[str, Any]) -> Optional[Decimal]:
    """Clamp a position size into the interval; None when that is unsafe.

    An empty interval (SIZE_INTERVAL_EMPTY) or missing inputs
    (INPUTS_UNAVAILABLE) yields None -- never a clamp onto a boundary,
    since no size inside the interval exists.  A point interval clamps
    everything to the single feasible size.
    """
    if not is_actionable(interval):
        return None
    lo = _to_decimal(interval.get("q_min"))
    hi = _to_decimal(interval.get("q_max"))
    value = _to_decimal(size)
    if lo is None or hi is None or value is None:
        return None
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _json_safe(value: Any) -> Any:
    """Decimal -> str to preserve precision; recurse into containers."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH size-interval classification (offline, read-only)."
    )
    parser.add_argument("--q-min", default=None, help="lower bound; omit for unknown")
    parser.add_argument("--q-max", default=None, help="upper bound; omit for unknown")
    parser.add_argument("--out", help="output path; defaults to stdout")
    args = parser.parse_args(argv)
    result = size_interval(q_min=args.q_min, q_max=args.q_max)
    payload = json.dumps(_json_safe(result), indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
