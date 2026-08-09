from datetime import datetime, timedelta, timezone

import pytest

from scripts.lp_reward_persistence_v1_readonly import (
    SURROGATE_ABSENT,
    SURROGATE_STRONG,
    SURROGATE_STRONG_FACTOR,
    SURROGATE_WEAK,
    reward_high_duration_from_observations,
    reward_persistence_surrogate,
)


UTC = timezone.utc
CUTOFF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _strong(**updates):
    record = {
        "apy": 70.0,
        "apyBase": 10.0,
        "apyReward": 60.0,
        "apyMean30d": 58.0,
        "apyBase7d": 8.0,
        "apyPct1D": -100.0,  # noisy total-APY changes are audit-only
        "apyPct7D": -20.0,
        "apyPct30D": 10.0,
        "count": 386,
    }
    record.update(updates)
    return record


def test_surrogate_three_tiers_and_strong_never_trusted():
    strong = reward_persistence_surrogate(_strong())
    weak = reward_persistence_surrogate(_strong(apyPct30D=-100.0))
    absent = reward_persistence_surrogate({"apyBase": 10.0, "apyReward": 60.0})

    assert strong["tier"] == SURROGATE_STRONG
    assert strong["entry_eligible"] is True
    assert strong["score_factor"] == SURROGATE_STRONG_FACTOR == 0.25
    assert strong["score_factor"] < 1.0
    assert strong["effective_duration_hours"] == 6.0
    assert strong["evidence_source"] == "surrogate_defillama"
    assert weak["tier"] == SURROGATE_WEAK
    assert weak["entry_eligible"] is False and weak["score_factor"] == 0.0
    assert absent["tier"] == SURROGATE_ABSENT
    assert absent["evidence_source"] == "absent"


def test_surrogate_does_not_mislabel_total_apy_as_reward_history():
    decision = reward_persistence_surrogate(_strong())
    inputs = decision["inputs"]
    assert inputs["historical_reward_proxy_mismatched_windows"] == 50.0
    assert "mismatched_windows" in next(
        key for key in inputs if key.startswith("historical_reward_proxy")
    )


def test_partial_history_is_weak_not_strong_and_invalid_reward_is_absent():
    partial = reward_persistence_surrogate({
        "apyBase": 10.0, "apyReward": 20.0, "apyMean30d": 25.0,
        "count": 100,
    })
    invalid = reward_persistence_surrogate(_strong(apyReward=float("nan")))
    assert partial["tier"] == SURROGATE_WEAK
    assert invalid["tier"] == SURROGATE_ABSENT
    assert invalid["reason"] == "REWARD_APR_INVALID"


def _row(hours_before, reward):
    return {
        "as_of": (CUTOFF - timedelta(hours=hours_before)).isoformat(),
        "apy_reward": reward,
    }


def test_contiguous_duration_uses_strict_cutoff_two_samples_and_gap_boundary():
    observations = [_row(step / 2.0, 10) for step in range(1, 50)]
    # Add a current-cycle row which must never participate.
    observations.append({"as_of": CUTOFF.isoformat(), "apy_reward": 10})
    evidence = reward_high_duration_from_observations(observations, cutoff=CUTOFF)
    assert evidence["duration_hours"] == pytest.approx(24.0)
    assert evidence["sample_count"] == 49

    one = reward_high_duration_from_observations([_row(0.25, 10)], cutoff=CUTOFF)
    assert one["duration_hours"] is None
    assert one["status"] == "INSUFFICIENT_OBSERVATIONS"


def test_zero_gap_and_staleness_reset_contiguous_suffix():
    zero_reset = reward_high_duration_from_observations(
        [_row(0.25, 10), _row(0.5, 0), _row(0.75, 10)], cutoff=CUTOFF
    )
    assert zero_reset["duration_hours"] is None
    assert zero_reset["sample_count"] == 1

    gap_reset = reward_high_duration_from_observations(
        [_row(0.25, 10), _row(1.0, 10)], cutoff=CUTOFF
    )
    assert gap_reset["duration_hours"] is None

    stale = reward_high_duration_from_observations([_row(0.75, 10)], cutoff=CUTOFF)
    assert stale["status"] == "STALE_OBSERVATIONS"
