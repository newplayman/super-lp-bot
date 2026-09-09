#!/usr/bin/env python3
"""Tests for the RH coverage audit & gap attribution module (offline/read-only)."""
import sqlite3
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_coverage_audit_v1_readonly import (  # noqa: E402
    ALLOWED_REMEDIATION,
    analyze_gaps,
    attribute_gaps,
    coverage_verdict,
    evaluation_window_coverage,
    coverage_by_asset,
    coverage_for_asset,
    NO_ASSET_DATA,
)

BASE = datetime(2026, 9, 8, 5, 15, 14)


def iso(offsets):
    """Turn second-offsets (from BASE) into ISO sample_time strings."""
    return [(BASE + timedelta(seconds=o)).isoformat() + "Z" for o in offsets]


def offsets_from_intervals(intervals):
    offs = [0.0]
    for iv in intervals:
        offs.append(offs[-1] + iv)
    return offs


def _gap(start_off, end_off, duration):
    return {"start": iso([start_off])[0], "end": iso([end_off])[0],
            "duration_secs": duration, "missed_samples": int(round(duration / 15))}


# --- analyze_gaps: denominator & drift ---

def test_denominator_is_planned_window():
    # 10 samples spanning exactly 1 hour at a 15s plan -> 240 planned, not 10.
    offs = [i * 400 for i in range(10)]  # span = 9 * 400 = 3600s
    a = analyze_gaps(iso(offs), expected_interval_secs=15)
    assert a["total_samples"] == 10
    assert a["expected_samples"] == 240  # denominator is the planned window
    assert a["coverage_ratio"] == Decimal(10) / Decimal(240)
    assert round(float(a["coverage_ratio"]), 3) == 0.042


def test_systematic_drift_no_gaps():
    # Median interval 16.5s, no interval exceeds the 22.5s gap threshold.
    a = analyze_gaps(iso(offsets_from_intervals([16.5] * 100)), expected_interval_secs=15)
    assert a["gaps"] == []
    assert a["systematic_drift"] is True
    assert abs(a["drift_secs_per_round"] - 1.5) < 1e-6


def test_analyze_no_drift_when_on_cadence():
    a = analyze_gaps(iso(offsets_from_intervals([15.0] * 100)), expected_interval_secs=15)
    assert a["systematic_drift"] is False
    assert a["drift_secs_per_round"] == 0.0
    assert a["gaps"] == []


def test_three_real_gaps_missed_samples():
    intervals = [15] * 52
    for i in (10, 25, 40):
        intervals[i] = 300  # three 5-minute gaps
    a = analyze_gaps(iso(offsets_from_intervals(intervals)), expected_interval_secs=15)
    assert len(a["gaps"]) == 3
    for g in a["gaps"]:
        assert g["duration_secs"] == 300
        assert g["missed_samples"] == 20


def test_analyze_single_sample_no_crash():
    a = analyze_gaps(iso([0]), expected_interval_secs=15)
    assert a["total_samples"] == 1
    assert a["expected_samples"] == 0
    assert a["gaps"] == []
    assert a["systematic_drift"] is False


# --- attribute_gaps ---

def test_attribute_degraded():
    out = attribute_gaps([_gap(0, 300, 300)],
                         [{"sample_time": iso([150])[0], "state": "DEGRADED"}])
    assert out[0]["attribution"] == "RPC_DEGRADED"


def test_attribute_exit_only():
    out = attribute_gaps([_gap(0, 300, 300)],
                         [{"sample_time": iso([150])[0], "state": "EXIT_ONLY"}])
    assert out[0]["attribution"] == "RPC_EXIT_ONLY"


def test_attribute_unexplained_no_rows():
    out = attribute_gaps([_gap(0, 300, 300)], [])  # no health rows at all
    assert out[0]["attribution"] == "UNEXPLAINED"
    # must NOT be forced into any known class (PRD §8.4)
    assert out[0]["attribution"] not in (
        "RPC_DEGRADED", "RPC_EXIT_ONLY", "PROCESS_RESTART", "SYSTEMATIC_DRIFT")


def test_attribute_process_restart_large_normal():
    health = [{"sample_time": iso([0])[0], "state": "NORMAL"},
              {"sample_time": iso([300])[0], "state": "NORMAL"}]
    out = attribute_gaps([_gap(0, 300, 300)], health)
    assert out[0]["attribution"] == "PROCESS_RESTART"


def test_attribute_systematic_drift_small_normal():
    health = [{"sample_time": iso([0])[0], "state": "NORMAL"},
              {"sample_time": iso([30])[0], "state": "NORMAL"}]
    out = attribute_gaps([_gap(0, 30, 30)], health)
    assert out[0]["attribution"] == "SYSTEMATIC_DRIFT"


# --- coverage_verdict ---

def test_verdict_fail_fix_drift():
    # The 89.9% real-data case: failing + systematic drift -> FIX_DRIFT.
    analysis = {"coverage_ratio": Decimal("0.899"), "total_samples": 1726,
                "expected_samples": 1919, "systematic_drift": True, "gaps": []}
    v = coverage_verdict(analysis)
    assert v["passed"] is False
    assert "FIX_DRIFT" in v["remediation"]
    assert v["shortfall_samples"] == 1919 - 1726


def test_verdict_pass():
    analysis = {"coverage_ratio": Decimal("0.995"), "total_samples": 199,
                "expected_samples": 200, "systematic_drift": False, "gaps": []}
    v = coverage_verdict(analysis)
    assert v["passed"] is True
    assert v["remediation"] == []
    assert v["blockers"] == []


def test_verdict_shortfall_and_extend():
    analysis = {"coverage_ratio": Decimal("0.5"), "total_samples": 100,
                "expected_samples": 200, "systematic_drift": False, "gaps": []}
    v = coverage_verdict(analysis)
    assert v["shortfall_samples"] == 100
    assert v["blockers"] == ["COVERAGE_INSUFFICIENT"]
    # no drift, no unexplained gaps -> the only remedy is to extend observation
    assert v["remediation"] == ["EXTEND_OBSERVATION"]


@pytest.mark.parametrize("ratio,drift,unexplained", [
    ("0.50", False, False),
    ("0.899", True, False),
    ("0.90", False, True),
    ("0.95", True, True),
    ("0.98", False, False),
    ("0.99", False, False),
])
def test_remediation_never_relaxes(ratio, drift, unexplained):
    # For ANY failing ratio the remedy must stay within the three allowed
    # actions -- never a threshold relaxation.
    gaps = [{"attribution": "UNEXPLAINED"}] if unexplained else []
    analysis = {"coverage_ratio": Decimal(ratio), "total_samples": 1,
                "expected_samples": 2, "systematic_drift": drift, "gaps": gaps}
    v = coverage_verdict(analysis)
    assert set(v["remediation"]) <= ALLOWED_REMEDIATION
    if not v["passed"]:
        assert len(v["remediation"]) >= 1


# --- evaluation_window_coverage ---

def test_eval_window_coverage_denominator():
    # 100 actual samples inside a 1-hour window, 240 planned -> 0.417, not 1.0.
    offs = [i * 36 for i in range(100)]  # 100 samples spanning 3564s (< 3600)
    cov = evaluation_window_coverage(
        iso(offs), window_start=iso([0])[0], window_end=iso([3600])[0],
        expected_interval_secs=15)
    assert round(float(cov), 3) == 0.417
    assert cov != Decimal(1)  # would be 1.0 if the denominator were the actual count


def test_eval_window_empty():
    cov = evaluation_window_coverage(
        [], window_start=iso([0])[0], window_end=iso([3600])[0],
        expected_interval_secs=15)
    assert cov == Decimal(0)


def test_eval_window_counts_only_inside():
    # 50 samples inside the window, 50 outside -> only the inside ones count.
    inside = [i * 36 for i in range(50)]            # 0..1764s
    outside = [4000 + i * 36 for i in range(50)]     # all past the 3600s end
    cov = evaluation_window_coverage(
        iso(inside + outside), window_start=iso([0])[0], window_end=iso([3600])[0],
        expected_interval_secs=15)
    assert cov == Decimal(50) / Decimal(240)


# --- real-data regression (COLLECTOR_PERIOD_DRIFT_FIX.md) ---

def test_real_data_regression():
    # 1726 samples / 1919 planned / median interval 16.4s -> coverage ~0.899,
    # systematic drift detected even though the 4 gaps are the only large ones.
    intervals = [16.4] * 1721 + [140.15] * 4  # span -> 28785s, median -> 16.4s
    a = analyze_gaps(iso(offsets_from_intervals(intervals)), expected_interval_secs=15)
    assert a["total_samples"] == 1726
    assert a["expected_samples"] == 1919
    assert round(float(a["coverage_ratio"]), 3) == 0.899
    assert a["systematic_drift"] is True
    assert len(a["gaps"]) == 4


# --- asset-scoped database coverage ---

def _asset_coverage_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rh_market_states ("
        "asset_address TEXT NOT NULL, sample_time TEXT NOT NULL)"
    )
    rows = []
    for asset in ("asset-a", "asset-b"):
        for i in range(116):
            sample_time = BASE + timedelta(seconds=3600 * i / 115)
            rows.append((asset, sample_time.isoformat() + "Z"))
    conn.executemany("INSERT INTO rh_market_states VALUES (?, ?)", rows)
    return conn


def test_asset_coverage_is_independent_and_never_summed():
    conn = _asset_coverage_db()
    try:
        by_asset = coverage_by_asset(
            conn, asset_addresses=("asset-a", "asset-b"),
            expected_interval_secs=15)
        assert set(by_asset) == {"asset-a", "asset-b"}
        for result in by_asset.values():
            assert result["status"] == "OK"
            assert abs(float(result["coverage_ratio"]) - 0.484) < 0.001

        combined = sum(
            (result["coverage_ratio"] for result in by_asset.values()),
            Decimal(0),
        )
        assert all(
            result["coverage_ratio"] != combined
            for result in by_asset.values()
        )
    finally:
        conn.close()


def test_unknown_asset_is_not_zero_coverage():
    conn = _asset_coverage_db()
    try:
        result = coverage_for_asset(
            conn, asset_address="asset-missing", expected_interval_secs=15)
        assert result["status"] == NO_ASSET_DATA
        assert result["message"] == "无该资产数据"
        assert result["coverage_ratio"] is None
        assert result["analysis"] is None
    finally:
        conn.close()


def test_asset_address_is_required():
    conn = _asset_coverage_db()
    try:
        with pytest.raises(TypeError):
            coverage_for_asset(conn, expected_interval_secs=15)
    finally:
        conn.close()
