from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from decimal import Decimal

from scripts import lp_rh_premium_guard_v1_readonly as pg
from scripts.lp_rh_stock_reference_v1_readonly import ReferenceValue

_NOW = datetime(2026, 9, 8, 8, 53, 41, tzinfo=timezone.utc)


def _ref(exit_bid):
    """A ReferenceValue with an optional executable exit bid."""
    return ReferenceValue(
        reference_bid=Decimal("100.0"),
        reference_ask=Decimal("100.1"),
        reference_mid=Decimal("100.05"),
        executable_exit_bid_for_position_size=exit_bid,
        reference_age_secs=3,
        quote_age_secs=3,
        source_quality="REST",
    )


_GOOD_REF = _ref(Decimal("99.9"))
_BAD_REF = _ref(None)


def _gate(**overrides):
    kwargs = dict(session="RTH", health_flags=[], premium_band="NORMAL",
                  corp_action_state="NORMAL", reference=_GOOD_REF,
                  multiplier_agreement="AGREE")
    kwargs.update(overrides)
    return pg.stock_entry_gate(**kwargs)


# --- regression: six real data points (REFERENCE_PRICE_AND_PREMIUM_20260908) ---
# (symbol, reference, dex, stated_bps).  Five reconcile within +/-5 bps.
REGRESSION = [
    ("SGOV", "100.99", "101.36", 37),
    ("GLD", "402.75", "405.35", 65),
    ("SPY", "766.98", "768.86", 24),
    ("QQQ", "717.36", "718.78", 20),
    ("NVDA", "230.43", "231.11", 30),
]
_AMC = ("AMC", "2.64", "2.6142", -90)


@pytest.mark.parametrize("symbol,ref,dex,stated", REGRESSION)
def test_regression_premium_bps_within_5bps(symbol, ref, dex, stated):
    bps = pg.premium_bps(dex_price=Decimal(dex),
                         reference_price=Decimal(ref))
    assert bps is not None
    assert abs(bps - Decimal(stated)) <= Decimal(5)


def test_regression_amc_premium_bps():
    # The report states -90 bps, but its table rounds the reference to 2.64.
    # The precise value from (2.6142 - 2.64) / 2.64 * 10000 is -97.73, so the
    # stated -90 is a rounding artifact, not a formula error.  Assert the
    # formula's precise value; the band is still NORMAL (|97.73| <= 100).
    bps = pg.premium_bps(dex_price=Decimal("2.6142"),
                         reference_price=Decimal("2.64"))
    assert bps is not None
    assert abs(bps - Decimal("-97.73")) <= Decimal("0.05")


def test_regression_all_six_classify_normal():
    for symbol, ref, dex, _ in REGRESSION + [_AMC]:
        bps = pg.premium_bps(dex_price=Decimal(dex),
                             reference_price=Decimal(ref))
        band, _ = pg.classify_premium(bps)
        assert band == "NORMAL", (symbol, band)


# --- band thresholds --------------------------------------------------------
def test_classify_150bps_reduce_size():
    band, allows = pg.classify_premium(Decimal(150))
    assert band == "REDUCE_SIZE"
    assert allows is False  # stricter: only NORMAL allows recenter (PRD §13.2)


def test_classify_400bps_no_new_widen_remove_eval():
    band, allows = pg.classify_premium(Decimal(400))
    assert band == "NO_NEW_WIDEN_REMOVE_EVAL"
    assert allows is False  # NO_NEW forbids recenter (PRD §10.2 / §13.2)


def test_classify_800bps_dislocation_no_recenter():
    band, allows = pg.classify_premium(Decimal(800))
    assert band == "DISLOCATION"
    assert allows is False  # PRD §11: DISLOCATION forbids recentering


# --- edge cases -------------------------------------------------------------
def test_reference_zero_returns_none_not_zero():
    bps = pg.premium_bps(dex_price=Decimal("101.36"),
                         reference_price=Decimal(0))
    assert bps is None  # a zero reference is UNKNOWN, never 0


def test_premium_bps_none_when_either_missing():
    assert pg.premium_bps(dex_price=None,
                          reference_price=Decimal("100")) is None
    assert pg.premium_bps(dex_price=Decimal("100"),
                          reference_price=None) is None


def test_classify_none_unknown():
    assert pg.classify_premium(None) == ("UNKNOWN", False)


# --- range center: DEX may never drive it (PRD §11) -------------------------
def test_range_center_excludes_dex_when_premium_high():
    ref = Decimal("100.0")
    # 150 bps premium on a 100.0 reference -> dex ~ 101.5.
    dex = Decimal("101.5")
    bps = pg.premium_bps(dex_price=dex, reference_price=ref)
    center, reason = pg.range_center(chainlink_or_reference=ref, dex_twap=dex,
                                     premium_bps=bps)
    assert reason == "DEX_EXCLUDED_PREMIUM_EXCEEDS_THRESHOLD"
    assert center == ref  # DEX fully excluded; center stays on the reference


def test_range_center_includes_dex_when_premium_low():
    ref = Decimal("100.0")
    # 50 bps premium on a 100.0 reference -> dex = 100.5.
    dex = Decimal("100.5")
    bps = pg.premium_bps(dex_price=dex, reference_price=ref)
    center, reason = pg.range_center(chainlink_or_reference=ref, dex_twap=dex,
                                     premium_bps=bps)
    assert reason == "SYNTHESIZED_WEIGHTED_MEDIAN"
    assert center == (ref + dex) / 2  # DEX participates, does not dominate


# --- allows_recenter: True ONLY for NORMAL (FAIL-2) -------------------------
@pytest.mark.parametrize("bps,band,allows", [
    (Decimal(50), "NORMAL", True),
    (Decimal(150), "REDUCE_SIZE", False),
    (Decimal(400), "NO_NEW_WIDEN_REMOVE_EVAL", False),
    (Decimal(800), "DISLOCATION", False),
    (None, "UNKNOWN", False),
])
def test_allows_recenter_only_normal(bps, band, allows):
    got_band, got_allows = pg.classify_premium(bps)
    assert got_band == band
    assert got_allows is allows


# --- quote_freshness: RFC3339 string + aware datetime (FAIL-1) -------------
def test_freshness_nine_digit_nanosecond_string():
    # Real /rhj/prices generatedAt carries 9 fractional digits (nanoseconds);
    # quote_freshness must accept it without crashing (FAIL-1 regression).
    gen = "2026-09-08T08:53:41.707033470Z"
    now = (datetime(2026, 9, 8, 8, 53, 41, 707033, tzinfo=timezone.utc)
           + timedelta(seconds=3))
    status, age = pg.quote_freshness(generated_at=gen, now=now)
    assert status == "FRESH"
    assert age == 3


def test_freshness_string_matches_datetime():
    gen_str = "2026-09-08T08:53:41.707033470Z"
    gen_dt = datetime(2026, 9, 8, 8, 53, 41, 707033, tzinfo=timezone.utc)
    now = datetime(2026, 9, 8, 8, 53, 44, 707033, tzinfo=timezone.utc)
    assert pg.quote_freshness(generated_at=gen_str, now=now) == \
        pg.quote_freshness(generated_at=gen_dt, now=now) == ("FRESH", 3)


def test_freshness_3s_fresh():
    gen = _NOW - timedelta(seconds=3)
    status, age = pg.quote_freshness(generated_at=gen, now=_NOW)
    assert status == "FRESH"
    assert age == 3


def test_freshness_120s_stale():
    gen = _NOW - timedelta(seconds=120)
    status, age = pg.quote_freshness(generated_at=gen, now=_NOW)
    assert status == "STALE"
    assert age == 120


def test_freshness_none_unknown():
    status, age = pg.quote_freshness(generated_at=None, now=_NOW)
    assert (status, age) == ("UNKNOWN", -1)


# --- stock_entry_gate: each gate rejects independently (no short-circuit) ---
def test_gate_reject_session_not_rth():
    allowed, reasons = _gate(session="ETH")
    assert allowed is False
    assert any("SESSION_NOT_RTH" in r for r in reasons)


def test_gate_reject_health_flags():
    allowed, reasons = _gate(health_flags=["ORACLE_PAUSED"])
    assert allowed is False
    assert any("HEALTH_FLAGS" in r for r in reasons)


def test_gate_reject_premium_not_normal():
    allowed, reasons = _gate(premium_band="REDUCE_SIZE")
    assert allowed is False
    assert any("PREMIUM_BAND_NOT_NORMAL" in r for r in reasons)


def test_gate_reject_corp_action_not_normal():
    allowed, reasons = _gate(corp_action_state="SUSPECT")
    assert allowed is False
    assert any("CORP_ACTION_NOT_NORMAL" in r for r in reasons)


def test_gate_reject_no_exit_quote():
    allowed, reasons = _gate(reference=_BAD_REF)
    assert allowed is False
    assert any("EXIT_QUOTE" in r for r in reasons)


def test_gate_reject_multiplier_disagreement():
    allowed, reasons = _gate(multiplier_agreement="DISAGREE")
    assert allowed is False
    assert any("MULTIPLIER_DISAGREEMENT" in r for r in reasons)


def test_gate_all_pass():
    allowed, reasons = _gate()
    assert allowed is True
    assert reasons == []


# --- calibration status: thresholds are NOT validated ----------------------
def test_calibration_status_not_calibrated():
    # PRD/B2 Shadow initial values, not calibrated against live data; they
    # must never be treated as validated thresholds.
    assert pg.CALIBRATION_STATUS == "SHADOW_INITIAL_NOT_CALIBRATED"


