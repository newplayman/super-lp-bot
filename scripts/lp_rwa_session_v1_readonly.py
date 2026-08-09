#!/usr/bin/env python3
"""Read-only US-equity session classification and RWA shadow recorders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
from typing import TextIO
from zoneinfo import ZoneInfo

from scripts.lp_rwa_instrument_v1_readonly import Instrument, InstrumentValidationError


NEW_YORK = ZoneInfo("America/New_York")

# NYSE full-day closures for the complete 2026 calendar year.
US_MARKET_HOLIDAYS_2026 = frozenset({
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
})
US_MARKET_EARLY_CLOSES_2026 = frozenset({date(2026, 11, 27), date(2026, 12, 24)})


class RwaSession(str, Enum):
    REGULAR = "REGULAR"
    EXTENDED = "EXTENDED"
    OVERNIGHT = "OVERNIGHT"
    PRIMARY_CLOSED = "PRIMARY_CLOSED"
    HALTED = "HALTED"


@dataclass(frozen=True)
class SessionState:
    session: RwaSession
    as_of_new_york: datetime
    shadow_only: bool
    auto_narrow_range: bool = False


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    return value


def classify_us_equity_session(as_of: datetime, *, halted: bool = False) -> SessionState:
    """Classify US equity time using America/New_York (including DST).

    PRIMARY_CLOSED is always shadow-only and never signals automatic range
    narrowing.  The explicit halt input has priority over every calendar rule.
    """

    local = _aware(as_of).astimezone(NEW_YORK)
    if halted:
        return SessionState(RwaSession.HALTED, local, True)
    day, current = local.date(), local.time().replace(tzinfo=None)
    if local.year != 2026:
        raise ValueError("calendar is fail-closed outside explicitly supported year 2026")
    if local.weekday() >= 5 or day in US_MARKET_HOLIDAYS_2026:
        return SessionState(RwaSession.PRIMARY_CLOSED, local, True)

    regular_close = time(13, 0) if day in US_MARKET_EARLY_CLOSES_2026 else time(16, 0)
    if time(9, 30) <= current < regular_close:
        return SessionState(RwaSession.REGULAR, local, False)
    if time(4, 0) <= current < time(9, 30) or regular_close <= current < time(20, 0):
        return SessionState(RwaSession.EXTENDED, local, False)
    # 20:00 Friday starts the weekend; Monday 00:00-04:00 has no Sunday-night
    # underlier session in this conservative state machine.
    if (current >= time(20, 0) and local.weekday() < 4) or (current < time(4, 0) and local.weekday() in {1, 2, 3, 4}):
        return SessionState(RwaSession.OVERNIGHT, local, False)
    return SessionState(RwaSession.PRIMARY_CLOSED, local, True)


def _decimal_string(value: object, name: str) -> str:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return str(result)


def _append_jsonl(sink: TextIO, record: dict[str, object]) -> None:
    if not hasattr(sink, "write"):
        raise TypeError("sink must provide write()")
    sink.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    if hasattr(sink, "flush"):
        sink.flush()


class ShadowBasisLeadLogger:
    """Append-only observation surface with deliberately no scoring API."""

    def __init__(self, sink: TextIO):
        self._sink = sink

    def log(
        self, *, as_of: datetime, instrument_id: str, cex_source: str, dex_source: str,
        cex_price: object, dex_price: object, basis_bps: object, session: RwaSession,
    ) -> dict[str, object]:
        record = {
            "as_of": _aware(as_of).astimezone(timezone.utc).isoformat(),
            "feature_name": "cex_dex_basis_lead",
            "shadow_only": True,
            "instrument_id": str(instrument_id),
            "cex_source": str(cex_source),
            "dex_source": str(dex_source),
            "cex_price": _decimal_string(cex_price, "cex_price"),
            "dex_price": _decimal_string(dex_price, "dex_price"),
            "basis_bps": _decimal_string(basis_bps, "basis_bps"),
            "session": RwaSession(session).value,
        }
        _append_jsonl(self._sink, record)
        return record


class SnapshotRecorder:
    """Minimal injected-I/O JSONL collector for PRD §12.5's 14-day shadow data."""

    def __init__(self, sink: TextIO):
        self._sink = sink

    def append(
        self, *, as_of: datetime, instrument: Instrument, observed_price: object,
        basis_bps: object, source: str,
    ) -> dict[str, object]:
        if not isinstance(instrument, Instrument):
            raise InstrumentValidationError("snapshot instrument must be validated")
        if not source or not str(source).strip():
            raise ValueError("source must be non-empty")
        record = {
            "as_of": _aware(as_of).astimezone(timezone.utc).isoformat(),
            "instrument": instrument.to_mapping(),
            "observed_price": _decimal_string(observed_price, "observed_price"),
            # ``None`` is an explicit fail-closed observation.  In particular,
            # a Robinhood token is a different issuer/instrument from Backed's
            # xStock and therefore must never acquire a direct-basis value.
            "basis_bps": None if basis_bps is None else _decimal_string(basis_bps, "basis_bps"),
            "session": instrument.market_session,
            "source": str(source).strip(),
        }
        _append_jsonl(self._sink, record)
        return record
