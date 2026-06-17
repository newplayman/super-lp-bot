import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_tier_b_baseline_v2_readonly import (
    age_days,
    apr_from_window,
    fee_apr_multi,
    is_sustained,
    passes_tier_b_refined,
)


def test_apr_from_window_matches_expected_range():
    apr = apr_from_window(5, 133_263_196, 24, 8_481_774)
    assert 280.0 < apr < 295.0


def test_apr_from_window_tvl_zero_is_zero():
    assert apr_from_window(5, 100, 24, 0) == 0.0


def test_fee_apr_multi_keys_and_floats():
    out = fee_apr_multi(5, 12345, 23456, 34567, 45678)
    assert set(out.keys()) == {"apr_h1", "apr_h6", "apr_h24"}
    assert all(isinstance(v, float) for v in out.values())


def test_is_sustained_cases():
    assert is_sustained(100, 120, 110, max_ratio=3.0) is True
    assert is_sustained(900, 100, 300, max_ratio=3.0) is False
    assert is_sustained(100, 0, 0, max_ratio=3.0) is False


def test_age_days_happy_path_and_bad_path():
    val = age_days("2024-05-06T05:03:45Z", "2026-06-11T03:17:32Z")
    assert val > 700.0
    assert age_days("not-a-date", "also-bad") == -1.0


def test_passes_tier_b_refined_logic():
    good = passes_tier_b_refined(
        200.0,
        2_000_000.0,
        400.0,
        1.0,
        True,
        tvl_min=100_000,
        age_min_days=7,
        move_max_pct=25,
    )
    assert good is True

    assert (
        passes_tier_b_refined(
            200.0,
            50_000.0,
            400.0,
            1.0,
            True,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is False
    )
    assert (
        passes_tier_b_refined(
            200.0,
            2_000_000.0,
            1.0,
            1.0,
            True,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is False
    )
    assert (
        passes_tier_b_refined(
            200.0,
            2_000_000.0,
            400.0,
            30.0,
            True,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is False
    )
    assert (
        passes_tier_b_refined(
            200.0,
            2_000_000.0,
            400.0,
            1.0,
            False,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is False
    )
    assert (
        passes_tier_b_refined(
            80.0,
            2_000_000.0,
            400.0,
            1.0,
            True,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is True
    )
    assert (
        passes_tier_b_refined(
            800.0,
            2_000_000.0,
            400.0,
            1.0,
            True,
            tvl_min=100_000,
            age_min_days=7,
            move_max_pct=25,
        )
        is False
    )
