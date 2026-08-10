import json
import math

import pytest

from scripts.lp_lvr_coefficient_calibration_v1_readonly import (
    COEFFICIENTS,
    replay_window,
    sensitivity_rows,
    sqrt_price_from_log,
)


def test_decodes_shared_v3_algebra_sqrt_price_word():
    sqrt_price = 123456789
    words = [0, 0, sqrt_price, 999, 0, 1, 2]
    log = {"data": "0x" + "".join(f"{word:064x}" for word in words)}
    assert sqrt_price_from_log(log) == sqrt_price


def test_replay_separates_endpoint_il_from_path_lvr():
    q96 = 2**96
    # Price goes 1 -> 1.21 -> 1: endpoint IL is zero but path LVR is positive.
    result = replay_window([q96, int(q96 * 1.1), q96])
    assert result["endpoint_il_per_initial_usd"] == pytest.approx(0.0)
    assert result["approx_lvr_per_initial_usd"] > 0.0
    assert result["approx_lvr_to_endpoint_il"] is None


def test_replay_monotone_path_matches_normalized_endpoint_formulas():
    q96 = 2**96
    result = replay_window([q96, int(q96 * math.sqrt(1.21))])
    assert result["terminal_return"] == pytest.approx(1.21)
    assert result["endpoint_il_per_initial_usd"] == pytest.approx(0.005)
    # One discrete rebalance only: rebalanced portfolio and HODL coincide.
    assert result["approx_lvr_per_initial_usd"] == pytest.approx(0.005)
    assert result["approx_lvr_to_endpoint_il"] == pytest.approx(1.0)


def test_sensitivity_is_fail_closed_and_never_changes_threshold():
    base = {
        "risk_usd": 3.5,  # IL=1, old LVR=.5, fixed costs=2
        "expected_net_yield_usd": -0.5,  # adjusted income=3
        "il_ev_usd": 1.0,
        "lvr_ev_usd": 0.5,
        "netcover_ratio": 3.0 / 3.5,
        "entry_eligible": True,
        "gates": {
            "status_ok": True,
            "quality": True,
            "yield_cover": True,
            "stable": True,
            "position_cap": True,
        },
    }
    unavailable = {**base, "risk_usd": None}
    rows = sensitivity_rows([base, unavailable])
    assert tuple(row["lvr_coefficient"] for row in rows) == COEFFICIENTS
    assert all(row["universe_count"] == 2 for row in rows)
    assert all(row["fail_closed_unavailable_count"] == 1 for row in rows)
    assert rows[0]["netcover_max"] == pytest.approx(1.0)
    assert rows[0]["netcover_pass_count"] == 1
    assert rows[0]["terminal_accept_count"] == 1
    assert all(row["netcover_pass_count"] == 0 for row in rows[1:])
    baseline = next(row for row in rows if row["lvr_coefficient"] == 0.5)
    assert baseline["baseline_reproduction_max_abs_error"] == pytest.approx(0.0)
