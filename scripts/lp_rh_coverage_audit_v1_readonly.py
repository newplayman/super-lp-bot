#!/usr/bin/env python3
"""RH-02d: collection coverage audit & gap attribution (offline, read-only).

PRD §21.1: the coverage denominator is the *planned* observation window, never
the actual sample count (dropping bad windows and reporting 100% is forbidden).
PRD §8.4: an unknown gap stays UNEXPLAINED, never filled with a guessed cause.
No network, no live-store writes (scanner.db is opened read-only).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH, open_store  # noqa: E402

# Gap attribution labels. UNEXPLAINED is a first-class, non-guessable cause
# (PRD §8.4: never fill the unknown with a known label).
RPC_DEGRADED = "RPC_DEGRADED"
RPC_EXIT_ONLY = "RPC_EXIT_ONLY"
PROCESS_RESTART = "PROCESS_RESTART"
SYSTEMATIC_DRIFT = "SYSTEMATIC_DRIFT"
UNEXPLAINED = "UNEXPLAINED"

# rh_rpc_health.state values written by the collector (NORMAL/DEGRADED/EXIT_ONLY).
# These are the *inputs* to attribution; the labels above are the *outputs*.
STATE_DEGRADED = "DEGRADED"
STATE_EXIT_ONLY = "EXIT_ONLY"

# Remediation actions. Deliberately excludes any "relax the threshold" option:
# a shortfall is closed by extending observation, fixing drift, or investigating.
EXTEND_OBSERVATION = "EXTEND_OBSERVATION"
FIX_DRIFT = "FIX_DRIFT"
INVESTIGATE_UNEXPLAINED = "INVESTIGATE_UNEXPLAINED"
ALLOWED_REMEDIATION = frozenset({EXTEND_OBSERVATION, FIX_DRIFT, INVESTIGATE_UNEXPLAINED})


def _to_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 sample_time (with or without a trailing Z)."""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def analyze_gaps(
    sample_times: Sequence[str],
    *,
    expected_interval_secs: int,
    tolerance_ratio: Decimal = Decimal("1.5"),
) -> Dict[str, Any]:
    """Audit a sample timeline against the planned cadence.

    The denominator (``expected_samples``) is the planned window:
    ``span / interval``. A pairwise interval above ``interval * tolerance_ratio``
    is a gap. ``drift_secs_per_round`` is the median interval minus the planned
    interval; a positive drift above 0.5s flags systematic drift even when no
    single gap exists (the 89.9% failure mode).
    """
    pairs: List[tuple] = []
    for s in sample_times:
        dt = _to_dt(s)
        if dt is not None:
            pairs.append((dt, s))
    pairs.sort(key=lambda p: p[0])
    times = [p[0] for p in pairs]
    raw = [p[1] for p in pairs]
    total = len(times)
    if total < 2:
        return {
            "total_samples": total,
            "span_secs": 0.0,
            "expected_samples": 0,
            "coverage_ratio": Decimal(0),
            "gaps": [],
            "drift_secs_per_round": 0.0,
            "systematic_drift": False,
        }
    span_secs = (times[-1] - times[0]).total_seconds()
    expected_samples = int(round(span_secs / expected_interval_secs))
    coverage_ratio = (
        Decimal(total) / Decimal(expected_samples) if expected_samples > 0 else Decimal(0)
    )
    intervals = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    threshold = expected_interval_secs * float(tolerance_ratio)
    gaps: List[Dict[str, Any]] = []
    for i, iv in enumerate(intervals):
        if iv > threshold:
            gaps.append({
                "start": raw[i],
                "end": raw[i + 1],
                "duration_secs": round(iv, 3),
                "missed_samples": int(round(iv / expected_interval_secs)),
            })
    median_iv = statistics.median(intervals)
    drift = median_iv - expected_interval_secs
    return {
        "total_samples": total,
        "span_secs": round(span_secs, 3),
        "expected_samples": expected_samples,
        "coverage_ratio": coverage_ratio,
        "gaps": gaps,
        "drift_secs_per_round": round(drift, 3),
        "systematic_drift": drift > 0.5,
    }


def attribute_gaps(
    gaps: Sequence[Dict[str, Any]],
    health_rows: Sequence[Dict[str, Any]],
    *,
    window_secs: int = 60,
) -> List[Dict[str, Any]]:
    """Align each gap with ``rh_rpc_health`` rows and attribute a cause.

    A row "corresponds" to a gap when its sample_time falls within
    ``[start - window_secs, end + window_secs]``. Priority:
      DEGRADED row -> RPC_DEGRADED; else EXIT_ONLY row -> RPC_EXIT_ONLY;
      else no rows at all -> UNEXPLAINED (never guessed, PRD §8.4);
      else rows are all NORMAL -> SYSTEMATIC_DRIFT for a small gap
      (<= window_secs, drift-sized) or PROCESS_RESTART for a large one.
    """
    rows = []
    for r in health_rows:
        st = _to_dt(r["sample_time"])
        if st is not None:
            rows.append((st.timestamp(), r["state"]))
    out: List[Dict[str, Any]] = []
    for gap in gaps:
        start = _to_dt(gap["start"])
        end = _to_dt(gap["end"])
        lo = start.timestamp() - window_secs
        hi = end.timestamp() + window_secs
        states = {state for (ts, state) in rows if lo <= ts <= hi}
        if STATE_DEGRADED in states:
            cause = RPC_DEGRADED
        elif STATE_EXIT_ONLY in states:
            cause = RPC_EXIT_ONLY
        elif not states:
            cause = UNEXPLAINED
        else:  # rows exist and are all NORMAL
            cause = (
                SYSTEMATIC_DRIFT if gap["duration_secs"] <= window_secs
                else PROCESS_RESTART
            )
        out.append({**gap, "attribution": cause})
    return out


def coverage_verdict(analysis: Dict[str, Any], *, min_ratio: Decimal = Decimal("0.99")) -> Dict[str, Any]:
    """Verdict on coverage. ``remediation`` is always a subset of the three
    allowed actions and never a threshold relaxation."""
    ratio = Decimal(str(analysis["coverage_ratio"]))
    passed = ratio >= min_ratio
    shortfall = max(0, analysis["expected_samples"] - analysis["total_samples"])
    blockers: List[str] = [] if passed else ["COVERAGE_INSUFFICIENT"]
    remediation: List[str] = []
    if not passed:
        if analysis.get("systematic_drift"):
            remediation.append(FIX_DRIFT)
        if any(g.get("attribution") == UNEXPLAINED for g in analysis.get("gaps", [])):
            remediation.append(INVESTIGATE_UNEXPLAINED)
        if not remediation:
            remediation.append(EXTEND_OBSERVATION)
    return {
        "passed": passed,
        "ratio": ratio,
        "shortfall_samples": shortfall,
        "blockers": blockers,
        "remediation": remediation,
    }


def evaluation_window_coverage(
    sample_times: Sequence[str],
    *,
    window_start: Any,
    window_end: Any,
    expected_interval_secs: int,
) -> Decimal:
    """Coverage of the window selected for P&L evaluation (PRD §21.1).

    The denominator is the *planned* sample count for the window
    (``span / interval``), never the actual count inside it.
    """
    ws = _to_dt(window_start)
    we = _to_dt(window_end)
    if ws is None or we is None or we <= ws:
        return Decimal(0)
    planned = Decimal(str((we - ws).total_seconds())) / Decimal(expected_interval_secs)
    if planned <= 0:
        return Decimal(0)
    actual = 0
    for s in sample_times:
        t = _to_dt(s)
        if t is not None and ws <= t <= we:
            actual += 1
    return Decimal(actual) / planned


NO_ASSET_DATA = "NO_ASSET_DATA"


def fetch_asset_sample_times(conn: Any, *, asset_address: str) -> List[str]:
    """Return sample times for exactly one asset.

    ``asset_address`` is intentionally keyword-only and has no default: a
    caller must identify the asset instead of silently auditing all rows.
    Uses case-insensitive comparison to handle EIP-55 checksum or lowercase addresses.
    """
    rows = conn.execute(
        "SELECT sample_time FROM rh_market_states "
        "WHERE LOWER(asset_address) = LOWER(?) ORDER BY sample_time",
        (asset_address,),
    ).fetchall()
    return [row[0] for row in rows]


def _no_asset_data(asset_address: str) -> Dict[str, Any]:
    """Return an explicit result for an asset absent from the store."""
    return {
        "asset_address": asset_address,
        "status": NO_ASSET_DATA,
        "has_data": False,
        "message": "无该资产数据",
        "reason": "no rows in rh_market_states for asset_address",
        "coverage_ratio": None,
        "analysis": None,
        "attributed_gaps": [],
        "verdict": None,
    }


def coverage_for_asset(
    conn: Any,
    *,
    asset_address: str,
    expected_interval_secs: int,
    health_rows: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Audit coverage for exactly one asset.

    The SQL query is asset-scoped. An absent asset is reported as
    ``NO_ASSET_DATA`` rather than being passed to ``analyze_gaps`` as an empty
    timeline, because no row and zero coverage are different states.
    """
    sample_times = fetch_asset_sample_times(conn, asset_address=asset_address)
    if not sample_times:
        return _no_asset_data(asset_address)

    analysis = analyze_gaps(
        sample_times, expected_interval_secs=expected_interval_secs)
    attributed = attribute_gaps(analysis["gaps"], health_rows)
    verdict = coverage_verdict({**analysis, "gaps": attributed})
    return {
        "asset_address": asset_address,
        "status": "OK",
        "has_data": True,
        "coverage_ratio": analysis["coverage_ratio"],
        "analysis": analysis,
        "attributed_gaps": attributed,
        "verdict": verdict,
    }


def coverage_by_asset(
    conn: Any,
    *,
    asset_addresses: Sequence[str],
    expected_interval_secs: int,
    health_rows: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Dict[str, Any]]:
    """Return independent coverage results keyed by asset address.

    Each asset is queried and analyzed separately; sample counts and spans are
    never combined across assets.
    """
    return {
        asset_address: coverage_for_asset(
            conn,
            asset_address=asset_address,
            expected_interval_secs=expected_interval_secs,
            health_rows=health_rows,
        )
        for asset_address in asset_addresses
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH coverage audit & gap attribution (read-only)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH),
                        help="RH scanner.db (read-only)")
    parser.add_argument("--interval-secs", type=int, default=15,
                        help="planned sample interval (s)")
    parser.add_argument("--asset-address", required=True,
                        help="asset address to audit (required; never all assets)")
    parser.add_argument("--out", default="COVERAGE_AUDIT.json",
                        help="output JSON path")
    args = parser.parse_args(argv)
    conn = open_store(args.db, read_only=True)
    try:
        health_rows = [
            {"sample_time": st, "state": state}
            for st, state in conn.execute(
                "SELECT sample_time, state FROM rh_rpc_health ORDER BY sample_time").fetchall()
        ]
        coverage = coverage_for_asset(
            conn,
            asset_address=args.asset_address,
            expected_interval_secs=args.interval_secs,
            health_rows=health_rows,
        )
    finally:
        conn.close()
    report = {
        "db": str(args.db),
        "interval_secs": args.interval_secs,
        **coverage,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
