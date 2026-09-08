#!/usr/bin/env python3
"""Tests for lp_rh_in_range_v1_readonly (RH-04e: in-range duration conversion).

Offline: samples are constructed in-memory (no network, no wallets, no chain
writes).  Money amounts and ratios are Decimal.  One test reads the live
scanner.db read-only for a real-data regression (skipped if absent).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_in_range_v1_readonly import (
    effective_fee_ev,
    in_range_fraction,
    range_scan,
    tick_from_price,
)

DEC0, DEC1 = 18, 6
CENTER = -198160  # main-brain measured current tick (price ~2490.58)
_T0 = datetime(2026, 9, 8, 0, 0, 0)


def price_at_tick(tick: int, dec0: int = DEC0, dec1: int = DEC1) -> float:
    """Human/decimals-normalised price at a given tick (inverse of the module)."""
    return (1.0001 ** tick) * (10 ** (dec0 - dec1))


def _ts(i: int, step: int = 15) -> str:
    return (_T0 + timedelta(seconds=step * i)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def make_samples(ticks, step: int = 15):
    """Build [{"sample_time","reference_mid"}] from a list of ticks (None ok)."""
    out = []
    for i, tick in enumerate(ticks):
        mid = None if tick is None else str(price_at_tick(tick))
        out.append({"sample_time": _ts(i, step), "reference_mid": mid})
    return out


def test_tick_from_price_precision_normalised():
    # Main-brain measured tick=-198160 for price 2490.58 at 18/6.  A correct
    # implementation lands in [-198200, -198100]; one that skips the precision
    # scaling lands near +78207 and MUST fail here.
    t = tick_from_price(Decimal("2490.58"), dec0=18, dec1=6)
    assert -198200 <= t <= -198100


def test_tick_from_price_roundtrip():
    for tick in (-198160, -198260, -197960, -200160, -196160):
        price = price_at_tick(tick)
        assert tick_from_price(Decimal(str(price)), dec0=DEC0, dec1=DEC1) == tick


def test_all_in_range():
    r = in_range_fraction(make_samples([CENTER] * 5),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert r["fraction"] == Decimal(1)
    assert r["in_range_samples"] == 5
    assert r["excursions"] == []


def test_all_out_range():
    r = in_range_fraction(make_samples([CENTER - 200] * 4),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert r["fraction"] == Decimal(0)
    assert len(r["excursions"]) == 1
    assert r["excursions"][0]["side"] == "BELOW"


def test_half_in_half_out():
    ticks = [CENTER, CENTER - 200, CENTER, CENTER - 200,
             CENTER, CENTER - 200, CENTER, CENTER - 200]
    r = in_range_fraction(make_samples(ticks),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert r["fraction"] == Decimal("0.5")


def test_below_side():
    r = in_range_fraction(make_samples([CENTER, CENTER - 300, CENTER - 300, CENTER]),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert len(r["excursions"]) == 1
    assert r["excursions"][0]["side"] == "BELOW"


def test_above_side():
    r = in_range_fraction(make_samples([CENTER, CENTER + 300, CENTER + 300, CENTER]),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert len(r["excursions"]) == 1
    assert r["excursions"][0]["side"] == "ABOVE"


def test_multiple_excursions_count_and_durations():
    # IN, OUT,OUT,OUT, IN, IN, OUT,OUT, IN  (step=15s)
    ticks = [CENTER,
             CENTER - 200, CENTER - 200, CENTER - 200,
             CENTER, CENTER,
             CENTER + 200, CENTER + 200,
             CENTER]
    r = in_range_fraction(make_samples(ticks),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert len(r["excursions"]) == 2
    assert r["excursions"][0]["side"] == "BELOW"
    assert r["excursions"][0]["duration_secs"] == 30.0  # t1 -> t3
    assert r["excursions"][1]["side"] == "ABOVE"
    assert r["excursions"][1]["duration_secs"] == 15.0  # t6 -> t7
    assert r["in_range_samples"] == 4
    assert r["fraction"] == Decimal(4) / Decimal(9)


def test_none_samples_skipped_not_out_of_range():
    # 10 samples: 3 None, 7 in-range.  fraction denominator is 7, not 10.
    ticks = [CENTER, None, CENTER, None, CENTER, CENTER,
             None, CENTER, CENTER, CENTER]
    r = in_range_fraction(make_samples(ticks),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert r["total_samples"] == 10
    assert r["skipped"] == 3
    assert r["in_range_samples"] == 7
    assert r["fraction"] == Decimal(1)
    assert r["excursions"] == []


def test_in_range_fraction_return_keys():
    r = in_range_fraction(make_samples([CENTER]),
                          tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert set(r) == {"total_samples", "in_range_samples", "fraction",
                      "first", "last", "skipped", "excursions"}
    assert r["first"] == r["last"] == _ts(0)
    assert isinstance(r["fraction"], Decimal)


def test_empty_samples():
    r = in_range_fraction([], tick_lower=CENTER - 100, tick_upper=CENTER + 100,
                          dec0=DEC0, dec1=DEC1)
    assert r["total_samples"] == 0
    assert r["fraction"] == Decimal(0)
    assert r["first"] is None and r["last"] is None
    assert r["excursions"] == []


def test_effective_fee_ev_basic():
    ev = effective_fee_ev(full_range_fee_ev=Decimal("100"),
                          in_range_fraction=Decimal("0.5"),
                          concentration_multiplier=Decimal("4"))
    assert ev == Decimal("200")


def test_effective_fee_ev_none_inputs():
    base = dict(full_range_fee_ev=Decimal("100"),
                in_range_fraction=Decimal("0.5"),
                concentration_multiplier=Decimal("4"))
    for key in base:
        args = dict(base)
        args[key] = None
        assert effective_fee_ev(**args) is None  # None, not 0


def test_range_scan_monotonic_non_decreasing():
    # A wider symmetric range contains every narrower one, so the in-range
    # fraction can only stay the same or grow as width increases.
    ticks = [CENTER + off for off in (-150, 0, 120, -60, 0, 90, -30)]
    rows = range_scan(make_samples(ticks), center_tick=CENTER,
                      widths_ticks=[50, 100, 500, 2000], dec0=DEC0, dec1=DEC1)
    fracs = [row["fraction"] for row in rows]
    assert all(a <= b for a, b in zip(fracs, fracs[1:]))
    assert [row["width_ticks"] for row in rows] == [50, 100, 500, 2000]
    for row in rows:
        assert row["tick_lower"] == CENTER - row["width_ticks"]
        assert row["tick_upper"] == CENTER + row["width_ticks"]


def test_range_scan_keys():
    rows = range_scan(make_samples([CENTER]), center_tick=CENTER,
                      widths_ticks=[100], dec0=DEC0, dec1=DEC1)
    assert set(rows[0]) == {"width_ticks", "tick_lower", "tick_upper",
                            "fraction", "excursion_count"}


def test_real_data_regression():
    db = REPO_ROOT / "reports" / "lp_rh" / "scanner.db"
    if not db.exists():
        pytest.skip("live scanner.db not present")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sample_time, reference_mid FROM rh_market_states "
            "ORDER BY sample_time DESC LIMIT 500").fetchall()
    finally:
        con.close()
    samples = [{"sample_time": r[0], "reference_mid": r[1]} for r in rows][::-1]
    assert len(samples) >= 100
    out = range_scan(samples, center_tick=CENTER,
                     widths_ticks=[100, 500, 2000], dec0=DEC0, dec1=DEC1)
    fracs = [row["fraction"] for row in out]
    # Monotonic non-decreasing in width ...
    assert fracs[0] <= fracs[1] <= fracs[2]
    # ... and the wide range strictly beats the narrow one on this data.
    assert fracs[2] > fracs[0]
