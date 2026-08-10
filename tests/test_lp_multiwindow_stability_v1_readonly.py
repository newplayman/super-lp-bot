"""Pure tests for multi-window stability (no network)."""
import math
from scripts.lp_multiwindow_stability_v1_readonly import (
    DEFAULT_N_WINDOWS,
    STABLE_MIN_FRAC,
    assess_pool,
    stability_summary,
    classify_stability,
)


def test_stability_summary_basic():
    s = stability_summary([1.0, 2.0, 3.0])
    assert s["n"] == 3 and abs(s["mean"] - 2.0) < 1e-9
    assert s["min"] == 1.0 and s["max"] == 3.0 and s["std"] > 0


def test_stability_summary_skips_none_and_empty():
    s = stability_summary([None, 2.0, None])
    assert s["n"] == 1 and s["mean"] == 2.0
    e = stability_summary([])
    assert e["n"] == 0 and e["mean"] is None and e["cv"] is None


def test_stability_summary_handles_inf():
    s = stability_summary([1.0, math.inf, 3.0])
    # inf excluded from mean/std but counted in n and max
    assert s["n"] == 3 and s["max"] == math.inf and not math.isinf(s["mean"])


def test_classify_stability_fraction_and_flag():
    st = classify_stability([1.2, 1.5, 0.4, 2.0, 1.1, 0.9])  # 4/6
    assert st["n_enter"] == 4 and st["stable"] is False
    st2 = classify_stability([1.2, 1.5, 1.1, 2.0, 1.1, 1.3])  # 6/6
    assert st2["stable"] is True and st2["enter_frac"] == 1.0


def test_classify_stability_inf_counts_and_empty():
    st = classify_stability(["inf", 2.0, 0.5])
    assert st["n_enter"] == 2
    assert classify_stability([])["stable"] is False


def test_classify_threshold_tunable():
    covers = [1.4, 1.6, 1.2, 0.9, 1.1, 1.3]
    loose = classify_stability(covers, threshold=1.0, min_frac=0.7)
    strict = classify_stability(covers, threshold=1.5, min_frac=0.7)
    assert loose["stable"] is True and strict["stable"] is False


def test_default_ten_windows_restore_literal_seventy_percent_boundary():
    assert DEFAULT_N_WINDOWS == 10
    assert STABLE_MIN_FRAC == 0.7
    exactly_seven = [1.0] * 7 + [0.0] * 3
    only_six = [1.0] * 6 + [0.0] * 4
    assert classify_stability(exactly_seven)["stable"] is True
    assert classify_stability(exactly_seven)["enter_frac"] == 0.7
    assert classify_stability(only_six)["stable"] is False


def test_ten_window_assessment_retains_same_batch_six_window_counterfactual():
    covers = iter([1.1] * 4 + [0.9] * 2 + [1.1] * 3 + [0.9])

    def fetch_pool_swaps(*_args):
        return [next(covers)]

    live = {
        "fetch_pool_swaps": fetch_pool_swaps,
        "hourly_closes": lambda swaps: swaps,
        "daily_vol_from_closes": lambda _closes: (0.01, 1),
        "efficiency_ratio": lambda _prices: 0.2,
        "recommend_range_pct": lambda *_args: 5.0,
        "replay": lambda swaps, *_args, **_kwargs: {
            "fees_quote": swaps[0], "il_quote": 1.0,
        },
        "fee_cover_ratio": lambda fees, il: fees / il,
    }
    result = assess_pool(
        live,
        {"pool": "0xpool", "dec0": 6, "dec1": 18, "fee_tier": 0.003},
        1.0,
        10,
        1_000_000,
    )
    decision = result["fee_cover_stability"]
    assert decision["same_batch_former_n_enter"] == 4
    assert decision["same_batch_former_enter_frac"] == 0.667
    assert decision["same_batch_former_stable"] is False
    assert decision["n_enter"] == 7
    assert decision["enter_frac"] == 0.7
    assert decision["stable"] is True
