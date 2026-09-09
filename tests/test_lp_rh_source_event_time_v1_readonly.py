"""Paired tests for the RH-02u source_event_time column (read-only).

scripts/lp_rh_collector_v1_readonly.py now writes the sampled block's own
timestamp into rh_source_snapshots.source_event_time (UTC RFC3339), None
when the block timestamp is unavailable -- never fetch_time, never 0.
All RPC traffic is injected via fake rpc_fn callables (never the network);
all databases live under tmp_path. The sample instant is controlled by
monkeypatching collector._utc_now.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from datetime import datetime

import pytest

from scripts import lp_rh_collector_v1_readonly as collector
from scripts.lp_rh_market_session_v1_readonly import classify_session
from scripts.lp_rh_store_v1_readonly import (
    assert_utc_rfc3339, migrate, open_store,
)

# sqrtPriceX96 for the identity-gated target pool (dec0=18, dec1=6).
SQRT_PRICE = 3953938817749275760872870
SLOT0_HEX = "0x" + format(SQRT_PRICE, "064x")

LATEST_NUMBER = "0x1dcd1"
GOOD_HASH = "0xGOODHASH"
GOOD_BLOCK_INT = int(LATEST_NUMBER, 16)


def _block(timestamp_hex, number=LATEST_NUMBER, hash_=GOOD_HASH):
    return {"number": number, "hash": hash_, "timestamp": timestamp_hex,
            "baseFeePerGas": "0x3b9aca00"}


def _block_rpc(latest=None, latest_err=None, good_block=None,
               good_block_err=None, slot0_err=None):
    """rpc_fn serving eth_getBlockByNumber / eth_call; no network.

    latest / latest_err: response for the ["latest", False] call.
    good_block / good_block_err: response for the specific-block call
    (hex(good_block) identifier). eth_call: slot0 returns a real price,
    everything else a dummy value.
    """
    def rpc_fn(method, params=None, **_kw):
        if method == "eth_getBlockByNumber":
            ident = params[0]
            if ident == "latest":
                if latest_err is not None:
                    return None, latest_err, 12
                return latest, None, 5
            if good_block_err is not None:
                return None, good_block_err, 9
            return good_block, None, 5
        data = params[0]["data"]
        if data == collector.SEL_SLOT0:
            if slot0_err is not None:
                return None, slot0_err, 4
            return SLOT0_HEX, None, 4
        return "0x1", None, 4
    return rpc_fn


def _snap(conn):
    row = conn.execute(
        "SELECT source_event_time, fetch_time, schema_kind, raw_ref, "
        "quality FROM rh_source_snapshots").fetchone()
    return dict(zip(("event", "fetch", "schema", "raw_ref", "quality"), row))


def _market(conn):
    row = conn.execute(
        "SELECT session, derived_block_hash, derived_block_number, "
        "reference_age_secs, reference_mid FROM rh_market_states"
    ).fetchone()
    return dict(zip(("session", "hash", "number", "age", "mid"), row))


@pytest.fixture
def conn(tmp_path):
    c = open_store(tmp_path / "rh_sev.db")
    migrate(c)
    yield c
    c.close()


def _round(conn, rpc, monkeypatch=None, stamp=None, now_fn=None):
    if stamp is not None:
        monkeypatch.setattr(collector, "_utc_now", lambda: stamp)
    kw = {}
    if now_fn is not None:
        kw["now_fn"] = now_fn
    return collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None, rpc_fn=rpc, **kw)


def _normal_rpc(stamp_hex="0x64"):
    return _block_rpc(latest=_block(stamp_hex), good_block=_block(stamp_hex))


# --- 1. exact epoch value (spec star case) ----------------------------------
def test_source_event_time_exact_epoch_100(conn):
    _round(conn, _normal_rpc("0x64"))
    assert _snap(conn)["event"] == "1970-01-01T00:01:40Z"


# --- 2. block timestamp unavailable -> None, never fetch_time ---------------
def test_source_event_time_none_when_block_unavailable(conn):
    _round(conn, _block_rpc(latest=_block("0x64"),
                            good_block_err={"code": -32603,
                                            "message": "boom"}))
    s = _snap(conn)
    assert s["event"] is None
    assert s["fetch"] is not None
    assert s["event"] != s["fetch"]


# --- 3. value passes the store's UTC RFC3339 guard ---------------------------
def test_source_event_time_passes_assert_utc_rfc3339(conn):
    _round(conn, _normal_rpc())
    s = _snap(conn)
    assert assert_utc_rfc3339(s["event"], "source_event_time") == s["event"]


# --- 4. Z suffix, no +00:00 offset -------------------------------------------
def test_source_event_time_ends_with_z_no_offset(conn):
    _round(conn, _normal_rpc())
    s = _snap(conn)
    assert s["event"].endswith("Z")
    assert "+00:00" not in s["event"]


# --- 5. fetch_time and source_event_time are distinct values -----------------
def test_fetch_time_differs_from_source_event_time(conn):
    # Block timestamp 100s (1970-01-01) is far in the past relative to now.
    _round(conn, _normal_rpc("0x64"))
    s = _snap(conn)
    assert s["event"] != s["fetch"]


# --- 6. fetch_time regression: still RFC3339 and non-empty -------------------
def test_fetch_time_still_rfc3339_nonempty(conn):
    _round(conn, _normal_rpc())
    s = _snap(conn)
    assert s["fetch"]
    assert assert_utc_rfc3339(s["fetch"], "fetch_time") == s["fetch"]


# --- 7. large timestamp converts without overflow ----------------------------
def test_large_timestamp_converts(conn):
    _round(conn, _normal_rpc("0x67000000"))
    assert _snap(conn)["event"] == "2024-10-04T14:47:28Z"


# --- 8. zero is a legal epoch instant, not "unavailable" ---------------------
def test_zero_timestamp_writes_epoch_not_none(conn):
    _round(conn, _normal_rpc("0x0"))
    s = _snap(conn)
    assert s["event"] is not None
    assert s["event"] == "1970-01-01T00:00:00Z"


# --- 9. idempotent duplicate payload: IntegrityError still swallowed ---------
def test_idempotent_duplicate_payload_swallowed(conn, monkeypatch):
    rpc = _normal_rpc("0x64")
    monkeypatch.setattr(collector, "_utc_now",
                        lambda: "2026-09-09T09:00:00.000001Z")
    _round(conn, rpc)
    monkeypatch.setattr(collector, "_utc_now",
                        lambda: "2026-09-09T09:00:00.000002Z")
    _round(conn, rpc)  # identical payload -> duplicate PK, must not raise
    n = conn.execute(
        "SELECT COUNT(*) FROM rh_source_snapshots").fetchone()[0]
    assert n == 1


# --- 10/11. quality regression ------------------------------------------------
def test_quality_partial_when_errors(conn):
    _round(conn, _block_rpc(latest=_block("0x64"), good_block=_block("0x64"),
                            slot0_err={"code": -32602, "message": "bad"}))
    assert _snap(conn)["quality"] == "PARTIAL"


def test_quality_ok_when_no_errors(conn):
    _round(conn, _normal_rpc())
    assert _snap(conn)["quality"] == "OK"


# --- 12/13. schema_kind / raw_ref regression ----------------------------------
def test_schema_kind_json_rpc_v1(conn):
    _round(conn, _normal_rpc())
    assert _snap(conn)["schema"] == "JSON_RPC_V1"


def test_raw_ref_none(conn):
    _round(conn, _normal_rpc())
    assert _snap(conn)["raw_ref"] is None


# --- 14. rh_market_states columns untouched by this package -------------------
def test_market_states_columns_unchanged(conn, monkeypatch):
    stamp = "2026-09-09T09:00:00.000000Z"
    _round(conn, _normal_rpc("0x64"), monkeypatch=monkeypatch, stamp=stamp,
           now_fn=lambda: 200.0)
    m = _market(conn)
    expected_session = classify_session(
        datetime.fromisoformat(stamp.replace("Z", "+00:00")),
        calendar=None)[0]
    assert m["session"] == expected_session
    assert m["hash"] == GOOD_HASH
    assert m["number"] == GOOD_BLOCK_INT
    assert m["age"] == 100  # int(now_fn() - block_timestamp) = 200 - 100
    assert m["mid"] is not None


# --- 15. no good block at all -> no specific-block call, event None ----------
def test_source_event_time_none_when_no_good_block(conn):
    _round(conn, _block_rpc(latest_err={"code": -32603, "message": "down"}))
    s = _snap(conn)
    assert s["event"] is None
    assert s["event"] != s["fetch"]
