#!/usr/bin/env python3
"""RH gas estimator: chain-state-based gas cost in USD (read-only, offline).

T34 forensics: ``gas_usd`` in the netcover inputs is a straight passthrough of
``evidence["gas_usd_estimate"]`` with no L1 data-fee term, no double-charge
detection, and no sanity check.  The main brain's hand-filled ``0.02``
understated the true value (~$0.4614) by ~23x and inverted a capital-policy
verdict.  But the measured 0.4614 must not be hard-coded either: on
Arbitrum-class L2s the gas bill is dominated by the L1 data fee and swings
with mainnet congestion.

This module therefore (a) computes a gas cost from *injected* chain state
(gas price + native price + gas units) rather than a constant, and (b)
provides ``gas_estimate_sanity`` -- the gate that would have caught the 23x
understatement by comparing an external estimate against a measured value.

Family convention: any network access goes through an injected ``call_fn``;
this module performs no I/O beyond the files named on the command line.
All money is ``Decimal``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Typical Uniswap V3 gas costs, in gas units.  These are NOT measured on this
# chain; they are order-of-magnitude references for a V3-style pool and should
# be replaced by a later package that calibrates them from real receipts via
# ``observed_gas_units``.
GAS_UNITS = {
    "v3_mint": 450000,
    "v3_burn_collect": 350000,
    "swap": 150000,
}

_E18 = Decimal(10) ** 18


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce int/float/str/Decimal to Decimal; None or bad input -> None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except Exception:
        return None


def estimate_gas_usd(
    *,
    gas_price_wei: Any,
    native_price_usd: Any,
    gas_units: Any,
) -> Optional[Decimal]:
    """gas_units * gas_price_wei / 1e18 * native_price_usd, as Decimal.

    Returns None (never 0) when any input is None or <= 0.
    """
    gp = _to_decimal(gas_price_wei)
    np_ = _to_decimal(native_price_usd)
    gu = _to_decimal(gas_units)
    if gp is None or np_ is None or gu is None:
        return None
    if gp <= 0 or np_ <= 0 or gu <= 0:
        return None
    return gu * gp / _E18 * np_


def round_trip_gas_usd(
    *,
    gas_price_wei: Any,
    native_price_usd: Any,
) -> Optional[Decimal]:
    """Open + close a position: v3_mint + v3_burn_collect gas units."""
    units = GAS_UNITS["v3_mint"] + GAS_UNITS["v3_burn_collect"]
    return estimate_gas_usd(
        gas_price_wei=gas_price_wei,
        native_price_usd=native_price_usd,
        gas_units=units,
    )


def _parse_iso(ts_str: str) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def observed_gas_usd(
    conn,
    *,
    now: str,
    max_age_secs: int = 3600,
    min_samples: int = 3,
) -> dict:
    """近期真实 gas 观测的中位数。

    返回 {"gas_usd": Decimal|None, "source": str, "sample_count": int,
          "newest_observed_at": str|None, "reason": str}
    """
    now_dt = _parse_iso(now)
    if now_dt is None:
        raise ValueError(f"Invalid 'now' timestamp: {now!r}")

    # Check table existence
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_gas_observations'"
        )
        if not cur.fetchone():
            return {
                "gas_usd": None,
                "source": "observed",
                "sample_count": 0,
                "newest_observed_at": None,
                "reason": "GAS_OBSERVATIONS_TABLE_MISSING",
            }
    except Exception:
        return {
            "gas_usd": None,
            "source": "observed",
            "sample_count": 0,
            "newest_observed_at": None,
            "reason": "GAS_OBSERVATIONS_TABLE_MISSING",
        }

    # Fetch all records from rh_gas_observations
    rows = conn.execute(
        "SELECT observed_at, gas_usd FROM rh_gas_observations ORDER BY observed_at DESC"
    ).fetchall()

    if not rows:
        return {
            "gas_usd": None,
            "source": "observed",
            "sample_count": 0,
            "newest_observed_at": None,
            "reason": "GAS_OBSERVATIONS_EMPTY",
        }

    newest_observed_at = rows[0][0]
    newest_dt = _parse_iso(newest_observed_at)
    if newest_dt is None or (now_dt - newest_dt).total_seconds() > max_age_secs:
        return {
            "gas_usd": None,
            "source": "observed",
            "sample_count": 0,
            "newest_observed_at": newest_observed_at,
            "reason": "GAS_OBSERVATIONS_STALE",
        }

    # Collect valid samples within max_age_secs window
    valid_gas_vals: list[Decimal] = []
    for obs_at_str, gas_usd_raw in rows:
        obs_dt = _parse_iso(obs_at_str)
        if obs_dt is None:
            continue
        age_secs = (now_dt - obs_dt).total_seconds()
        if 0 <= age_secs <= max_age_secs:
            val = _to_decimal(gas_usd_raw)
            if val is not None:
                valid_gas_vals.append(val)

    sample_count = len(valid_gas_vals)
    if sample_count < min_samples:
        return {
            "gas_usd": None,
            "source": "observed",
            "sample_count": sample_count,
            "newest_observed_at": newest_observed_at,
            "reason": "GAS_OBSERVATIONS_INSUFFICIENT",
        }

    med = _median(valid_gas_vals)
    return {
        "gas_usd": med,
        "source": "observed",
        "sample_count": sample_count,
        "newest_observed_at": newest_observed_at,
        "reason": "OK",
    }


def _median(values: Sequence[Decimal]) -> Optional[Decimal]:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: Sequence[Decimal], pct: Decimal) -> Optional[Decimal]:
    """Linear-interpolation percentile (pct in [0, 100])."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = (pct / 100) * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    fraction = rank - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def observed_gas_units(receipts: Sequence[Mapping[str, Any]]) -> dict:
    """Summarise receipts: [{"gasUsed": int, "effectiveGasPrice": int}].

    Returns {"n", "median_gas_used", "median_gas_price_wei", "p90_gas_used"}.
    Empty input -> n == 0 and every statistic is None (never 0).
    """
    gas_used: list[Decimal] = []
    gas_price: list[Decimal] = []
    for receipt in receipts:
        gu = _to_decimal(receipt.get("gasUsed"))
        gp = _to_decimal(receipt.get("effectiveGasPrice"))
        if gu is not None:
            gas_used.append(gu)
        if gp is not None:
            gas_price.append(gp)
    return {
        "n": len(receipts),
        "median_gas_used": _median(gas_used),
        "median_gas_price_wei": _median(gas_price),
        "p90_gas_used": _percentile(gas_used, Decimal(90)),
    }


def gas_estimate_sanity(
    estimate_usd: Any,
    observed_usd: Any,
    *,
    max_ratio: Any = Decimal("3"),
) -> dict:
    """Compare an external estimate against a measured value.

    Returns {"ratio": Decimal|None, "verdict": "OK"|"UNDERSTATED"|"OVERSTATED"|"UNKNOWN"}.
    ratio = estimate / observed.  UNDERSTATED when estimate < observed/max_ratio;
    OVERSTATED when estimate > observed*max_ratio; UNKNOWN when either side is
    None (or observed <= 0, so the ratio is undefined).
    """
    est = _to_decimal(estimate_usd)
    obs = _to_decimal(observed_usd)
    ratio_max = _to_decimal(max_ratio)
    if ratio_max is None or ratio_max <= 0:
        ratio_max = Decimal("3")
    if est is None or obs is None:
        return {"ratio": None, "verdict": "UNKNOWN"}
    if obs <= 0:
        return {"ratio": None, "verdict": "UNKNOWN"}
    ratio = est / obs
    if est < obs / ratio_max:
        verdict = "UNDERSTATED"
    elif est > obs * ratio_max:
        verdict = "OVERSTATED"
    else:
        verdict = "OK"
    return {"ratio": ratio, "verdict": verdict}


def _json_safe(value: Any) -> Any:
    """Make a result JSON-serialisable (Decimal -> str to preserve precision)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _load_receipts(raw: str) -> list:
    """Read receipts from a JSON file path, or parse inline JSON."""
    path = Path(raw)
    if path.is_file():
        return json.loads(path.read_text())
    return json.loads(raw)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate gas cost in USD from injected chain state (offline)."
    )
    parser.add_argument("--receipts-json", required=True,
                        help="path to a JSON file, or inline JSON, of receipts")
    parser.add_argument("--gas-price-wei", required=True, type=int)
    parser.add_argument("--native-price-usd", required=True)
    parser.add_argument("--out", help="output path; defaults to stdout")
    args = parser.parse_args(argv)

    receipts = _load_receipts(args.receipts_json)
    result = {
        "inputs": {
            "gas_price_wei": args.gas_price_wei,
            "native_price_usd": args.native_price_usd,
        },
        "gas_units": GAS_UNITS,
        "observed": observed_gas_units(receipts),
        "round_trip_gas_usd": round_trip_gas_usd(
            gas_price_wei=args.gas_price_wei,
            native_price_usd=args.native_price_usd,
        ),
    }
    payload = json.dumps(_json_safe(result), indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
