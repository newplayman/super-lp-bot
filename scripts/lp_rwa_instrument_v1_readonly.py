#!/usr/bin/env python3
"""Strict, pure-data RWA instrument normalization (INV-RWA-01).

The nine-field :class:`Instrument` describes what a price means.  The numeric
price deliberately lives in :class:`PriceObservation`, so serialization of the
required schema cannot silently omit any identity or semantics field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Mapping


BASE_DIVERGENCE_THRESHOLD_BPS = Decimal("40")
DEFAULT_MAX_SOURCE_AGE_SECONDS = Decimal("45")

PRICE_SEMANTICS = frozenset({"underlying", "token", "bid", "ask", "mid", "nav"})
MARKET_SESSIONS = frozenset({"REGULAR", "EXTENDED", "OVERNIGHT", "PRIMARY_CLOSED", "HALTED"})
REDEMPTION_STATUSES = frozenset({"OPEN", "CLOSED", "PAUSED", "PENDING", "UNAVAILABLE", "UNKNOWN"})


class InstrumentValidationError(ValueError):
    """The observation is unsafe for normalized basis calculation."""


def _decimal(value: object, field: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise InstrumentValidationError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InstrumentValidationError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise InstrumentValidationError(f"{field} must be finite")
    if positive and result <= 0:
        raise InstrumentValidationError(f"{field} must be > 0")
    if nonnegative and result < 0:
        raise InstrumentValidationError(f"{field} must be >= 0")
    return result


def _text(value: object, field: str, *, uppercase: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstrumentValidationError(f"{field} must be a non-empty string")
    result = value.strip()
    return result.upper() if uppercase else result


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InstrumentValidationError("source_timestamp must be ISO-8601") from exc
    else:
        raise InstrumentValidationError("source_timestamp must be datetime or ISO-8601 string")
    if result.tzinfo is None or result.utcoffset() is None:
        raise InstrumentValidationError("source_timestamp must include timezone")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Instrument:
    """The exact nine fields mandated by PRD v2.1 §4.2."""

    FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "instrument_id", "issuer", "underlying_ticker", "quote_currency", "multiplier",
        "price_semantics", "source_timestamp", "market_session", "redemption_status",
    )

    instrument_id: str
    issuer: str
    underlying_ticker: str
    quote_currency: str
    multiplier: Decimal
    price_semantics: str
    source_timestamp: datetime
    market_session: str
    redemption_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", _text(self.instrument_id, "instrument_id"))
        object.__setattr__(self, "issuer", _text(self.issuer, "issuer"))
        object.__setattr__(self, "underlying_ticker", _text(self.underlying_ticker, "underlying_ticker", uppercase=True))
        object.__setattr__(self, "quote_currency", _text(self.quote_currency, "quote_currency", uppercase=True))
        object.__setattr__(self, "multiplier", _decimal(self.multiplier, "multiplier", positive=True))
        semantics = _text(self.price_semantics, "price_semantics").lower()
        if semantics not in PRICE_SEMANTICS:
            raise InstrumentValidationError(f"unsupported price_semantics: {semantics}")
        object.__setattr__(self, "price_semantics", semantics)
        object.__setattr__(self, "source_timestamp", _timestamp(self.source_timestamp))
        session = _text(self.market_session, "market_session", uppercase=True)
        if session not in MARKET_SESSIONS:
            raise InstrumentValidationError(f"unsupported market_session: {session}")
        object.__setattr__(self, "market_session", session)
        redemption = _text(self.redemption_status, "redemption_status", uppercase=True)
        if redemption not in REDEMPTION_STATUSES:
            raise InstrumentValidationError(f"unsupported redemption_status: {redemption}")
        object.__setattr__(self, "redemption_status", redemption)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "Instrument":
        if not isinstance(raw, Mapping):
            raise InstrumentValidationError("instrument must be a mapping")
        missing = set(cls.FIELD_NAMES) - set(raw)
        if missing:
            raise InstrumentValidationError(f"missing instrument fields (stale): {sorted(missing)}")
        unknown = set(raw) - set(cls.FIELD_NAMES)
        if unknown:
            raise InstrumentValidationError(f"unknown instrument fields: {sorted(unknown)}")
        return cls(**{name: raw[name] for name in cls.FIELD_NAMES})

    def to_mapping(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "issuer": self.issuer,
            "underlying_ticker": self.underlying_ticker,
            "quote_currency": self.quote_currency,
            "multiplier": str(self.multiplier),
            "price_semantics": self.price_semantics,
            "source_timestamp": self.source_timestamp.isoformat(),
            "market_session": self.market_session,
            "redemption_status": self.redemption_status,
        }

    @property
    def economic_identity(self) -> tuple[str, str, str]:
        return self.issuer.casefold(), self.instrument_id.casefold(), self.underlying_ticker


@dataclass(frozen=True)
class PriceObservation:
    instrument: Instrument
    price: Decimal
    source_name: str = "unknown"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise InstrumentValidationError("instrument must be an Instrument")
        object.__setattr__(self, "price", _decimal(self.price, "price", positive=True))
        object.__setattr__(self, "source_name", _text(self.source_name, "source_name"))


@dataclass(frozen=True)
class NormalizedQuote:
    instrument: Instrument
    normalized_price: Decimal
    observed_price: Decimal
    source_name: str


def normalize_quote(
    observation: PriceObservation,
    *,
    now: datetime,
    max_age_seconds: object = DEFAULT_MAX_SOURCE_AGE_SECONDS,
) -> NormalizedQuote:
    """Normalize a token-equivalent price to one underlying share and reject stale/future data."""

    if not isinstance(observation, PriceObservation):
        raise InstrumentValidationError("quote must be a PriceObservation")
    current = _timestamp(now)
    age = Decimal(str((current - observation.instrument.source_timestamp).total_seconds()))
    max_age = _decimal(max_age_seconds, "max_age_seconds", positive=True)
    if age < 0:
        raise InstrumentValidationError("source_timestamp is in the future")
    if age > max_age:
        raise InstrumentValidationError(f"stale quote: source age {age}s exceeds {max_age}s")
    return NormalizedQuote(
        instrument=observation.instrument,
        normalized_price=observation.price / observation.instrument.multiplier,
        observed_price=observation.price,
        source_name=observation.source_name,
    )


def basis(left: NormalizedQuote, reference: NormalizedQuote) -> Decimal:
    """Absolute normalized basis; incompatible instruments fail closed."""

    if not isinstance(left, NormalizedQuote) or not isinstance(reference, NormalizedQuote):
        raise InstrumentValidationError("basis accepts normalized quotes only")
    li, ri = left.instrument, reference.instrument
    compatibility = (
        li.economic_identity == ri.economic_identity
        and li.quote_currency == ri.quote_currency
        and li.price_semantics == ri.price_semantics
        and li.market_session == ri.market_session
    )
    if not compatibility:
        raise InstrumentValidationError("incompatible normalized instruments for direct basis")
    return abs(left.normalized_price - reference.normalized_price) / reference.normalized_price


def divergence_threshold(*, spread_bps: object, sigma_short_bps: object, source_age_seconds: object) -> Decimal:
    """Return ``max(40bps, spread, volatility × age factor)`` in basis points."""

    spread = _decimal(spread_bps, "spread_bps", nonnegative=True)
    sigma = _decimal(sigma_short_bps, "sigma_short_bps", nonnegative=True)
    age = _decimal(source_age_seconds, "source_age_seconds", nonnegative=True)
    volatility_buffer = sigma * (Decimal("1") + age / DEFAULT_MAX_SOURCE_AGE_SECONDS)
    return max(BASE_DIVERGENCE_THRESHOLD_BPS, spread, volatility_buffer)

