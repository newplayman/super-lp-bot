"""US equity session, shadow feature, and §12.5 collector contracts."""

from datetime import datetime, timezone
from io import StringIO
import json

from scripts.lp_rwa_instrument_v1_readonly import Instrument
from scripts.lp_rwa_session_v1_readonly import (
    RwaSession,
    ShadowBasisLeadLogger,
    SnapshotRecorder,
    classify_us_equity_session,
)


def _utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _instrument(session="REGULAR"):
    return Instrument.from_mapping({
        "instrument_id": "backed:AAPLx", "issuer": "Backed", "underlying_ticker": "AAPL",
        "quote_currency": "USD", "multiplier": "1", "price_semantics": "mid",
        "source_timestamp": "2026-08-07T15:00:00+00:00", "market_session": session,
        "redemption_status": "OPEN",
    })


def test_saturday_2026_08_08_is_primary_closed_and_shadow():
    state = classify_us_equity_session(_utc("2026-08-08T15:00:00"))
    assert state.session is RwaSession.PRIMARY_CLOSED
    assert state.shadow_only is True
    assert state.auto_narrow_range is False


def test_2026_august_weekday_regular():
    assert classify_us_equity_session(_utc("2026-08-07T15:00:00")).session is RwaSession.REGULAR


def test_2026_august_weekday_premarket_extended():
    assert classify_us_equity_session(_utc("2026-08-07T12:00:00")).session is RwaSession.EXTENDED


def test_2026_august_weekday_after_hours_extended():
    assert classify_us_equity_session(_utc("2026-08-07T21:30:00")).session is RwaSession.EXTENDED


def test_2026_august_weekday_overnight():
    assert classify_us_equity_session(_utc("2026-08-07T05:00:00")).session is RwaSession.OVERNIGHT


def test_2026_market_holiday_is_primary_closed():
    assert classify_us_equity_session(_utc("2026-09-07T15:00:00")).session is RwaSession.PRIMARY_CLOSED


def test_explicit_halt_overrides_time_and_calendar():
    assert classify_us_equity_session(_utc("2026-08-07T15:00:00"), halted=True).session is RwaSession.HALTED


def test_shadow_basis_lead_record_has_no_score_or_decision_surface():
    sink = StringIO()
    record = ShadowBasisLeadLogger(sink).log(
        as_of=_utc("2026-08-07T15:00:01"), instrument_id="backed:AAPLx",
        cex_source="bybit", dex_source="orca", cex_price="100", dex_price="100.2",
        basis_bps="20", session=RwaSession.REGULAR,
    )
    assert record["feature_name"] == "cex_dex_basis_lead"
    assert record["shadow_only"] is True
    assert not ({"score", "enter", "decision", "weight"} & set(record))
    assert json.loads(sink.getvalue()) == record


def test_snapshot_recorder_appends_session_tagged_nine_field_record():
    sink = StringIO()
    recorder = SnapshotRecorder(sink)
    record = recorder.append(
        as_of=_utc("2026-08-07T15:00:01"), instrument=_instrument(),
        observed_price="100.1", basis_bps="12", source="xstocks_official",
    )
    assert record["session"] == "REGULAR"
    assert set(record["instrument"]) == set(Instrument.FIELD_NAMES)
    assert json.loads(sink.getvalue()) == record


def test_snapshot_recorder_is_append_only_for_injected_sink():
    sink = StringIO()
    recorder = SnapshotRecorder(sink)
    for basis_bps in ("1", "2"):
        recorder.append(as_of=_utc("2026-08-07T15:00:01"), instrument=_instrument(),
                        observed_price="100", basis_bps=basis_bps, source="mock")
    assert len(sink.getvalue().splitlines()) == 2


def test_snapshot_recorder_serializes_explicit_unavailable_basis_as_null():
    sink = StringIO()

    record = SnapshotRecorder(sink).append(
        as_of=_utc("2026-08-07T15:00:01"), instrument=_instrument(),
        observed_price="100", basis_bps=None, source="robinhood_stock_token",
    )

    assert record["basis_bps"] is None
    assert json.loads(sink.getvalue())["basis_bps"] is None
