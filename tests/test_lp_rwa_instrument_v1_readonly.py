"""INV-RWA-01 contracts for strict RWA instrument normalization."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from scripts.lp_rwa_instrument_v1_readonly import (
    BASE_DIVERGENCE_THRESHOLD_BPS,
    Instrument,
    InstrumentValidationError,
    NormalizedQuote,
    PriceObservation,
    basis,
    divergence_threshold,
    normalize_quote,
)


NOW = datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc)


def _instrument(**overrides):
    values = {
        "instrument_id": "backed:AAPLx",
        "issuer": "Backed",
        "underlying_ticker": "AAPL",
        "quote_currency": "USD",
        "multiplier": "1",
        "price_semantics": "mid",
        "source_timestamp": NOW.isoformat(),
        "market_session": "REGULAR",
        "redemption_status": "OPEN",
    }
    values.update(overrides)
    return Instrument.from_mapping(values)


def test_schema_is_exact_nine_fields_and_strictly_typed():
    instrument = _instrument()
    assert tuple(instrument.to_mapping()) == (
        "instrument_id", "issuer", "underlying_ticker", "quote_currency",
        "multiplier", "price_semantics", "source_timestamp", "market_session",
        "redemption_status",
    )
    assert instrument.multiplier == Decimal("1")
    assert instrument.source_timestamp == NOW


@pytest.mark.parametrize("missing", list(Instrument.FIELD_NAMES))
def test_every_missing_field_is_rejected_as_stale(missing):
    raw = _instrument().to_mapping()
    del raw[missing]
    with pytest.raises(InstrumentValidationError, match="missing"):
        Instrument.from_mapping(raw)


def test_unknown_fields_and_naive_timestamp_fail_closed():
    raw = _instrument().to_mapping()
    raw["price"] = "123"
    with pytest.raises(InstrumentValidationError, match="unknown"):
        Instrument.from_mapping(raw)
    with pytest.raises(InstrumentValidationError, match="timezone"):
        _instrument(source_timestamp="2026-08-07T15:00:00")


def test_stale_quote_is_rejected_before_basis():
    quote = PriceObservation(_instrument(source_timestamp=(NOW - timedelta(seconds=46)).isoformat()), "100")
    with pytest.raises(InstrumentValidationError, match="stale"):
        normalize_quote(quote, now=NOW)


def test_semantics_session_quote_and_economic_identity_must_match():
    left = normalize_quote(PriceObservation(_instrument(), "100"), now=NOW)
    variants = (
        _instrument(price_semantics="ask"),
        _instrument(market_session="EXTENDED"),
        _instrument(quote_currency="EUR"),
        _instrument(issuer="Robinhood", instrument_id="robinhood:AAPL"),
    )
    for candidate in variants:
        right = normalize_quote(PriceObservation(candidate, "100"), now=NOW)
        with pytest.raises(InstrumentValidationError, match="incompatible"):
            basis(left, right)


def test_split_multiplier_normalization_keeps_basis_continuous():
    before = normalize_quote(PriceObservation(_instrument(multiplier="1"), "100"), now=NOW)
    after = normalize_quote(PriceObservation(_instrument(multiplier="0.5"), "50"), now=NOW)
    assert isinstance(before, NormalizedQuote)
    assert before.normalized_price == after.normalized_price == Decimal("100")
    assert basis(before, after) == Decimal("0")


def test_dynamic_threshold_has_hard_40bps_floor():
    assert BASE_DIVERGENCE_THRESHOLD_BPS == Decimal("40")
    assert divergence_threshold(spread_bps="2", sigma_short_bps="3", source_age_seconds=0) == Decimal("40")


def test_dynamic_threshold_uses_spread_buffer_when_larger():
    assert divergence_threshold(spread_bps="71", sigma_short_bps="3", source_age_seconds=0) == Decimal("71")


def test_dynamic_threshold_volatility_buffer_grows_with_age():
    fresh = divergence_threshold(spread_bps="1", sigma_short_bps="30", source_age_seconds=0)
    aged = divergence_threshold(spread_bps="1", sigma_short_bps="30", source_age_seconds=30)
    assert fresh == Decimal("40")
    assert aged > fresh
