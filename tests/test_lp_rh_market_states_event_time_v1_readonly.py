"""Paired tests for RH-02w: rh_market_states.source_event_time column.

Verifies the new column is present on a fresh DB, added idempotently to a
legacy DB without losing rows, and filled with exactly the same value as
rh_source_snapshots.source_event_time (one variable, not recomputed). Also
regresses the surrounding columns and the primary key. All RPC traffic is
injected via fake rpc_fn callables (never the network); all databases live
under tmp_path.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
from decimal import Decimal

import pytest

from scripts import lp_rh_collector_v1_readonly as collector
from scripts.lp_rh_market_session_v1_readonly import SESSIONS
from scripts.lp_rh_store_v1_readonly import (
    assert_utc_rfc3339, insert_row, migrate, open_store)

# sqrtPriceX96 for the identity-gated target pool (dec0=18, dec1=6).
SQRT_PRICE = 3953938817749275760872870
SLOT0_HEX = "0x" + format(SQRT_PRICE, "064x")

LATEST_NUMBER = "0x1dcd1"
GOOD_HASH = "0xGOODHASH"
GOOD_BLOCK_INT = int(LATEST_NUMBER, 16)


def _block_rpc(timestamp_hex, blocks_err=None, blocks_null=False):
    """rpc_fn serving eth_getBlockByNumber; no network.

    latest: the ["latest", False] call (sets block_number / good_block).
    specific-block: the hex(good_block) call that carries the timestamp.
    eth_call: normal values so the round is NORMAL with a price.
    """
    latest = {"number": LATEST_NUMBER, "hash": "0xLATESTHASH",
              "timestamp": timestamp_hex, "baseFeePerGas": "0x3b9aca00"}
    good = {"number": LATEST_NUMBER, "hash": GOOD_HASH,
            "timestamp": timestamp_hex, "baseFeePerGas": "0x3b9aca00"}
    blocks = {LATEST_NUMBER: good}

    def rpc_fn(method, params=None, **_kw):
        if method == "eth_getBlockByNumber":
            ident = params[0]
            if ident == "latest":
                return latest, None, 5
            if blocks_err is not None:
                return None, blocks_err, 9
            if blocks_null:
                return None, None, 5
            return blocks.get(ident), None, 5
        data = params[0]["data"]
        if data == collector.SEL_DECIMALS:
            dec = "0x12" if params[0]["to"] == collector.TOKEN0 else "0x6"
            return dec, None, 4
        if data == collector.SEL_SLOT0:
            return SLOT0_HEX, None, 4
        return "0x1", None, 4
    return rpc_fn


def _col(conn, column):
    """The single rh_market_states row's value for `column`."""
    return conn.execute(
        "SELECT " + column + " FROM rh_market_states").fetchone()[0]


@pytest.fixture
def conn(tmp_path):
    c = open_store(tmp_path / "rh_evtime.db")
    migrate(c)
    yield c
    c.close()


def _round(conn, timestamp_hex, **kw):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(timestamp_hex, **kw))


# --- 1. fresh DB: migrate creates the column ---------------------------------
def test_migrate_new_db_has_source_event_time(conn):
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(rh_market_states)").fetchall()}
    assert "source_event_time" in cols


# --- 2. legacy DB: column added, rows kept, value NULL ------------------------
def test_migrate_old_db_adds_column_keeps_rows_null(tmp_path):
    c = sqlite3.connect(tmp_path / "old.db")
    c.execute(
        "CREATE TABLE rh_market_states ("
        "asset_address TEXT NOT NULL, sample_time TEXT NOT NULL,"
        "chain_id INTEGER NOT NULL, source_payload_hash TEXT,"
        "session TEXT NOT NULL, health_flags_json TEXT NOT NULL,"
        "reference_bid TEXT, reference_ask TEXT, reference_mid TEXT,"
        "reference_age_secs INTEGER, multiplier_human TEXT,"
        "oracle_paused INTEGER, derived_block_hash TEXT,"
        "derived_block_number INTEGER,"
        "PRIMARY KEY (asset_address, sample_time))")
    c.execute("INSERT INTO rh_market_states"
              " (asset_address, sample_time, chain_id, session,"
              " health_flags_json) VALUES ('0xA',"
              " '2026-01-01T00:00:00.000000Z', 4663, 'RTH', '[]')")
    c.execute("INSERT INTO rh_market_states"
              " (asset_address, sample_time, chain_id, session,"
              " health_flags_json) VALUES ('0xA',"
              " '2026-01-02T00:00:00.000000Z', 4663, 'RTH', '[]')")
    c.commit()
    migrate(c)
    cols = {r[1] for r in c.execute(
        "PRAGMA table_info(rh_market_states)").fetchall()}
    assert "source_event_time" in cols
    rows = c.execute(
        "SELECT sample_time, source_event_time FROM rh_market_states"
        " ORDER BY sample_time").fetchall()
    assert [r[0] for r in rows] == [
        "2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"]
    assert rows[0][1] is None
    assert rows[1][1] is None
    c.close()


# --- 3. migrate is idempotent -------------------------------------------------
def test_migrate_idempotent_twice(conn):
    migrate(conn)
    migrate(conn)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(rh_market_states)").fetchall()}
    assert "source_event_time" in cols


# --- 4. exact value for a known block timestamp -------------------------------
def test_source_event_time_exact_value(conn):
    _round(conn, "0x64")  # 100s epoch
    assert _col(conn, "source_event_time") == "1970-01-01T00:01:40Z"


# --- 5. same value as rh_source_snapshots in the same round -------------------
def test_source_event_time_same_as_snapshots(conn):
    _round(conn, "0x64")
    ms = _col(conn, "source_event_time")
    snap = conn.execute(
        "SELECT source_event_time FROM rh_source_snapshots").fetchone()[0]
    assert ms == snap
    assert ms == "1970-01-01T00:01:40Z"


# --- 6. timestamp unavailable -> None, never sample_time ----------------------
def test_source_event_time_none_when_unavailable(conn):
    _round(conn, "0x64", blocks_err={"code": -32603, "message": "fail"})
    ms = _col(conn, "source_event_time")
    assert ms is None
    assert ms != _col(conn, "sample_time")


# --- 7. zero timestamp is a real value, distinct from unavailable ------------
def test_source_event_time_zero_timestamp(conn):
    _round(conn, "0x0")
    assert _col(conn, "source_event_time") == "1970-01-01T00:00:00Z"


# --- 8. written value passes the store's RFC3339 guard ------------------------
def test_source_event_time_passes_rfc3339(conn):
    _round(conn, "0x64")
    val = _col(conn, "source_event_time")
    assert assert_utc_rfc3339(val, "source_event_time") == val


# --- 9-13. regression: surrounding columns unchanged (RH-02p / RH-02u) --------
def test_regression_session(conn):
    _round(conn, "0x64")
    assert _col(conn, "session") in SESSIONS


def test_regression_derived_block_hash(conn):
    _round(conn, "0x64")
    assert _col(conn, "derived_block_hash") == GOOD_HASH


def test_regression_derived_block_number(conn):
    _round(conn, "0x64")
    assert _col(conn, "derived_block_number") == GOOD_BLOCK_INT


def test_regression_reference_age_secs(conn):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc("0x65"), now_fn=lambda: 1_000_000.0)
    assert _col(conn, "reference_age_secs") == 1_000_000 - 0x65


def test_regression_reference_mid(conn):
    _round(conn, "0x64")
    assert Decimal("2490.0") < Decimal(_col(conn, "reference_mid")) \
        < Decimal("2491.0")


# --- 14. primary key still (asset_address, sample_time) -----------------------
def test_pk_duplicate_no_second_row(conn):
    info = conn.execute("PRAGMA table_info(rh_market_states)").fetchall()
    pk = {r[1]: r[5] for r in info if r[5] > 0}
    assert set(pk) == {"asset_address", "sample_time"}
    row = {"asset_address": "0xA",
           "sample_time": "2026-01-01T00:00:00.000000Z",
           "chain_id": 4663, "session": "RTH", "health_flags_json": "[]"}
    insert_row(conn, "rh_market_states", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(conn, "rh_market_states", row)
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_market_states").fetchone()[0] == 1


# --- 15. this package must not introduce oracle_updated_at --------------------
def test_no_oracle_updated_at_column(conn):
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(rh_market_states)").fetchall()}
    assert "oracle_updated_at" not in cols
