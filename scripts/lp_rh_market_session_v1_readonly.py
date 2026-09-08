#!/usr/bin/env python3
"""RH-02b: market session + health classification (two independent dimensions).

Pure, offline logic.  ``classify_session`` returns a Session
(RTH/PREMARKET/POSTMARKET/OVERNIGHT/CLOSED_WEEKDAY/WEEKEND/HOLIDAY/UNKNOWN);
``evaluate_health`` returns a sorted list of HealthFlags (HALT, CORP_ACTION,
ORACLE_PAUSED, ORACLE_UNAVAILABLE, ORACLE_STALE, API_STALE,
SOURCE_DISAGREEMENT, CHAIN_DEGRADED).
Session and HealthFlags are two independent return values, never merged into
one enum (PRD §9.4).  Timezone conversion uses stdlib ``zoneinfo`` (no
hand-rolled UTC offsets).  No network, no collection, no writes to
``reports/lp_rh/``.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CALENDAR_VERSION = "nyse-2026-v1"
_ET = ZoneInfo("America/New_York")

# Full NYSE closure days for 2026 (date -> label).
HOLIDAYS = {
    "2026-01-01": "NEW_YEAR",
    "2026-01-19": "MARTIN_LUTHER_KING_JR_DAY",
    "2026-02-16": "WASHINGTONS_BIRTHDAY",
    "2026-04-03": "GOOD_FRIDAY",
    "2026-05-25": "MEMORIAL_DAY",
    "2026-06-19": "JUNETEENTH",
    "2026-07-04": "INDEPENDENCE_DAY",
    "2026-09-07": "LABOR_DAY",
    "2026-11-26": "THANKSGIVING",
    "2026-12-25": "CHRISTMAS_DAY",
}

# Early-close days for 2026 (13:00 ET close); still trading days, not closures.
EARLY_CLOSE_DAYS = {"2026-07-03", "2026-11-27", "2026-12-24"}

SESSIONS = ("RTH", "PREMARKET", "POSTMARKET", "OVERNIGHT",
            "CLOSED_WEEKDAY", "WEEKEND", "HOLIDAY", "UNKNOWN")
HEALTH_FLAGS = ("HALT", "CORP_ACTION", "ORACLE_PAUSED", "ORACLE_UNAVAILABLE",
                "ORACLE_STALE", "API_STALE", "SOURCE_DISAGREEMENT",
                "CHAIN_DEGRADED")

_PREMARKET_START = time(4, 0)
_RTH_START = time(9, 30)
_RTH_END_NORMAL = time(16, 0)
_RTH_END_EARLY = time(13, 0)
_POSTMARKET_END = time(20, 0)


def _weekday_session(t: time, is_early_close: bool) -> str:
    rth_end = _RTH_END_EARLY if is_early_close else _RTH_END_NORMAL
    if t < _PREMARKET_START:
        return "OVERNIGHT"
    if t < _RTH_START:
        return "PREMARKET"
    if t < rth_end:
        return "RTH"
    if t < _POSTMARKET_END:
        return "POSTMARKET"
    return "OVERNIGHT"


def classify_session(dt_utc: Optional[datetime], *,
                     calendar: Optional[dict] = None) -> tuple[str, dict]:
    """Classify a UTC instant into a market session (independent of health).

    Returns ``(session, info)`` where ``info`` carries the calendar version,
    the ET-local ISO timestamp, and whether the day is an early-close day.
    """
    if calendar is None:
        calendar = HOLIDAYS
    if dt_utc is None:
        return "UNKNOWN", {"calendar_version": CALENDAR_VERSION,
                           "et_local": None, "is_early_close": False}
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    et_local = dt_utc.astimezone(_ET)
    date_str = et_local.date().isoformat()
    is_early_close = date_str in EARLY_CLOSE_DAYS
    if et_local.weekday() >= 5:  # Sat=5, Sun=6
        session = "WEEKEND"
    elif date_str in calendar:
        session = "HOLIDAY"
    else:
        session = _weekday_session(et_local.time(), is_early_close)
    info = {"calendar_version": CALENDAR_VERSION,
            "et_local": et_local.isoformat(), "is_early_close": is_early_close}
    return session, info


def _to_dt(value, field: str) -> Optional[datetime]:
    """Coerce an RFC3339 string or aware datetime to an aware datetime.

    ``None`` passes through as ``None``.  A naive datetime raises
    ``ValueError("NAIVE_DATETIME: <field>")``; a string that fails to parse
    as ISO-8601 or carries no UTC offset raises
    ``ValueError("NON_UTC_TIMESTAMP: <field>")``.  This mirrors the storage
    layer, which stores UTC RFC3339 strings (RH-02a).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"NAIVE_DATETIME: {field}")
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"NON_UTC_TIMESTAMP: {field}") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"NON_UTC_TIMESTAMP: {field}")
        return parsed
    raise ValueError(f"NON_UTC_TIMESTAMP: {field}")


def evaluate_health(*, oracle_paused, oracle_updated_at, api_generated_at,
                    now, halt, corp_action_pending, sources_disagree,
                    chain_degraded, oracle_heartbeat_secs: int = 3600,
                    api_stale_secs: int = 300) -> list[str]:
    """Return a sorted list of active health flags (independent of session).

    ``oracle_updated_at`` / ``api_generated_at`` / ``now`` each accept an
    RFC3339 string or an aware datetime (see ``_to_dt``).  A ``None``
    ``oracle_updated_at`` means the chain has no oracle to read (structural,
    not transient) and raises ``ORACLE_UNAVAILABLE``; a present-but-old
    oracle raises ``ORACLE_STALE``.  The two are mutually exclusive.  A
    ``None`` ``api_generated_at`` still raises ``API_STALE``.
    """
    now_dt = _to_dt(now, "now")
    oracle_dt = _to_dt(oracle_updated_at, "oracle_updated_at")
    api_dt = _to_dt(api_generated_at, "api_generated_at")
    flags = set()
    if halt:
        flags.add("HALT")
    if corp_action_pending:
        flags.add("CORP_ACTION")
    if oracle_paused:
        flags.add("ORACLE_PAUSED")
    if oracle_dt is None:
        # No oracle on this chain (structural) -> UNAVAILABLE, not STALE.
        flags.add("ORACLE_UNAVAILABLE")
    elif (now_dt - oracle_dt).total_seconds() > oracle_heartbeat_secs:
        flags.add("ORACLE_STALE")
    if api_dt is None:
        flags.add("API_STALE")
    elif (now_dt - api_dt).total_seconds() > api_stale_secs:
        flags.add("API_STALE")
    if sources_disagree:
        flags.add("SOURCE_DISAGREEMENT")
    if chain_degraded:
        flags.add("CHAIN_DEGRADED")
    return sorted(flags)


def stale_reason(session: str, oracle_age_secs: Optional[float],
                 heartbeat_secs: Optional[int]) -> str:
    """Why the oracle is stale: unavailable vs. closed vs. live-but-stale vs. fresh.

    Both the closed and live-but-stale cases block new narrow ranges, but the
    reason must be reported separately (PRD §9.4).  A missing oracle age
    (``oracle_age_secs is None``) or missing heartbeat threshold
    (``heartbeat_secs is None``) is reported as ``ORACLE_UNAVAILABLE``.  That
    check runs first, before the session check, because "no oracle" is
    independent of which session it is (a chain with no oracle is unavailable
    in RTH just as in POSTMARKET).
    """
    if oracle_age_secs is None or heartbeat_secs is None:
        return "ORACLE_UNAVAILABLE"
    if session != "RTH":
        return "EXPECTED_SESSION_CLOSED"
    if oracle_age_secs > heartbeat_secs:
        return "STALE_WHILE_EXPECTED_LIVE"
    return "FRESH"


def allows_new_position(session: str, flags: list[str]) -> bool:
    """Initial LIVE policy (PRD §10.2): only RTH with no health flags."""
    return session == "RTH" and not flags


def _self_test() -> None:
    cases = [
        ("2026-09-07 14:30 UTC (Labor Day)",
         datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc)),
        ("2026-03-08 14:35 UTC (DST start)",
         datetime(2026, 3, 8, 14, 35, tzinfo=timezone.utc)),
        ("2026-11-01 14:35 UTC (DST end)",
         datetime(2026, 11, 1, 14, 35, tzinfo=timezone.utc)),
        ("2026-11-27 18:30 UTC (early close)",
         datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc)),
    ]
    for label, dt in cases:
        session, info = classify_session(dt)
        print(f"{label} -> {session} (et_local={info['et_local']}, "
              f"early_close={info['is_early_close']})")
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    flags = evaluate_health(oracle_paused=False, oracle_updated_at=now,
                            api_generated_at=now, now=now, halt=False,
                            corp_action_pending=False, sources_disagree=False,
                            chain_degraded=False)
    print("evaluate_health(all fresh) ->", flags)
    print("stale_reason(RTH, age=7200, hb=3600) ->",
          stale_reason("RTH", 7200, 3600))
    print("allows_new_position(RTH, []) ->", allows_new_position("RTH", []))
    session, _ = classify_session(datetime(2026, 9, 7, 14, 30,
                                           tzinfo=timezone.utc))
    assert session == "HOLIDAY", session
    print("SESSION_SELF_TEST_OK")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-02b market session + health classification (offline)")
    parser.add_argument("--self-test", action="store_true",
                        help="run built-in self-test and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
