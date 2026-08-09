import math
from pathlib import Path

import pytest

from scripts.lp_m0n_income_validation_v1_readonly import (
    EXPECTED_AS_OF,
    EXPECTED_DB_SHA256,
    EXPECTED_LOGICAL_CONTENT_SHA256,
    HORIZONS,
    THEORETICAL_H720_H168_RATIO,
    _m0f_old_income_terms,
    before_after,
    build_report,
    load_locked_scores,
    ratio_assertion,
    select_samples,
)


DB = Path("reports/lp_funnel_rerank/20260809_135500/scanner.db")


def _curve(fee_ratio: float, reward_ratio: float | None):
    return [
        {"horizon_hours": HORIZONS[0], "fee_ev_usd": 1.0,
         "reward_ev_usd": 2.0 if reward_ratio is not None else 0.0},
        {"horizon_hours": HORIZONS[1], "fee_ev_usd": 1.4,
         "reward_ev_usd": 2.8 if reward_ratio is not None else 0.0},
        {"horizon_hours": HORIZONS[2], "fee_ev_usd": fee_ratio,
         "reward_ev_usd": 2.0 * reward_ratio if reward_ratio is not None else 0.0},
    ]


def test_ratio_assertion_checks_sqrt_shape_and_never_computes_zero_over_zero():
    reward_curve = _curve(
        THEORETICAL_H720_H168_RATIO, THEORETICAL_H720_H168_RATIO,
    )
    assert ratio_assertion(
        reward_curve, "fee_ev_usd", reward_bearing=True,
    )["ratio_status"] == "PASS"
    assert ratio_assertion(
        reward_curve, "reward_ev_usd", reward_bearing=True,
    )["ratio_status"] == "PASS"

    no_reward = ratio_assertion(
        _curve(THEORETICAL_H720_H168_RATIO, None),
        "reward_ev_usd",
        reward_bearing=False,
    )
    assert no_reward["observed_h720_h168_ratio"] is None
    assert no_reward["ratio_status"] == "N/A_ZERO_REWARD"

    linear = ratio_assertion(
        _curve(720.0 / 168.0, 720.0 / 168.0),
        "fee_ev_usd",
        reward_bearing=True,
    )
    inverse_sqrt = ratio_assertion(
        _curve(math.sqrt(168.0 / 720.0), 1.0),
        "fee_ev_usd",
        reward_bearing=True,
    )
    assert linear["ratio_status"] == "FAIL"
    assert inverse_sqrt["ratio_status"] == "FAIL"


def _selection_item(
    pool: str,
    group: str,
    *,
    shape: str,
    il720: float,
    suspect: bool = False,
):
    return {
        "pool": pool,
        "reward_group": group,
        "fully_calculable_all_horizons": True,
        "identity_locked": True,
        "suspect_flags": ["SUSPECT"] if suspect else [],
        "ratio_assertions": [
            {"ratio_status": "PASS"},
            {"ratio_status": "PASS" if group == "REWARD" else "N/A_ZERO_REWARD"},
        ],
        "curve": [{}, {}, {"il_ev_usd": il720}],
        "curve_shape": {
            "observed_shape": shape,
            "fixed_cost_usd_entry_exit_gas_slippage": 1.0,
        },
    }


def test_selection_prefers_internal_optimum_and_excludes_suspect_rows():
    inventory = [
        _selection_item(
            "0x" + "1" * 40, "REWARD",
            shape="MONOTONIC_DECREASING_ON_GRID", il720=100.0,
        ),
        _selection_item(
            "0x" + "2" * 40, "REWARD",
            shape="INTERNAL_OPTIMUM_AT_336H", il720=2.0,
        ),
        _selection_item(
            "0x" + "3" * 40, "REWARD",
            shape="INTERNAL_OPTIMUM_AT_336H", il720=999.0, suspect=True,
        ),
        _selection_item(
            "0x" + "4" * 40, "NO_REWARD",
            shape="MONOTONIC_INCREASING_ON_GRID", il720=1.0,
        ),
    ]
    selected = select_samples(inventory, minimum_each=1)
    assert selected["REWARD"][0]["pool"] == "0x" + "2" * 40
    assert selected["NO_REWARD"][0]["pool"] == "0x" + "4" * 40


def test_m0f_old_formula_is_independent_of_corrected_income_values():
    score = {"reward_apr": 20.0}
    corrected = {
        "fee_capture_share_ratio": 0.5,
        "fee_capture_evidence_apr_pct": 10.0,
        "fee_capture_haircut": 0.4,
        "horizon_hours": 720.0,
        # These values must not be consumed by the old-formula reconstruction.
        "fee_ev_usd": 999999.0,
        "reward_ev_usd": 999999.0,
    }
    old_fee, old_reward = _m0f_old_income_terms(score, corrected)
    assert old_fee == pytest.approx(50.0 * 0.10 * 0.4 * (168.0 / 8760.0) * 0.5)
    assert old_reward == pytest.approx(50.0 * 0.20 * (720.0 / 8760.0))


def test_locked_snapshot_inventory_selection_and_before_after_are_reproducible():
    report = build_report(
        DB, EXPECTED_DB_SHA256, EXPECTED_AS_OF, EXPECTED_LOGICAL_CONTENT_SHA256,
    )
    assert report["verdict"] == "PASS"
    assert report["inventory_summary"] == {
        "total": 47,
        "fully_calculable_all_horizons": 27,
        "fully_calculable_reward": 24,
        "fully_calculable_no_reward": 3,
    }
    assert len(report["selected_samples"]["REWARD"]) == 3
    assert len(report["selected_samples"]["NO_REWARD"]) == 3
    assert report["source"]["canonical_logical_content_sha256_observed"] == (
        EXPECTED_LOGICAL_CONTENT_SHA256
    )

    comparisons = {item["symbol"]: item for item in report["before_after"]}
    usdt = comparisons["USDC-USDT"]["curve"]
    vvv = comparisons["USDC-VVV"]["curve"]
    assert usdt[0]["m0f_old"]["netcover"] == pytest.approx(
        usdt[0]["m0n_n1_corrected"]["netcover"]
    )
    assert usdt[-1]["mechanical_change_factors"][
        "corrected_fee_over_old_fee"
    ] == pytest.approx(720.0 / 168.0)
    assert usdt[-1]["mechanical_change_factors"][
        "corrected_reward_over_old_reward"
    ] == pytest.approx(usdt[-1]["share_ratio"])
    assert vvv[-1]["mechanical_change_factors"][
        "corrected_fee_over_old_fee"
    ] == pytest.approx(720.0 / 168.0)
    assert vvv[-1]["mechanical_change_factors"][
        "corrected_reward_over_old_reward"
    ] is None


def test_locked_snapshot_rejects_wrong_physical_or_logical_digest():
    with pytest.raises(ValueError, match="source DB SHA-256 mismatch"):
        load_locked_scores(DB, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="canonical logical content SHA-256 mismatch"):
        load_locked_scores(
            DB,
            expected_sha256=EXPECTED_DB_SHA256,
            expected_logical_sha256="0" * 64,
        )
