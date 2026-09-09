import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import random

from scripts.lp_rh_premium_series_v1_readonly import (
    lvr_haircut_frac,
    main,
    premium_bps,
    premium_regime,
    regime_confidence,
    series_stats,
)


def make_samples(values, spacing=60, half_spread_bps=Decimal("0.1")):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = []
    for index, value in enumerate(values):
        reference = Decimal("100")
        chain = reference * (Decimal(1) + value / Decimal("10000"))
        timestamp = (start + timedelta(seconds=index * spacing)).isoformat()
        # Carry a realistic bid/ask so the resolution floor is computable.  0.1
        # bps is tight but the right order: SPY measures 0.26 bps live, QQQ 0.28.
        half = reference * half_spread_bps / Decimal("20000")
        samples.append({
            "sample_time": timestamp.replace("+00:00", "Z"),
            "chain_price": chain,
            "reference_price": reference,
            "reference_bid": reference - half,
            "reference_ask": reference + half,
        })
    return samples


def test_premium_bps_positive():
    assert premium_bps(Decimal("101"), Decimal("100")) == Decimal("100")


def test_premium_bps_negative():
    assert premium_bps(Decimal("99"), Decimal("100")) == Decimal("-100")


def test_premium_bps_zero_when_prices_equal():
    assert premium_bps(Decimal("100"), Decimal("100")) == Decimal("0")


def test_premium_bps_missing_chain_is_none():
    assert premium_bps(None, Decimal("100")) is None


def test_premium_bps_missing_reference_is_none():
    assert premium_bps(Decimal("100"), None) is None


def test_premium_bps_zero_reference_is_none():
    assert premium_bps(Decimal("100"), Decimal("0")) is None


def test_premium_bps_zero_chain_is_none():
    assert premium_bps(Decimal("0"), Decimal("100")) is None


def test_sine_series_is_mean_reverting():
    values = [
        Decimal(str(60 * math.sin(2 * math.pi * index / 16)))
        for index in range(120)
    ]
    stats = series_stats(make_samples(values))
    assert stats["status"] == "COMPUTED"
    assert premium_regime(stats) == "MEAN_REVERTING"
    assert stats["half_life_secs"] is not None


def test_persistent_offset_series_is_persistent():
    values = [Decimal(80 + (index % 3) - 1) for index in range(120)]
    stats = series_stats(make_samples(values))
    assert premium_regime(stats) == "PERSISTENT_OFFSET"
    assert stats["zero_crossings"] == 0
    assert stats["sign_stability"] == Decimal(1)


def test_diverging_random_walk_has_no_half_life():
    rng = random.Random(5)
    value = Decimal(1)
    values = []
    for _ in range(120):
        value += Decimal(rng.choice((1, 2, 3)))
        values.append(value)
    stats = series_stats(make_samples(values))
    assert stats["half_life_secs"] is None


def test_insufficient_samples_have_only_counts():
    stats = series_stats(make_samples([Decimal(50)] * 29))
    assert stats["status"] == "INSUFFICIENT_SAMPLES"
    assert stats["n_usable"] == 29
    assert stats["mean_bps"] is None


def test_all_missing_samples_are_unavailable():
    samples = [
        {
            "sample_time": "2026-01-01T00:00:00Z",
            "chain_price": None,
            "reference_price": None,
        }
        for _ in range(35)
    ]
    stats = series_stats(samples)
    assert stats["status"] == "INPUTS_UNAVAILABLE"
    assert stats["n_skipped"] == stats["n_total"] == 35


def test_missing_data_is_not_zero_premium():
    samples = make_samples([Decimal(50)] * 60)
    for index in range(40):
        samples.append({
            "sample_time": f"2026-01-02T00:{index // 60:02d}:{index % 60:02d}Z",
            "chain_price": Decimal("100"),
            "reference_price": None,
        })
    stats = series_stats(samples)
    assert stats["n_usable"] == 60
    assert stats["n_skipped"] == 40
    assert stats["mean_bps"] == Decimal("50")


def test_persistence_threshold_can_be_overridden():
    stats = series_stats(
        make_samples([Decimal(50)] * 30),
        persistence_threshold_bps=Decimal(60),
    )
    assert stats["persistence_frac"] == Decimal("0")


def test_persistent_offset_has_zero_haircut():
    # Was [80] * 30, whose stdev is exactly 0 and which any floor therefore
    # vetoes.  Given real microstructure a premium never sits perfectly still,
    # so the fixture now carries 1 bps of jitter above the 0.1 bps floor.  The
    # assertions are unchanged; only the synthetic data got more realistic.
    stats = series_stats(make_samples([Decimal(80), Decimal(81)] * 15))
    regime = premium_regime(stats)
    assert regime == "PERSISTENT_OFFSET"
    assert lvr_haircut_frac(stats, regime) == Decimal(0)


def test_unstable_regime_has_unknown_haircut():
    stats = series_stats(make_samples([Decimal(80), Decimal(-80)] * 20))
    regime = premium_regime(stats)
    assert regime == "UNSTABLE"
    assert lvr_haircut_frac(stats, regime) is None


def test_mean_reverting_haircut_uses_model_and_is_bounded():
    values = [
        Decimal(str(60 * math.sin(2 * math.pi * index / 16)))
        for index in range(120)
    ]
    stats = series_stats(make_samples(values))
    regime = premium_regime(stats)
    haircut = lvr_haircut_frac(stats, regime)
    assert regime == "MEAN_REVERTING"
    assert haircut == min(Decimal(1), stats["stdev_bps"] / Decimal(10000) * Decimal("0.50"))


def test_unordered_times_are_sorted_internally():
    samples = list(reversed(make_samples([Decimal(50)] * 30)))
    stats = series_stats(samples)
    assert stats["status"] == "COMPUTED"
    assert stats["mean_bps"] == Decimal("50")


def test_descriptive_statistics_are_decimal_and_present():
    stats = series_stats(make_samples([Decimal(10), Decimal(20), Decimal(30)] * 10))
    assert isinstance(stats["mean_bps"], Decimal)
    assert stats["median_bps"] == Decimal("20")
    assert stats["p05_bps"] < stats["p95_bps"]
    assert stats["max_abs_bps"] == Decimal("30")


def test_premium_regime_passes_through_insufficient_status():
    stats = series_stats(make_samples([Decimal(10)] * 29))
    assert premium_regime(stats) == "INSUFFICIENT_SAMPLES"
    assert lvr_haircut_frac(stats, premium_regime(stats)) is None


def test_premium_regime_passes_through_unavailable_status():
    stats = series_stats([])
    assert premium_regime(stats) == "INPUTS_UNAVAILABLE"


def test_zero_values_belong_to_positive_sign_bucket():
    stats = series_stats(make_samples([Decimal(0)] * 30))
    assert stats["sign_stability"] == Decimal(1)
    assert stats["zero_crossings"] == 0


def test_cli_reads_samples_and_writes_decimal_safe_json(tmp_path, monkeypatch):
    input_path = tmp_path / "samples.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(
        make_samples([Decimal(50), Decimal(51), Decimal(49)] * 10), default=str))
    monkeypatch.setattr(
        sys,
        "argv",
        ["premium-series", "--samples-json", str(input_path), "--out", str(output_path)],
    )
    main()
    result = json.loads(output_path.read_text())
    assert result["status"] == "COMPUTED"
    assert Decimal(result["mean_bps"]) == Decimal("50")
    assert result["regime"] == "PERSISTENT_OFFSET"


def test_lvr_coefficient_is_the_declared_constant():
    source_path = Path(__file__).parents[1] / "scripts" / "lp_rh_premium_series_v1_readonly.py"
    source = source_path.read_text()
    assert 'LVR_COEFFICIENT_MODEL = Decimal("0.50")' in source
    assert source.count("0.50") == 1
    for forbidden in ("0" + ".25", "0" + ".75"):
        assert forbidden not in source


def make_samples_ref(values, references, bids=None, asks=None, spacing=60):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = []
    for index, value in enumerate(values):
        reference = references[index]
        chain = reference * (Decimal(1) + value / Decimal("10000"))
        timestamp = (start + timedelta(seconds=index * spacing)).isoformat()
        sample = {
            "sample_time": timestamp.replace("+00:00", "Z"),
            "chain_price": chain,
            "reference_price": reference,
        }
        if bids is not None and asks is not None:
            sample["reference_bid"] = bids[index]
            sample["reference_ask"] = asks[index]
        samples.append(sample)
    return samples


def test_constant_reference_with_real_premium_swing_still_classifies():
    """A still reference must NOT by itself veto classification.

    Chain price swinging 60 bps against a constant reference is a 60 bps premium
    swing: real, measurable exposure.  An earlier draft of the resolution gate
    refused these outright and produced six false positives on this suite.
    """
    values = [Decimal(str(60 * math.sin(2 * math.pi * i / 16))) for i in range(120)]
    stats = series_stats(make_samples(values))
    assert stats["n_distinct_reference"] == 1
    assert premium_regime(stats) == "MEAN_REVERTING"


def test_sgov_like_low_variation_is_insufficient_resolution():
    """Reproduces SGOV: premium variation an order below the reference floor.

    Live values were stdev 0.107 bps against a 0.995 bps floor.  Classifying this
    as PERSISTENT_OFFSET would charge a zero LVR haircut, which is the optimistic
    reading, not the safe one -- a still reference is no evidence the chain price
    tracks it.
    """
    values = [Decimal("36.7"), Decimal("36.8")] * 20
    stats = series_stats(make_samples(values, half_spread_bps=Decimal("1.0")))
    assert stats["stdev_bps"] <= stats["resolution_floor_bps"]
    regime = premium_regime(stats)
    assert regime == "INSUFFICIENT_RESOLUTION"
    assert lvr_haircut_frac(stats, regime) is None


def test_amc_reproduction_insufficient_resolution():
    levels = [Decimal("2.495"), Decimal("2.505"), Decimal("2.515"), Decimal("2.525")]
    values = [Decimal(str(48 * math.sin(2 * math.pi * index / 16))) for index in range(32)]
    references = [levels[index % 4] for index in range(32)]
    bids = [reference - Decimal("0.005") for reference in references]
    asks = [reference + Decimal("0.005") for reference in references]
    stats = series_stats(make_samples_ref(values, references, bids, asks))
    assert stats["n_distinct_reference"] == 4
    assert stats["reference_spread_bps"] is not None
    assert stats["resolution_floor_bps"] is not None
    assert stats["stdev_bps"] <= stats["resolution_floor_bps"]
    assert premium_regime(stats) == "INSUFFICIENT_RESOLUTION"
    assert lvr_haircut_frac(stats, premium_regime(stats)) is None


def test_spy_reproduction_not_blocked():
    references = [Decimal("766.85") + Decimal("0.005") * Decimal(i) for i in range(34)]
    values = [Decimal(str(50 * math.sin(2 * math.pi * index / 16))) for index in range(34)]
    bids = [reference - Decimal("0.015") for reference in references]
    asks = [reference + Decimal("0.015") for reference in references]
    stats = series_stats(make_samples_ref(values, references, bids, asks))
    assert stats["n_distinct_reference"] == 34
    assert stats["resolution_floor_bps"] is not None
    assert stats["resolution_floor_bps"] < Decimal(1)
    assert premium_regime(stats) == "MEAN_REVERTING"


def test_stdev_equal_to_floor_is_insufficient():
    stats = {
        "status": "COMPUTED",
        "n_usable": 30,
        "n_distinct_reference": 2,
        "stdev_bps": Decimal("50"),
        "resolution_floor_bps": Decimal("50"),
        "sign_stability": Decimal("0.5"),
        "zero_crossings": 0,
        "half_life_secs": None,
    }
    assert premium_regime(stats) == "INSUFFICIENT_RESOLUTION"


def test_stdev_slightly_above_floor_passes():
    stats = {
        "status": "COMPUTED",
        "n_usable": 30,
        "n_distinct_reference": 2,
        "stdev_bps": Decimal("50.01"),
        "resolution_floor_bps": Decimal("50"),
        "sign_stability": Decimal("0.5"),
        "zero_crossings": 0,
        "half_life_secs": None,
    }
    assert premium_regime(stats) == "UNSTABLE"


def test_no_bid_ask_two_distinct_reference():
    references = [Decimal("100"), Decimal("100.01")] * 15
    stats = series_stats(make_samples_ref([Decimal(50)] * 30, references))
    assert stats["n_distinct_reference"] == 2
    assert stats["reference_spread_bps"] is None
    assert stats["reference_quantum_bps"] is not None
    assert stats["resolution_floor_bps"] == stats["reference_quantum_bps"]
    assert premium_regime(stats) == "INSUFFICIENT_RESOLUTION"


def test_floor_none_is_insufficient_resolution():
    stats = {
        "status": "COMPUTED",
        "n_usable": 30,
        "n_distinct_reference": 2,
        "stdev_bps": Decimal("50"),
        "resolution_floor_bps": None,
        "sign_stability": Decimal("0.5"),
        "zero_crossings": 0,
        "half_life_secs": None,
    }
    assert premium_regime(stats) == "INSUFFICIENT_RESOLUTION"


def test_resolution_fields_none_under_unavailable():
    stats = series_stats([])
    assert stats["status"] == "INPUTS_UNAVAILABLE"
    for field in ("n_distinct_reference", "reference_quantum_bps",
                  "reference_spread_bps", "resolution_floor_bps"):
        assert field in stats
        assert stats[field] is None


def test_resolution_fields_none_under_insufficient():
    stats = series_stats(make_samples([Decimal(10)] * 29))
    assert stats["status"] == "INSUFFICIENT_SAMPLES"
    for field in ("n_distinct_reference", "reference_quantum_bps",
                  "reference_spread_bps", "resolution_floor_bps"):
        assert field in stats
        assert stats[field] is None


def test_lvr_coefficient_still_declared():
    source_path = Path(__file__).parents[1] / "scripts" / "lp_rh_premium_series_v1_readonly.py"
    source = source_path.read_text()
    assert 'LVR_COEFFICIENT_MODEL = Decimal("0.50")' in source
    assert source.count("0.50") == 1
    for forbidden in ("0" + ".25", "0" + ".75"):
        assert forbidden not in source


def test_original_regime_strings_unchanged():
    assert premium_regime({"status": "INPUTS_UNAVAILABLE"}) == "INPUTS_UNAVAILABLE"
    assert premium_regime({"status": "INSUFFICIENT_SAMPLES"}) == "INSUFFICIENT_SAMPLES"
    base = {
        "status": "COMPUTED",
        "n_usable": 30,
        "n_distinct_reference": 2,
        "stdev_bps": Decimal("100"),
        "resolution_floor_bps": Decimal("10"),
        "half_life_secs": None,
    }
    persistent = dict(base, sign_stability=Decimal("1"), zero_crossings=0)
    assert premium_regime(persistent) == "PERSISTENT_OFFSET"
    mean_reverting = dict(
        base, sign_stability=Decimal("0.5"), zero_crossings=10, half_life_secs=Decimal("60")
    )
    assert premium_regime(mean_reverting) == "MEAN_REVERTING"
    unstable = dict(base, sign_stability=Decimal("0.5"), zero_crossings=0)
    assert premium_regime(unstable) == "UNSTABLE"


def test_zero_variation_is_vetoed_and_that_is_deliberate():
    """A perfectly still premium is refused, and the choice is recorded here.

    With stdev exactly 0 the unobservable reversion is bounded by the floor, so
    on a 0.1 bps floor a zero haircut would be safe to within 5e-6 and letting it
    through would be defensible.  The veto is kept anyway because the same
    argument fails where it matters: AMC's floor is 79 bps, where the hidden
    reversion is 800x larger.  One conservative rule beats a rule whose safety
    depends on which symbol it runs on.
    """
    stats = series_stats(make_samples([Decimal(80)] * 30))
    assert stats["stdev_bps"] == Decimal(0)
    regime = premium_regime(stats)
    assert regime == "INSUFFICIENT_RESOLUTION"
    assert lvr_haircut_frac(stats, regime) is None


# ---------------------------------------------------------------------------
# RH-05k: regime labels must carry a signal-to-floor ratio, because two
# UNSTABLE series can sit at wildly different distances from the floor.
# ---------------------------------------------------------------------------

def _confidence_stats(signal_to_floor):
    return {"status": "COMPUTED", "n_usable": 30, "signal_to_floor": signal_to_floor}


def test_signal_to_floor_none_when_floor_none():
    # Constant reference (no quantum) and no bid/ask (no spread) => floor None.
    references = [Decimal("100")] * 30
    stats = series_stats(make_samples_ref([Decimal(50)] * 30, references))
    assert stats["status"] == "COMPUTED"
    assert stats["resolution_floor_bps"] is None
    assert stats["signal_to_floor"] is None


def test_signal_to_floor_none_when_floor_zero():
    # Constant reference plus zero-width bid/ask gives a floor of exactly 0.
    # Division by zero must yield None, not inf and not a crash.
    references = [Decimal("100")] * 30
    bids = [Decimal("100")] * 30
    asks = [Decimal("100")] * 30
    stats = series_stats(make_samples_ref([Decimal(50)] * 30, references, bids, asks))
    assert stats["status"] == "COMPUTED"
    assert stats["resolution_floor_bps"] == Decimal(0)
    assert stats["signal_to_floor"] is None


def test_signal_to_floor_key_present_under_insufficient_samples():
    stats = series_stats(make_samples([Decimal(10)] * 29))
    assert stats["status"] == "INSUFFICIENT_SAMPLES"
    assert "signal_to_floor" in stats
    assert stats["signal_to_floor"] is None


def test_signal_to_floor_key_present_under_unavailable():
    stats = series_stats([])
    assert stats["status"] == "INPUTS_UNAVAILABLE"
    assert "signal_to_floor" in stats
    assert stats["signal_to_floor"] is None


def test_confidence_unknown_when_signal_to_floor_none():
    assert regime_confidence(_confidence_stats(None)) == "UNKNOWN"


def test_confidence_below_floor_at_099():
    assert regime_confidence(_confidence_stats(Decimal("0.99"))) == "BELOW_FLOOR"


def test_confidence_marginal_at_10():
    assert regime_confidence(_confidence_stats(Decimal("1.0"))) == "MARGINAL"


def test_confidence_marginal_at_199():
    assert regime_confidence(_confidence_stats(Decimal("1.99"))) == "MARGINAL"


def test_confidence_adequate_at_20():
    assert regime_confidence(_confidence_stats(Decimal("2.0"))) == "ADEQUATE"


def test_confidence_strong_at_50():
    assert regime_confidence(_confidence_stats(Decimal("5.0"))) == "STRONG"


def _measured_stats(stdev_bps, floor_bps):
    return {
        "status": "COMPUTED",
        "n_usable": 30,
        "stdev_bps": stdev_bps,
        "resolution_floor_bps": floor_bps,
        "signal_to_floor": stdev_bps / floor_bps,
        "sign_stability": Decimal("0.5"),
        "zero_crossings": 0,
        "half_life_secs": None,
    }


def test_nvda_afterhours_is_marginal():
    # Live measurement: stdev 2.67 bps against a 2.44 bps floor (ratio ~1.09).
    stats = _measured_stats(Decimal("2.67"), Decimal("2.44"))
    assert premium_regime(stats) == "UNSTABLE"
    assert regime_confidence(stats) == "MARGINAL"


def test_qqq_afterhours_is_adequate():
    # Live measurement: stdev 2.28 bps against a 0.77 bps floor (ratio ~2.96).
    stats = _measured_stats(Decimal("2.28"), Decimal("0.77"))
    assert premium_regime(stats) == "UNSTABLE"
    assert regime_confidence(stats) == "ADEQUATE"


def test_same_regime_different_confidence():
    # The point of RH-05k: two series share a regime label while sitting at
    # very different distances from the floor.
    nvda = _measured_stats(Decimal("2.67"), Decimal("2.44"))
    qqq = _measured_stats(Decimal("2.28"), Decimal("0.77"))
    assert premium_regime(nvda) == premium_regime(qqq)
    assert regime_confidence(nvda) != regime_confidence(qqq)


def test_premium_regime_return_set_unchanged():
    assert premium_regime({"status": "INPUTS_UNAVAILABLE"}) == "INPUTS_UNAVAILABLE"
    assert premium_regime({"status": "INSUFFICIENT_SAMPLES"}) == "INSUFFICIENT_SAMPLES"
    base = {
        "status": "COMPUTED",
        "n_usable": 30,
        "stdev_bps": Decimal("100"),
        "resolution_floor_bps": Decimal("10"),
        "half_life_secs": None,
    }
    insufficient = dict(base, stdev_bps=Decimal("5"))
    assert premium_regime(insufficient) == "INSUFFICIENT_RESOLUTION"
    persistent = dict(base, sign_stability=Decimal("1"), zero_crossings=0)
    assert premium_regime(persistent) == "PERSISTENT_OFFSET"
    mean_reverting = dict(
        base, sign_stability=Decimal("0.5"), zero_crossings=10, half_life_secs=Decimal("60")
    )
    assert premium_regime(mean_reverting) == "MEAN_REVERTING"
    unstable = dict(base, sign_stability=Decimal("0.5"), zero_crossings=0)
    assert premium_regime(unstable) == "UNSTABLE"


def test_lvr_haircut_frac_behavior_unchanged():
    stats = {"status": "COMPUTED", "stdev_bps": Decimal("100")}
    assert lvr_haircut_frac(stats, "MEAN_REVERTING") == min(
        Decimal(1), Decimal("100") / Decimal("10000") * Decimal("0.50")
    )
    assert lvr_haircut_frac(stats, "PERSISTENT_OFFSET") == Decimal(0)
    assert lvr_haircut_frac(stats, "INSUFFICIENT_RESOLUTION") is None
