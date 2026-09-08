from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts import lp_rh_stock_reference_v1_readonly as sr

SNAPSHOT = (Path(__file__).resolve().parents[1]
            / "reports/rh_pivot/20260907T124500Z/RH-05-research"
            / "RH_ASSETS_SNAPSHOT.json")

_NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)


# --- T17: unified model, exact Decimal --------------------------------------
def test_t17_token_quantity_and_shares():
    qty = sr.token_quantity(2 * 10**18, 18)
    assert qty == Decimal("2")
    mult = sr.multiplier_from_raw(1250000000000000000)  # 1.25e18 raw
    assert mult == Decimal("1.25")
    shares = sr.underlying_share_equivalent(qty, mult)
    assert shares == Decimal("2.5")


def test_t17_reference_price_and_total():
    mult = Decimal("1.25")
    price = sr.token_equivalent_price(
        underlying_price_usd=Decimal("100"), multiplier_human=mult,
        source_is_already_token_equivalent=False)
    assert price == Decimal("125")
    total = sr.token_quantity(2 * 10**18, 18) * price
    assert total == Decimal("250")


# --- T18: no double-apply ----------------------------------------------------
def test_t18_already_token_equivalent_no_double_apply():
    price = sr.token_equivalent_price(
        underlying_price_usd=Decimal("125"), multiplier_human=Decimal("1.25"),
        source_is_already_token_equivalent=True)
    assert price == Decimal("125")
    assert price != Decimal("156.25")


# --- T19: USDG normalization -------------------------------------------------
def test_t19_usdg_normalized_price():
    got = sr.usdg_normalized_price(Decimal("125"), Decimal("0.98"))
    assert abs(got - Decimal("127.5510204081632653")) < Decimal("1e-8")


def test_t19_usdg_zero_raises():
    try:
        sr.usdg_normalized_price(Decimal("125"), Decimal("0"))
    except ValueError as e:
        assert str(e) == "USDG_PRICE_INVALID"
    else:
        raise AssertionError("expected ValueError USDG_PRICE_INVALID")


# --- T20: split preserves reference -----------------------------------------
def test_t20_split_preserves_reference_true():
    assert sr.split_preserves_reference(
        before_underlying=Decimal("200"), before_multiplier=Decimal("1"),
        after_underlying=Decimal("20"), after_multiplier=Decimal("10")) is True


def test_t20_split_preserves_reference_false():
    assert sr.split_preserves_reference(
        before_underlying=Decimal("200"), before_multiplier=Decimal("1"),
        after_underlying=Decimal("20"), after_multiplier=Decimal("9")) is False


# --- T21: oracle pause / read failure ---------------------------------------
def test_t21_oracle_paused_blocks():
    state, _ = sr.corp_action_guard(
        current_multiplier="1.0", pending_multiplier="",
        effective_at=None, now=_NOW, oracle_paused=True)
    assert state == "ORACLE_PAUSED"
    assert sr.allows_new_or_recenter(state) is False


def test_t21_oracle_paused_none_unknown():
    state, _ = sr.corp_action_guard(
        current_multiplier="1.0", pending_multiplier="",
        effective_at=None, now=_NOW, oracle_paused=None)
    assert state == "UNKNOWN"
    assert sr.allows_new_or_recenter(state) is False


# --- T22: no fabricated corp action -----------------------------------------
def test_t22_pending_equals_current_normal():
    state, reasons = sr.corp_action_guard(
        current_multiplier="1.000000000000000000",
        pending_multiplier="1.000000000000000000",
        effective_at=None, now=_NOW, oracle_paused=False)
    assert state == "NORMAL"
    assert reasons == []
    assert sr.allows_new_or_recenter(state) is True


# --- T23: stale classification (three values) -------------------------------
def test_t23_stale_session_closed():
    assert sr.stale_classification(
        session="PREMARKET", oracle_age_secs=7200, heartbeat_secs=3600
    ) == "EXPECTED_SESSION_CLOSED"


def test_t23_stale_while_expected_live():
    assert sr.stale_classification(
        session="RTH", oracle_age_secs=7200, heartbeat_secs=3600
    ) == "STALE_WHILE_EXPECTED_LIVE"


def test_t23_fresh():
    assert sr.stale_classification(
        session="RTH", oracle_age_secs=100, heartbeat_secs=3600
    ) == "FRESH"


# --- T24: exit quote ---------------------------------------------------------
def test_t24_exit_quote_unavailable():
    ref = sr.ReferenceValue(
        reference_bid=Decimal("100"), reference_ask=Decimal("101"),
        reference_mid=Decimal("100.5"),
        executable_exit_bid_for_position_size=None,
        reference_age_secs=5, quote_age_secs=5, source_quality="CHAINLINK")
    ok, reason = sr.exit_quote_required(ref)
    assert ok is False
    assert reason == "INPUTS_UNAVAILABLE: EXIT_QUOTE"


# --- CRWD real-data regression (only whole-number split on chain) -----------
def test_crwd_snapshot_regression():
    assets = sr.load_assets_snapshot(SNAPSHOT)
    crwd = assets["CRWD"]
    assert crwd["currentMultiplier"] == "4.000000000000000000"
    mult = sr.multiplier_from_api(crwd["currentMultiplier"])
    p_false = sr.token_equivalent_price(
        underlying_price_usd=Decimal("100"), multiplier_human=mult,
        source_is_already_token_equivalent=False)
    assert p_false == Decimal("400")
    p_true = sr.token_equivalent_price(
        underlying_price_usd=Decimal("100"), multiplier_human=mult,
        source_is_already_token_equivalent=True)
    assert p_true == Decimal("100")


# --- naming + no-float invariants -------------------------------------------
def test_reference_value_named_not_guaranteed():
    assert hasattr(sr, "ReferenceValue")
    assert not hasattr(sr, "GuaranteedFairPrice")


def test_redeem_access_default_not_proven():
    ref = sr.ReferenceValue(
        reference_bid=None, reference_ask=None, reference_mid=None,
        executable_exit_bid_for_position_size=None,
        reference_age_secs=None, quote_age_secs=None, source_quality="X")
    assert ref.redeem_access == "NOT_PROVEN"


def test_no_float_in_source():
    src = (Path(__file__).resolve().parents[1]
           / "scripts/lp_rh_stock_reference_v1_readonly.py").read_text()
    assert not re.search(r"float\(", src)
