"""Reward-decay and persistence contracts (pure, no network)."""
from __future__ import annotations

import json

from scripts.lp_portfolio_allocator_v1_readonly import is_enterable, rank_metric
from scripts.lp_reward_decay_replay_v1_readonly import (
    build_decay_trajectory,
    run_replay,
    write_report,
)
from scripts.lp_universe_screener_v1_readonly import (
    assess,
    reward_persistence_gate,
    score_pool,
)


GATES = {
    "min_tvl": 500_000.0,
    "min_vol1d": 50_000.0,
    "suspect_reward_apr": 300.0,
    "suspect_vol_tvl": 20.0,
}


def _pool(reward_apr=100.0, duration_hours=24.0):
    pool = {
        "symbol": "WETH-USDC",
        "project": "aerodrome-slipstream",
        "pool": "reward-decay-fixture",
        "poolMeta": "CL50 - 0.05%",
        "underlyingTokens": ["0xbase", "0xquote"],
        "rewardTokens": ["0xreward"],
        "tvlUsd": 2_000_000.0,
        "volumeUsd1d": 500_000.0,
        "apyBase": 20.0,
        "apyReward": reward_apr,
        # Deliberately stale: scoring must not extrapolate this old high APR.
        "apyMean30d": 120.0,
    }
    if duration_hours is not None:
        pool["reward_high_duration"] = duration_hours
    return pool


def _allocator_record(pool):
    screened = assess(pool, GATES)
    return {
        **screened,
        "status": "OK",
        "resolve_status": "OK",
        "wash_flag": False,
        "yield_cover": 5.0,
        "composite_score": screened["score"],
        "fee_apr_onchain": 20.0,
        "reward_apr": pool["apyReward"],
        "total_income_apr": 20.0 + pool["apyReward"],
        "il_apr": 5.0,
    }


def test_missing_reward_persistence_fails_closed_but_base_only_is_compatible():
    missing = reward_persistence_gate(_pool(duration_hours=None))
    assert missing["entry_eligible"] is False
    assert missing["status"] == "MISSING_FAIL_CLOSED"
    assert missing["score_factor"] == 0.0

    base_only = reward_persistence_gate({"apyBase": 20.0, "apyReward": 0.0})
    assert base_only["entry_eligible"] is True
    assert base_only["status"] == "NOT_APPLICABLE"


def test_new_300pct_incentive_for_30_minutes_cannot_enter():
    young = _pool(reward_apr=300.0, duration_hours=0.5)
    screened = assess(young, GATES)
    assert screened["gate_ok"] is True  # coarse liquidity gate is still diagnostic
    assert screened["entry_eligible"] is False
    assert screened["reward_persistence_status"] == "TOO_YOUNG_SHADOW_ONLY"
    assert "REWARD_PERSISTENCE_LT_6H" in screened["entry_block_reasons"]
    assert is_enterable(_allocator_record(young)) is False


def test_six_hours_is_minimum_and_24_hours_scores_more_credibly():
    six = _pool(reward_apr=100.0, duration_hours=6.0)
    trusted = _pool(reward_apr=100.0, duration_hours=24.0)
    assert assess(six, GATES)["entry_eligible"] is True
    assert assess(trusted, GATES)["reward_persistence_status"] == "TRUSTED_24H"
    assert score_pool(trusted) > score_pool(six)
    assert rank_metric(_allocator_record(trusted)) > rank_metric(_allocator_record(six))


def test_missing_duration_reward_record_is_fail_closed_at_allocator():
    missing = _allocator_record(_pool(reward_apr=30.0, duration_hours=None))
    assert missing["entry_eligible"] is False
    assert is_enterable(missing) is False
    # Legacy fee-only records have no reward persistence requirement.
    assert is_enterable({
        "status": "OK", "resolve_status": "OK", "wash_flag": False,
        "composite_score": 20.0, "yield_cover": 2.0,
        "fee_apr_onchain": 20.0, "reward_apr": 0.0,
    }) is True


def test_normalized_reward_field_cannot_be_bypassed_by_null_aggregator_field():
    normalized = {
        "apyReward": None,
        "reward_apr": 100.0,
        "reward_high_duration": None,
        "status": "OK", "resolve_status": "OK", "wash_flag": False,
        "composite_score": 80.0, "yield_cover": 5.0,
    }
    assert reward_persistence_gate(normalized)["status"] == "MISSING_FAIL_CLOSED"
    assert is_enterable(normalized) is False


def test_nonfinite_duration_is_invalid_fail_closed():
    decision = reward_persistence_gate(_pool(duration_hours=float("nan")))
    assert decision["entry_eligible"] is False
    assert decision["status"] == "INVALID_FAIL_CLOSED"


def test_negative_reward_apr_is_corrupt_evidence_not_fee_only():
    decision = reward_persistence_gate({"apyBase": 20.0, "apyReward": -1.0})
    assert decision["entry_eligible"] is False
    assert decision["status"] == "INVALID_REWARD_FAIL_CLOSED"
    assert decision["reason"] == "REWARD_APR_INVALID"


def test_expired_reward_is_not_resurrected_from_stale_30d_mean():
    expired = _pool(reward_apr=0.0, duration_hours=None)
    expired["apyMean30d"] = 320.0
    assert score_pool(expired) == 20.0  # current fee APR only


def test_decay_replay_uses_real_screener_allocator_scoring_chain():
    points = build_decay_trajectory()
    assert [p["reward_apr"] for p in points] == [100.0, 30.0, 5.0]
    replay = run_replay(points)
    rows = replay["trajectory"]
    assert all(row["entry_eligible"] for row in rows)
    assert [row["screener_score"] for row in rows] == sorted(
        [row["screener_score"] for row in rows], reverse=True
    )
    assert len({row["screener_score"] for row in rows}) == 3
    assert [row["allocator_rank_metric"] for row in rows] == sorted(
        [row["allocator_rank_metric"] for row in rows], reverse=True
    )
    assert len({row["allocator_rank_metric"] for row in rows}) == 3
    assert replay["assertions"]["scores_strictly_decrease"] is True
    assert replay["assertions"]["young_300pct_rejected"] is True
    assert replay["assertions"]["missing_persistence_fail_closed"] is True


def test_replay_writes_machine_and_human_reports(tmp_path):
    replay = run_replay()
    paths = write_report(replay, tmp_path)
    machine = json.loads(paths["machine_json"].read_text())
    human = paths["human_summary"].read_text()
    assert machine["schema_version"] == "lp-reward-decay-replay-v1"
    assert machine["assertions"]["all_passed"] is True
    assert "100.00%" in human and "30.00%" in human and "5.00%" in human
    assert "paper-only" in human.lower()
