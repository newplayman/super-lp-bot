import sqlite3
from datetime import datetime, timedelta, timezone

from scripts.lp_stock_tier_c_shadow_v1_readonly import (
    build_report,
    initialize,
    load_swap_counts,
    persist_snapshot,
    pool_persistence,
)


def _row(apy=100, tvl=30_000):
    return {
        "pool": "c", "symbol": "SPYX-SSX", "apy": apy,
        "apyBase": apy, "apyReward": 0, "tvlUsd": tvl,
        "volumeUsd1d": 50_000,
    }


def test_persistence_needs_real_48h_span_and_three_samples():
    db = sqlite3.connect(":memory:")
    initialize(db)
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    persist_snapshot(db, {"c"}, [_row()], observed_at=start)
    persist_snapshot(db, {"c"}, [_row(80)], observed_at=start + timedelta(hours=24))
    assert pool_persistence(db, "c")["eligible_48h"] is False
    persist_snapshot(db, {"c"}, [_row(60)], observed_at=start + timedelta(hours=48))
    result = pool_persistence(db, "c")
    assert result["eligible_48h"] is True
    assert result["sample_count"] == 3


def test_decay_and_rug_are_not_persistence_passes():
    db = sqlite3.connect(":memory:")
    initialize(db)
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    for hours, apy, tvl in ((0, 100, 30_000), (24, 80, 25_000), (48, 40, 10_000)):
        persist_snapshot(db, {"c"}, [_row(apy, tvl)],
                         observed_at=start + timedelta(hours=hours))
    result = pool_persistence(db, "c")
    assert result["eligible_48h"] is False
    assert result["cause"] == "POSSIBLE_RUG_OR_LIQUIDITY_WITHDRAWAL"


def test_unobserved_pool_is_reported_fail_closed():
    db = sqlite3.connect(":memory:")
    initialize(db)
    report = build_report(db, {"a", "b"})
    assert report["eligible_48h_count"] == 0
    assert report["observed_pool_count"] == 0


def test_only_actual_bounded_replay_is_imported_as_swap_count(tmp_path):
    path = tmp_path / "stage2.json"
    path.write_text('{"results":[{"llama_pool_id":"c","swap_replay":{"status":"PASS","swap_count":3}},{"llama_pool_id":"x","swap_replay":{"status":"NOT_REQUESTED","swap_count":0}}]}')
    assert load_swap_counts(path) == {"c": 3}
