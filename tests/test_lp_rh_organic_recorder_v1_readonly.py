"""Tests for scripts/lp_rh_organic_recorder_v1_readonly.py (RH-05i-b).

In-memory SQLite + injected fake call_fn/head_fn; no network, no reports/ files.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
import urllib.error
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_swap_logs_v1_readonly import (
    SWAP_TOPIC0,
    to_organic_events,
)
from scripts.lp_rh_organic_volume_v1_readonly import organic_volume_estimate
from scripts import lp_rh_organic_recorder_v1_readonly as mod

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
POOL = "0x" + "a" * 40
RECEPIENT = "0x" + "p" * 40


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(mod.SCHEMA)
    return conn


def _word(value):
    """Two's-complement 32-byte hex word (matches decode_int256)."""
    return format(value % (1 << 256), "064x")


def make_event(sender, block, tx, log_index, amount0, amount1):
    return {"block": block, "tx_hash": tx, "log_index": log_index,
            "sender": sender, "recipient": RECEPIENT, "amount0": amount0,
            "amount1": amount1, "sqrt_price_x96": 0, "liquidity": 0, "tick": 0}


def raw_log(ev):
    """Re-encode a decoded event as an eth_getLogs entry for the fake call_fn."""
    data = "0x" + _word(ev["amount0"]) + _word(ev["amount1"]) + "0" * 64 + "0" * 64 + _word(0)
    return {"blockNumber": hex(ev["block"]), "transactionHash": ev["tx_hash"],
            "logIndex": hex(ev["log_index"]),
            "topics": [SWAP_TOPIC0, "0x" + "0" * 12 + ev["sender"][2:],
                       "0x" + "0" * 12 + ev["recipient"][2:]],
            "data": data}


def sell_events(n, sender=None, start_block=1000, base_tx="0x"):
    """n SELL0 events (amount0<0, amount1>0); unique senders unless given."""
    out = []
    for i in range(n):
        who = sender if sender is not None else "0x" + format(i, "x").rjust(40, "0")
        out.append(make_event(who, start_block + i, f"{base_tx}{i}", i, -1000, 1000))
    return out


def mixed_events():
    """50 events: one sender with 40x1000, ten senders with 1x1000 each.

    All SELL0 so no round-trip matching; expected organic_fraction = 0.45."""
    big = "0x" + "b" * 40
    return (sell_events(40, sender=big, base_tx="0xbig")
            + sell_events(10, start_block=1040, base_tx="0xsmall"))


def make_call_fn(logs, fail_from_blocks=()):
    """Fake call_fn: returns `logs`; raises ValueError (non-range) for fromBlock
    in fail_from_blocks so fetch_swaps records the chunk failed, not a split."""
    def call_fn(params):
        if int(params["fromBlock"], 16) in fail_from_blocks:
            raise ValueError("bad params")
        return list(logs)
    return call_fn


def test_next_window_empty_db():
    conn = make_conn()
    assert mod.next_window(conn, 10000, span_blocks=100, max_lookback_blocks=1000) == (9900, 10000)


def test_next_window_continues_without_overlap():
    conn = make_conn()
    mod.record_window(conn, POOL, 100, 199, make_call_fn([]), "test")
    # head - prev_end = 301 <= lookback, so continue right after window_end_block
    lo, hi = mod.next_window(conn, 500, span_blocks=100, max_lookback_blocks=1000)
    assert (lo, hi) == (200, 300)  # tight against window_end_block=199, no overlap


def test_next_window_gap_beyond_lookback_jumps_to_head_span():
    conn = make_conn()
    mod.record_window(conn, POOL, 100, 199, make_call_fn([]), "test")
    lo, hi = mod.next_window(conn, 90000, span_blocks=100, max_lookback_blocks=5000)
    assert (lo, hi) == (89900, 90000)  # never requests pruned blocks


def test_next_window_gap_equal_to_lookback_continues():
    conn = make_conn()
    mod.record_window(conn, POOL, 100, 199, make_call_fn([]), "test")
    # head - prev_end == max_lookback exactly -> NOT beyond, so continue
    lo, hi = mod.next_window(conn, 5199, span_blocks=100, max_lookback_blocks=5000)
    assert (lo, hi) == (200, 300)


def test_record_window_fraction_matches_direct_estimate():
    conn = make_conn()
    events = mixed_events()
    row = mod.record_window(conn, POOL, 1000, 1099,
                            make_call_fn([raw_log(e) for e in events]), "test")
    est = organic_volume_estimate(to_organic_events([dict(e) for e in events]))
    assert row["organic_fraction"] == "0.45"  # TEXT in the returned row dict
    stored = conn.execute("SELECT organic_fraction FROM rh_organic_windows").fetchone()[0]
    assert Decimal(stored) == est["organic_fraction"] == Decimal("0.45")


def test_record_window_primary_key_dedup():
    conn = make_conn()
    call_fn = make_call_fn([])
    mod.record_window(conn, POOL, 100, 199, call_fn, "test")
    mod.record_window(conn, POOL, 100, 199, call_fn, "test")
    assert conn.execute("SELECT COUNT(*) FROM rh_organic_windows").fetchone()[0] == 1


def test_record_window_all_calls_fail():
    conn = make_conn()

    def failing(params):
        raise ValueError("bad params")

    row = mod.record_window(conn, POOL, 100, 199, failing, "test")
    assert row["fetch_status"] == "INPUTS_UNAVAILABLE"
    assert row["organic_fraction"] is None
    assert row["coverage_frac"] is None
    stored = conn.execute(
        "SELECT organic_fraction, coverage_frac FROM rh_organic_windows"
    ).fetchone()
    assert stored == (None, None)  # NULL in the db, never 0


def test_record_window_partial_failure():
    conn = make_conn()
    # fetch_swaps calls once for the full [1000,4999]; a range error on the
    # full range makes it split into [1000,2999] + [3000,4999]; the second
    # half then fails with a non-range error -> PARTIAL, coverage 0.5.
    events = sell_events(50, base_tx="0xok")
    logs = [raw_log(e) for e in events]

    def call_fn(params):
        a = int(params["fromBlock"], 16)
        b = int(params["toBlock"], 16)
        if a == 1000 and b == 4999:
            raise RuntimeError("provider error: block range too large")
        if a == 3000:
            raise ValueError("bad params")
        return list(logs)

    row = mod.record_window(conn, POOL, 1000, 4999, call_fn, "test")
    assert row["fetch_status"] == "PARTIAL"
    stored = conn.execute("SELECT coverage_frac FROM rh_organic_windows").fetchone()[0]
    assert Decimal("0") < Decimal(stored) < Decimal("1")
    assert row["organic_fraction"] is not None  # still computed from what arrived


def test_record_window_insufficient_samples():
    conn = make_conn()
    events = sell_events(3, base_tx="0xfew")
    row = mod.record_window(conn, POOL, 100, 199,
                            make_call_fn([raw_log(e) for e in events]), "test")
    assert row["estimate_status"] == "INSUFFICIENT_SAMPLES"
    assert row["organic_fraction"] is None
    assert row["n_events"] == 3
    stored = conn.execute("SELECT n_events FROM rh_organic_windows").fetchone()[0]
    assert stored == 3


def test_is_transient_network_busy():
    assert mod._is_transient(RuntimeError("eth_getLogs: -32005 network is busy")) is True


def test_is_transient_http_429():
    exc = urllib.error.HTTPError("http://rpc/x", 429, "Too Many Requests", None, None)
    assert mod._is_transient(exc) is True


def test_is_transient_http_503():
    exc = urllib.error.HTTPError("http://rpc/x", 503, "Service Unavailable", None, None)
    assert mod._is_transient(exc) is True


def test_is_transient_value_error_false():
    assert mod._is_transient(ValueError("bad params")) is False


def test_backoff_retries_transient_with_increasing_sleep():
    sleeps = []
    state = {"n": 0}

    def base(params):
        state["n"] += 1
        if state["n"] <= 2:
            raise RuntimeError("-32005 network is busy")
        return ["ok"]

    fn = mod.make_backoff_call_fn(base, sleep_fn=sleeps.append)
    assert fn({}) == ["ok"]
    assert sleeps == [8, 24]  # two sleeps, backoff increasing


def test_backoff_non_transient_raises_without_retry():
    sleeps = []
    calls = {"n": 0}

    def base(params):
        calls["n"] += 1
        raise ValueError("bad params")

    fn = mod.make_backoff_call_fn(base, sleep_fn=sleeps.append)
    with pytest.raises(ValueError):
        fn({})
    assert calls["n"] == 1
    assert sleeps == []  # no retry, no sleep


def test_decimal_columns_round_trip():
    conn = make_conn()
    values = {
        "top1_share": "0.3000000000000000000000000000000000000000000000000000000001",
        "top5_share": "0.75",
        "hhi": "0.1234567890123456789012345678901234567890123456789012345678",
        "round_trip_share": "0",
        "total_volume": "50000",
        "round_trip_volume": "0",
        "concentration_excess_volume": "27500",
        "organic_fraction": "0.45",
        "coverage_frac": "1",
    }
    conn.execute(
        "INSERT INTO rh_organic_windows (window_start_block, window_end_block, "
        "top1_share, top5_share, hhi, round_trip_share, total_volume, "
        "round_trip_volume, concentration_excess_volume, organic_fraction, "
        "coverage_frac) VALUES (1, 2, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(values.values()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT top1_share, top5_share, hhi, round_trip_share, total_volume, "
        "round_trip_volume, concentration_excess_volume, organic_fraction, "
        "coverage_frac FROM rh_organic_windows"
    ).fetchone()
    for name, stored in zip(values, row):
        assert Decimal(stored) == Decimal(values[name]), name


def test_main_once_returns_zero_and_writes_one_row(tmp_path):
    db = tmp_path / "organic.db"
    events = sell_events(50, base_tx="0xmain")
    rc = mod.main(["--db", str(db), "--pool", POOL, "--once"],
                  call_fn=make_call_fn([raw_log(e) for e in events]),
                  head_fn=lambda: 200000)
    assert rc == 0
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT window_start_block, window_end_block FROM rh_organic_windows"
    ).fetchall()
    conn.close()
    assert rows == [(200000 - 8800, 200000)]  # exactly one new row


def test_main_once_does_not_create_reports_db(tmp_path):
    db = tmp_path / "organic.db"
    rc = mod.main(["--db", str(db), "--pool", POOL, "--once"],
                  call_fn=make_call_fn([]), head_fn=lambda: 200000)
    assert rc == 0
    assert db.exists()
    assert not (ROOT / "reports" / "lp_rh" / "organic.db").exists()
