#!/usr/bin/env python3
"""RH-05d: premium guard + stock session entry gate (offline).

Pure, offline logic.  Implements the PRD §10.2 / §11 / §12 premium bands and
the stock entry gate.  No network, no collection, no writes to
``reports/lp_rh/``.  All money is ``Decimal``; no ``float``.

The premium bands are the PRD/B2 *Shadow initial values* and are **not
calibrated** against live data (``CALIBRATION_STATUS``).  They must never be
treated as validated thresholds.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_market_session_v1_readonly import _to_dt  # noqa: E402
from scripts.lp_rh_stock_reference_v1_readonly import (  # noqa: E402
    ReferenceValue, exit_quote_required)

# --- PRD §10.2 / §12 premium bands (SHADOW initial values, NOT calibrated) ---
# (upper_bound_bps, band).  A premium above the last bound is DISLOCATION.
PREMIUM_BANDS = ((100, "NORMAL"), (300, "REDUCE_SIZE"),
                 (700, "NO_NEW_WIDEN_REMOVE_EVAL"))
# > 700 -> "DISLOCATION"
CALIBRATION_STATUS = "SHADOW_INITIAL_NOT_CALIBRATED"


def premium_bps(*, dex_price: Optional[Decimal],
                reference_price: Optional[Decimal]) -> Optional[Decimal]:
    """(dex - ref) / ref * 10000, in basis points.

    ``None`` when either input is ``None`` or ``reference_price <= 0`` — a
    missing/invalid reference is UNKNOWN, never 0 (PRD §9.5 discipline).
    """
    if dex_price is None or reference_price is None:
        return None
    if reference_price <= 0:
        return None
    return (dex_price - reference_price) / reference_price * Decimal(10000)


def classify_premium(bps: Optional[Decimal]) -> tuple[str, bool]:
    """Return ``(band, allows_recenter)`` for a premium in bps.

    Bands are applied on ``abs(bps)`` so a discount classifies like a premium.
    ``None`` -> ``("UNKNOWN", False)``.  ``allows_recenter`` is True ONLY for
    the NORMAL band: PRD §10.2 forbids recentering on stale/pause/halt and
    §13.2 says when two policies apply take the stricter, so REDUCE_SIZE,
    NO_NEW_WIDEN_REMOVE_EVAL, DISLOCATION and UNKNOWN all forbid it.
    """
    if bps is None:
        return "UNKNOWN", False
    a = abs(bps)
    for threshold, band in PREMIUM_BANDS:
        if a <= threshold:
            return band, band == "NORMAL"
    return "DISLOCATION", False


def range_center(*, chainlink_or_reference: Decimal, dex_twap: Decimal,
                 premium_bps: Optional[Decimal],
                 max_dex_weight_bps: int = 100) -> tuple[Decimal, str]:
    """PRD §11: synthesize the range center; DEX may never drive it.

    When ``abs(premium_bps) > max_dex_weight_bps`` the DEX is fully excluded
    and the reference is returned unchanged.  Otherwise the DEX participates
    via an equal-weight median (midpoint) of the two prices, so the center
    can never follow DEX drift.  An unknown premium falls back to the
    reference (never trust the DEX without a known premium).
    """
    if premium_bps is None:
        return chainlink_or_reference, "PREMIUM_UNKNOWN_USE_REFERENCE"
    if abs(premium_bps) > max_dex_weight_bps:
        return chainlink_or_reference, "DEX_EXCLUDED_PREMIUM_EXCEEDS_THRESHOLD"
    center = (chainlink_or_reference + dex_twap) / 2
    return center, "SYNTHESIZED_WEIGHTED_MEDIAN"


def stock_entry_gate(*, session: str, health_flags: Sequence[str],
                     premium_band: str, corp_action_state: str,
                     reference: ReferenceValue,
                     multiplier_agreement: str) -> tuple[bool, list[str]]:
    """Conjunction of the stock entry gates (PRD §10.2 / §11 / §9.5).

    Returns ``(allowed, reasons)``.  Every failing gate is recorded — the
    check does NOT short-circuit, so a caller sees all reasons at once.
    The first version only admits ``session == "RTH"``.
    """
    reasons: list[str] = []
    if session != "RTH":
        reasons.append(f"SESSION_NOT_RTH: {session}")
    if health_flags:
        reasons.append("HEALTH_FLAGS: " + ",".join(health_flags))
    if premium_band != "NORMAL":
        reasons.append(f"PREMIUM_BAND_NOT_NORMAL: {premium_band}")
    if corp_action_state != "NORMAL":
        reasons.append(f"CORP_ACTION_NOT_NORMAL: {corp_action_state}")
    ok, why = exit_quote_required(reference)
    if not ok:
        reasons.append(why)  # "INPUTS_UNAVAILABLE: EXIT_QUOTE"
    if multiplier_agreement != "AGREE":
        reasons.append(f"MULTIPLIER_DISAGREEMENT: {multiplier_agreement}")
    return len(reasons) == 0, reasons


def quote_freshness(*, generated_at, now,
                    max_age_secs: int = 60,
                    future_tolerance_secs: int = 5) -> tuple[str, int]:
    """Return ``(status, age_secs)`` using the server-side ``generatedAt``.

    Both ``generated_at`` and ``now`` accept an RFC3339 string (including the
    9-digit fractional-seconds form the price API returns, e.g.
    ``2026-09-08T08:53:41.707033470Z``) or an aware datetime; normalization
    reuses ``lp_rh_market_session_v1_readonly._to_dt`` (import, not rewrite).
    ``generated_at is None`` -> ``("UNKNOWN", -1)``.  Ages from
    ``-future_tolerance_secs`` through ``max_age_secs`` are FRESH; ages below
    ``-future_tolerance_secs`` are INVALID because time runs in the wrong
    direction; older ages are STALE.  The default 5-second future tolerance
    accommodates normal second-level NTP drift and server/local clock
    differences, but an hour-scale difference is not normal.  The age is
    measured from the server ``generatedAt``, never the local fetch time
    (PRD §8.1).
    """
    if generated_at is None:
        return "UNKNOWN", -1
    gen_dt = _to_dt(generated_at, "generated_at")
    now_dt = _to_dt(now, "now")
    age_secs = int((now_dt - gen_dt).total_seconds())
    if age_secs < -future_tolerance_secs:
        return "INVALID", age_secs
    if age_secs <= max_age_secs:
        return "FRESH", age_secs
    return "STALE", age_secs


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Offline replay: compute premium bands + freshness for each symbol.

    ``--quotes-json`` maps symbol -> {reference_price, generated_at};
    ``--pool-prices-json`` maps symbol -> {dex_price}.  No network.
    """
    parser = argparse.ArgumentParser(
        description="RH-05d premium guard + stock entry gate (offline)")
    parser.add_argument("--quotes-json", required=True)
    parser.add_argument("--pool-prices-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--now", default=None,
                        help="RFC3339 now (default: generated_at of first quote)")
    args = parser.parse_args(argv)

    with open(args.quotes_json, "r", encoding="utf-8") as f:
        quotes = json.load(f)
    with open(args.pool_prices_json, "r", encoding="utf-8") as f:
        pool_prices = json.load(f)

    now_raw = args.now
    if now_raw is None:
        first = next(iter(quotes.values()))
        now_raw = first.get("generated_at")

    results = {}
    for symbol, q in quotes.items():
        ref = q.get("reference_price")
        dex = pool_prices.get(symbol, {}).get("dex_price")
        ref_d = Decimal(ref) if ref is not None else None
        dex_d = Decimal(dex) if dex is not None else None
        bps = premium_bps(dex_price=dex_d, reference_price=ref_d)
        band, allows_recenter = classify_premium(bps)
        if now_raw is None:
            status, age = "UNKNOWN", -1
        else:
            status, age = quote_freshness(
                generated_at=q.get("generated_at"), now=now_raw)
        results[symbol] = {
            "reference_price": ref,
            "dex_price": dex,
            "premium_bps": str(bps) if bps is not None else None,
            "band": band,
            "allows_recenter": allows_recenter,
            "quote_status": status,
            "quote_age_secs": age,
        }

    out = {"calibration_status": CALIBRATION_STATUS, "symbols": results}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
