"""Tests for RH-02aa: load_samples_from_db must replay the MOST RECENT N rows.

The old query used ``ORDER BY sample_time LIMIT ?`` (ascending), so LIMIT
selected the OLDEST N rows.  As the sample table grew, the shadow daemon kept
replaying the earliest hour and never saw new data.  The fix selects the most
recent N rows (``ORDER BY sample_time DESC LIMIT ?``) and then replays them in
ascending sample_time order.

All tests use an in-memory sqlite store with a known time series.  No network,
no wallet, no broadcast.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import load_samples_from_db

BASE = datetime(2026, 9, 8, 0, 0, 0)


def _ts(i: int) -> str:
    """Deterministic ISO-8601 timestamp, strictly increasing in i."""
    return (BASE + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _create_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE rh_market_states ("
        "asset_address TEXT NOT NULL, sample_time TEXT NOT NULL, "
        "chain_id INTEGER NOT NULL, source_payload_hash TEXT, "
        "session TEXT NOT NULL, health_flags_json TEXT NOT NULL, "
        "reference_bid TEXT, reference_ask TEXT, reference_mid TEXT, "
        "reference_age_secs INTEGER, multiplier_human TEXT, "
        "oracle_paused INTEGER, derived_block_hash TEXT, "
        "derived_block_number INTEGER, source_event_time TEXT, "
        "fee_growth_global_0 TEXT, fee_growth_global_1 TEXT, "
        "PRIMARY KEY (asset_address, sample_time))")


def _insert(conn, asset, i, *, mid="100.5", session="RTH", age=5,
            oracle_paused=0, payload_hash="0xabc", source_event_time=None,
            bid="100.4", ask="100.6", mult="1.0"):
    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time, chain_id, "
        "source_payload_hash, session, health_flags_json, reference_bid, "
        "reference_ask, reference_mid, reference_age_secs, multiplier_human, "
        "oracle_paused, source_event_time) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (asset, _ts(i), 4663, payload_hash, session, "{}", bid, ask, mid,
         age, mult, oracle_paused, source_event_time))
    conn.commit()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    _create_table(c)
    yield c
    c.close()


def test_returns_last_200_of_500(conn):
    """★Reproduce the defect: limit=200 must return the LAST 200 rows.★"""
    for i in range(500):
        _insert(conn, "poolA", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=200)
    assert len(samples) == 200
    # First returned row is the 301st inserted (index 300), not the oldest.
    assert samples[0]["sample_time"] == _ts(300)
    # Last returned row is the newest.
    assert samples[-1]["sample_time"] == _ts(499)


def test_return_order_ascending(conn):
    """★Returned rows must still be in ascending sample_time order.★"""
    for i in range(500):
        _insert(conn, "poolA", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=200)
    times = [s["sample_time"] for s in samples]
    for a, b in zip(times, times[1:]):
        assert a <= b


def test_fewer_than_limit_returns_all_ascending(conn):
    for i in range(50):
        _insert(conn, "poolA", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=200)
    assert len(samples) == 50
    times = [s["sample_time"] for s in samples]
    assert times == sorted(times)
    assert times[0] == _ts(0) and times[-1] == _ts(49)


def test_exactly_limit_returns_all(conn):
    for i in range(200):
        _insert(conn, "poolA", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=200)
    assert len(samples) == 200
    assert samples[0]["sample_time"] == _ts(0)
    assert samples[-1]["sample_time"] == _ts(199)


def test_limit_1_returns_newest(conn):
    for i in range(10):
        _insert(conn, "poolA", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=1)
    assert len(samples) == 1
    assert samples[0]["sample_time"] == _ts(9)


def test_only_specified_asset(conn):
    for i in range(5):
        _insert(conn, "poolA", i)
    for i in range(5):
        _insert(conn, "poolB", i)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=100)
    assert len(samples) == 5
    assert all(s["asset_address"] == "poolA" for s in samples)


def test_null_mid_skipped_and_counted(conn):
    for i in range(10):
        mid = None if i >= 7 else "100.5"
        _insert(conn, "poolA", i, mid=mid)
    samples, skipped = load_samples_from_db(conn, pool="poolA", limit=100)
    assert skipped == 3
    assert len(samples) == 7
    assert all(s["reference_mid"] is not None for s in samples)


def test_skipped_rows_consume_limit_slot(conn):
    """Existing semantics: LIMIT applies to raw rows, so NULL rows take a slot.

    105 rows; the 5 newest (i=100..104) have NULL mid.  limit=100 selects the
    100 newest raw rows (i=5..104); 5 of those are NULL -> skipped=5, returned=95.
    If skipped rows did NOT consume a slot, returned would be 100.
    """
    for i in range(105):
        mid = None if i >= 100 else "100.5"
        _insert(conn, "poolA", i, mid=mid)
    samples, skipped = load_samples_from_db(conn, pool="poolA", limit=100)
    assert skipped == 5
    assert len(samples) == 95
    # The oldest returned row is i=5 (i=0..4 fell outside the raw LIMIT window).
    assert samples[0]["sample_time"] == _ts(5)


def test_source_event_time_key_present(conn):
    """Regression RH-02x: sample dict carries source_event_time from the column."""
    _insert(conn, "poolA", 0, source_event_time="2026-09-08T00:00:01Z")
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert "source_event_time" in samples[0]
    assert samples[0]["source_event_time"] == "2026-09-08T00:00:01Z"


def test_reference_mid_is_decimal(conn):
    _insert(conn, "poolA", 0, mid="123.456")
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert isinstance(samples[0]["reference_mid"], Decimal)
    assert samples[0]["reference_mid"] == Decimal("123.456")


def test_session_key_correct(conn):
    _insert(conn, "poolA", 0, session="PREMARKET")
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert samples[0]["session"] == "PREMARKET"


def test_reference_age_secs_key_correct(conn):
    _insert(conn, "poolA", 0, age=42)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert samples[0]["reference_age_secs"] == 42


def test_oracle_paused_key_correct(conn):
    _insert(conn, "poolA", 0, oracle_paused=1)
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert samples[0]["oracle_paused"] == 1


def test_source_payload_hash_key_correct(conn):
    _insert(conn, "poolA", 0, payload_hash="0xdeadbeef")
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=10)
    assert samples[0]["source_payload_hash"] == "0xdeadbeef"


def test_mixed_old_new_returns_all_with_source_event_time(conn):
    """★The exact point the defect hid: newest rows carry source_event_time.★

    First 300 rows have source_event_time NULL (old), last 200 have values
    (new).  limit=200 must return the 200 newest, ALL with a value.
    """
    for i in range(300):
        _insert(conn, "poolA", i, source_event_time=None)
    for i in range(300, 500):
        _insert(conn, "poolA", i, source_event_time=f"evt-{i}")
    samples, _ = load_samples_from_db(conn, pool="poolA", limit=200)
    assert len(samples) == 200
    assert all(s["source_event_time"] is not None for s in samples)
    assert samples[0]["source_event_time"] == "evt-300"
    assert samples[-1]["source_event_time"] == "evt-499"
