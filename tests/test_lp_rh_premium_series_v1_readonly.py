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
    series_stats,
)


def make_samples(values, spacing=60):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = []
    for index, value in enumerate(values):
        reference = Decimal("100")
        chain = reference * (Decimal(1) + value / Decimal("10000"))
        timestamp = (start + timedelta(seconds=index * spacing)).isoformat()
        samples.append({
            "sample_time": timestamp.replace("+00:00", "Z"),
            "chain_price": chain,
            "reference_price": reference,
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
    stats = series_stats(make_samples([Decimal(80)] * 30))
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
    input_path.write_text(json.dumps(make_samples([Decimal(50)] * 30), default=str))
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
