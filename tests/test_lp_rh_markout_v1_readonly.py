import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
from decimal import Decimal

import pytest

from scripts import lp_rh_markout_v1_readonly as mark


def _fill(refs, delta_base="1", delta_quote="-1"):
    return {"delta_base": Decimal(delta_base),
            "delta_quote": Decimal(delta_quote), "refs": refs}


def _lookup(fill, window):
    return fill["refs"].get(window)


def test_registered_windows_are_fixed():
    assert mark.PREREGISTERED_WINDOWS == (30, 300, 1800)


def test_markout_formula_uses_both_legs():
    assert mark.markout(delta_base=Decimal("2"), delta_quote=Decimal("-3"),
                        ref_base_usd_future=Decimal("10"),
                        ref_quote_usd_future=Decimal("4")) == Decimal("8")


def test_missing_future_reference_returns_incomplete():
    assert mark.markout(delta_base=Decimal("1"), delta_quote=Decimal("1"),
                        ref_base_usd_future=None,
                        ref_quote_usd_future=Decimal("1")) is None


def test_as_signed_reverses_positive_markout():
    assert mark.as_signed(Decimal("2.5")) == Decimal("-2.5")


def test_as_signed_none_passthrough():
    assert mark.as_signed(None) is None


def test_profile_has_one_value_per_window():
    profile = mark.markout_profile(
        _fill({30: (Decimal("2"), Decimal("1")),
               300: (Decimal("3"), Decimal("1")),
               1800: (Decimal("4"), Decimal("1"))}),
        price_lookup=_lookup)
    assert profile["30"] == Decimal("1")
    assert profile["300"] == Decimal("2")
    assert profile["1800"] == Decimal("3")
    assert profile["incomplete_windows"] == []


def test_t42_profile_does_not_expose_cross_window_total():
    profile = mark.markout_profile(
        _fill({30: (Decimal("2"), Decimal("1")),
               300: (Decimal("3"), Decimal("1")),
               1800: (Decimal("4"), Decimal("1"))}),
        price_lookup=_lookup)
    assert not hasattr(mark, "total_markout")
    assert not hasattr(mark, "sum_all_windows")
    assert set(profile) == {"30", "300", "1800", "incomplete_windows"}


def test_t42_aggregate_is_selected_window_only():
    profiles = [{"30": Decimal("1"), "300": Decimal("2"), "1800": Decimal("3")},
                {"30": Decimal("-1"), "300": Decimal("-4"), "1800": Decimal("0")}]
    at_30 = mark.aggregate(profiles, window=30)
    at_300 = mark.aggregate(profiles, window=300)
    assert at_30["sum"] == Decimal("0")
    assert at_300["sum"] == Decimal("-2")
    assert at_30 != at_300


def test_unregistered_window_is_rejected():
    with pytest.raises(ValueError, match="WINDOW_NOT_PREREGISTERED"):
        mark.aggregate([], window=60)


def test_profile_records_missing_window():
    profile = mark.markout_profile(
        _fill({30: (Decimal("2"), Decimal("1")),
               300: None,
               1800: (Decimal("4"), Decimal("1"))}),
        price_lookup=_lookup)
    assert profile["300"] is None
    assert profile["incomplete_windows"] == [300]


def test_aggregate_counts_incomplete_without_zero_filling():
    profiles = [{"30": Decimal("5")}, {"30": None}, {"30": Decimal("-2")}]
    result = mark.aggregate(profiles, window=30)
    assert result["incomplete_count"] == 1
    assert result["n"] == 2
    assert result["sum"] == Decimal("3")


def test_positive_markout_is_retained_in_net_sum():
    result = mark.aggregate(
        [{"30": Decimal("5")}, {"30": Decimal("-2")}], window=30)
    assert result["positive_count"] == 1
    assert result["negative_count"] == 1
    assert result["sum"] == Decimal("3")


def test_zero_markout_is_neither_positive_nor_negative():
    result = mark.aggregate([{"30": Decimal("0")}], window=30)
    assert result["positive_count"] == 0
    assert result["negative_count"] == 0


def test_lp_share_of_fill_uses_actual_active_liquidity():
    assert mark.lp_share_of_fill(pool_amount=Decimal("100"),
                                 lp_liquidity=Decimal("10"),
                                 active_liquidity=Decimal("100")) == Decimal("10")


def test_lp_share_rejects_nonpositive_active_liquidity():
    with pytest.raises(ValueError, match="ACTIVE_LIQUIDITY_INVALID"):
        mark.lp_share_of_fill(pool_amount=Decimal("100"),
                              lp_liquidity=Decimal("10"),
                              active_liquidity=Decimal("0"))


def test_float_money_is_rejected():
    with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
        mark.markout(delta_base=1.0, delta_quote=Decimal("1"),
                     ref_base_usd_future=Decimal("1"),
                     ref_quote_usd_future=Decimal("1"))


def test_cli_is_offline_and_serializes_decimal_profiles(tmp_path):
    fills = {"fills": [{"delta_base": "1", "delta_quote": "-1",
                         "future_refs": {
                             "30": {"base": "2", "quote": "1"},
                             "300": {"base": "3", "quote": "1"},
                             "1800": {"base": "4", "quote": "1"}}}]}
    source = tmp_path / "fills.json"
    output = tmp_path / "out.json"
    source.write_text(json.dumps(fills), encoding="utf-8")
    assert mark.main(["--fills-json", str(source), "--out", str(output)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["profiles"][0]["30"] == "1"
    assert result["aggregates"]["300"]["sum"] == "2"
