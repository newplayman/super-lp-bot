#!/usr/bin/env python3
"""RH-02L: reference-price freshness resolution (downstream adjudication only).

User decision 2026-09-09: accept the REST ``generatedAt`` as a freshness
basis, with two conditions -- (1) the single-source data risk must be
recorded explicitly in the attestation, and (2) fail closed the moment the
REST feed is lost.  This module builds ONLY the downstream adjudication
capability; it does not wire into ``lp_rh_market_session_v1_readonly.py``
(that is the next package).  Pure and offline: no network, no writes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Optional

# Measured REST quote age is 15-20 seconds; take a 3x margin.  This is an
# empirical constant, not an arbitrary one.
MAX_REST_AGE_SECS = 60

# A timestamp more than this far in the future means the server clock is
# untrustworthy; do not pass (fail closed).
FUTURE_TOLERANCE_SECS = 5

AUTHORIZED_BY = "user-decision-20260909"


def _to_aware_utc(value: datetime) -> datetime:
    """Coerce a datetime to aware UTC; naive datetimes are assumed UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_generated_at(value) -> Optional[datetime]:
    """Parse a REST ``generatedAt`` into an aware UTC datetime.

    Accepts an ISO-8601 string (including nanosecond 9-decimal fractional
    seconds, e.g. ``"2026-09-09T12:00:00.123456789Z"``), an ``int``/``float``
    epoch-seconds value, or a ``datetime``.  Sub-second precision is preserved
    to microsecond granularity.  Anything unparseable returns ``None`` -- it
    NEVER returns ``now``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return _to_aware_utc(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _result(source, age_secs, verdict, single_source_risk, reasons) -> dict:
    return {"source": source, "age_secs": age_secs, "verdict": verdict,
            "single_source_risk": single_source_risk, "reasons": list(reasons)}


def resolve_freshness(*, oracle_updated_at, api_generated_at, now,
                      max_rest_age_secs: int = MAX_REST_AGE_SECS,
                      oracle_heartbeat_secs: int = 36) -> dict:
    """Resolve which reference-price source is fresh enough to trust.

    Returns ``{"source", "age_secs", "verdict", "single_source_risk",
    "reasons"}`` where ``source`` is one of ``ONCHAIN_ORACLE`` /
    ``REST_GENERATED_AT`` / ``NONE`` and ``verdict`` is one of ``FRESH`` /
    ``STALE`` / ``UNAVAILABLE``.

    Priority: a fresh on-chain oracle wins (verifiable by anyone, so no
    single-source risk).  Otherwise fall back to the REST ``generatedAt``
    (single-source risk, recorded explicitly).  If neither source is usable
    the result fails closed (``NONE`` / ``UNAVAILABLE``).
    """
    now_dt = parse_generated_at(now)
    if now_dt is None:
        raise ValueError("now must be a parseable timestamp")
    oracle_dt = parse_generated_at(oracle_updated_at)
    rest_dt = parse_generated_at(api_generated_at)

    # 1) On-chain oracle: usable only if present and within heartbeat.
    if oracle_dt is not None:
        oracle_age = (now_dt - oracle_dt).total_seconds()
        if oracle_age < -FUTURE_TOLERANCE_SECS:
            return _result("NONE", None, "UNAVAILABLE", False,
                           ["FUTURE_TIMESTAMP"])
        if oracle_age <= oracle_heartbeat_secs:
            return _result("ONCHAIN_ORACLE", oracle_age, "FRESH", False, [])

    # 2) REST generatedAt fallback.
    if rest_dt is not None:
        rest_age = (now_dt - rest_dt).total_seconds()
        if rest_age < -FUTURE_TOLERANCE_SECS:
            return _result("NONE", None, "UNAVAILABLE", False,
                           ["FUTURE_TIMESTAMP"])
        if rest_age <= max_rest_age_secs:
            return _result("REST_GENERATED_AT", rest_age, "FRESH", True, [])
        return _result("REST_GENERATED_AT", rest_age, "STALE", True,
                       ["REST_OVER_AGE"])

    # 3) No usable source: fail closed.
    return _result("NONE", None, "UNAVAILABLE", False, ["NO_USABLE_SOURCE"])


def build_attestation(resolution, *, now, chain_id, endpoint) -> dict:
    """Build the attestation record for a freshness resolution.

    ``single_source_risk`` is True iff the source is ``REST_GENERATED_AT``.
    ``fail_closed_on_loss`` is always True (user condition 2).
    """
    source = resolution["source"]
    attested_dt = parse_generated_at(now)
    return {
        "single_source_risk": source == "REST_GENERATED_AT",
        "source": source,
        "age_secs": resolution["age_secs"],
        "verdict": resolution["verdict"],
        "endpoint": endpoint,
        "chain_id": chain_id,
        "authorized_by": AUTHORIZED_BY,
        "fail_closed_on_loss": True,
        "attested_at": attested_dt.isoformat() if attested_dt is not None
        else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-02L reference-price freshness resolution (offline)")
    parser.add_argument("--resolution-json", required=True,
                        help="path to JSON: {resolution, now, chain_id, endpoint}")
    parser.add_argument("--out",
                        help="write the attestation JSON here (omit to print)")
    args = parser.parse_args(argv)
    with open(args.resolution_json, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    resolution = payload["resolution"]
    attestation = build_attestation(
        resolution, now=payload.get("now"),
        chain_id=payload.get("chain_id"), endpoint=payload.get("endpoint"))
    text = json.dumps(attestation, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
