"""Paired provenance tests for scripts/lp_rh_collector_v1_readonly.py (RH-02p).

The collector now writes the rh_market_states provenance columns
(derived_block_hash / derived_block_number) and a real market session.
All RPC traffic is injected via fake rpc_fn callables (never the network);
all databases live under tmp_path. The sample instant is controlled by
monkeypatching collector._utc_now.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

import pytest

from scripts import lp_rh_collector_v1_readonly as collector
from scripts.lp_rh_market_session_v1_readonly import SESSIONS
from scripts.lp_rh_store_v1_readonly import migrate, open_store

# sqrtPriceX96 for the identity-gated target pool (dec0=18, dec1=6).
SQRT_PRICE = 3953938817749275760872870
SLOT0_HEX = "0x" + format(SQRT_PRICE, "064x")

LATEST_NUMBER = "0x1dcd1"
LATEST_HASH = "0xLATESTHASH"
GOOD_HASH = "0xGOODHASH"
LATEST_BLOCK = {"number": LATEST_NUMBER, "hash": LATEST_HASH,
                "timestamp": "0x65", "baseFeePerGas": "0x3b9aca00"}
GOOD_BLOCK = {"number": LATEST_NUMBER, "hash": GOOD_HASH,
              "timestamp": "0x65", "baseFeePerGas": "0x3b9aca00"}
GOOD_BLOCK_INT = int(LATEST_NUMBER, 16)


def _block_rpc(latest=None, latest_err=None, blocks=None, blocks_err=None,
               blocks_null=False):
    """rpc_fn serving eth_getBlockByNumber by block identifier; no network.

    latest / latest_err: response for the ["latest", False] call.
    blocks: dict mapping the specific-block hex identifier to its block.
    blocks_err / blocks_null: force the specific-block call to error / null.
    eth_call: normal values so the round is NORMAL with a price.
    """
    def rpc_fn(method, params=None, **_kw):
        if method == "eth_getBlockByNumber":
            ident = params[0]
            if ident == "latest":
                if latest_err is not None:
                    return None, latest_err, 12
                return latest, None, 5
            if blocks_err is not None:
                return None, blocks_err, 9
            if blocks_null:
                return None, None, 5
            return (blocks or {}).get(ident), None, 5
        data = params[0]["data"]
        if data == collector.SEL_DECIMALS:
            dec = "0x12" if params[0]["to"] == collector.TOKEN0 else "0x6"
            return dec, None, 4
        if data == collector.SEL_SLOT0:
            return SLOT0_HEX, None, 4
        return "0x1", None, 4
    return rpc_fn


_COLS = ("derived_block_hash", "derived_block_number", "session",
         "reference_mid", "reference_age_secs", "source_payload_hash",
         "health_flags_json", "reference_bid", "reference_ask",
         "multiplier_human", "oracle_paused")


def _fields(conn):
    row = conn.execute(
        "SELECT " + ",".join(_COLS) + " FROM rh_market_states").fetchone()
    return dict(zip(("hash", "number", "session", "mid", "age", "payload",
                     "flags", "bid", "ask", "mult", "paused"), row))


@pytest.fixture
def conn(tmp_path):
    c = open_store(tmp_path / "rh_prov.db")
    migrate(c)
    yield c
    c.close()


def _normal_round(conn, monkeypatch=None, stamp=None):
    """Run one NORMAL round; optionally pin the sample instant via monkeypatch."""
    if stamp is not None:
        monkeypatch.setattr(collector, "_utc_now", lambda: stamp)
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest=LATEST_BLOCK,
                          blocks={LATEST_NUMBER: GOOD_BLOCK}))


# --- 1. normal path: provenance columns --------------------------------------
def test_normal_path_provenance(conn):
    _normal_round(conn)
    f = _fields(conn)
    assert f["hash"] == GOOD_HASH
    assert f["number"] == GOOD_BLOCK_INT


# --- 2. fallback to last_good_block ------------------------------------------
def test_fallback_last_good_block_hash(conn):
    last_good = 193000
    fb = {"number": hex(last_good), "hash": "0xFALLBACKHASH",
          "timestamp": "0x65", "baseFeePerGas": "0x3b9aca00"}
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=last_good,
        rpc_fn=_block_rpc(latest_err={"code": -32601, "message": "nope"},
                          blocks={hex(last_good): fb}))
    f = _fields(conn)
    assert f["hash"] == "0xFALLBACKHASH"
    assert f["hash"] != LATEST_HASH
    assert f["number"] == last_good


# --- 3. good_block fetch error -> hash None, other columns intact ------------
def test_good_block_fetch_error_hash_none(conn):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest=LATEST_BLOCK,
                          blocks_err={"code": -32603,
                                      "message": "block fetch failed"}))
    f = _fields(conn)
    assert f["hash"] is None
    assert f["hash"] != ""
    assert f["hash"] != LATEST_HASH
    assert f["number"] == GOOD_BLOCK_INT
    assert f["mid"] is not None
    assert len(f["payload"]) == 64
    assert f["flags"] == "[]"
    assert f["session"] in SESSIONS


# --- 4. good_block fetch null result -> hash None ----------------------------
def test_good_block_fetch_null_hash_none(conn):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest=LATEST_BLOCK, blocks_null=True))
    f = _fields(conn)
    assert f["hash"] is None
    assert f["number"] == GOOD_BLOCK_INT


# --- 5. block object missing hash key -> None --------------------------------
def test_block_missing_hash_key_none(conn):
    no_hash = {"number": LATEST_NUMBER, "timestamp": "0x65",
               "baseFeePerGas": "0x3b9aca00"}
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest=LATEST_BLOCK,
                          blocks={LATEST_NUMBER: no_hash}))
    f = _fields(conn)
    assert f["hash"] is None
    assert f["number"] == GOOD_BLOCK_INT


# --- 6. first round, no history -> both None, no exception -------------------
def test_first_round_no_history_both_none(conn):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest_err={"code": -32601, "message": "nope"}))
    f = _fields(conn)
    assert f["hash"] is None
    assert f["number"] is None


# --- 7-10. session at pinned sample instants (Jan 2026 = EST, UTC-5) ---------
# 2026-01-13 is a Tuesday, 2026-01-17 a Saturday; neither is a holiday.
def test_session_rth_weekday_10am_et(conn, monkeypatch):
    _normal_round(conn, monkeypatch=monkeypatch,
                  stamp="2026-01-13T15:00:00.000000Z")  # ET 10:00
    assert _fields(conn)["session"] == "RTH"


def test_session_overnight_weekday_02am_et(conn, monkeypatch):
    _normal_round(conn, monkeypatch=monkeypatch,
                  stamp="2026-01-13T07:00:00.000000Z")  # ET 02:00
    assert _fields(conn)["session"] == "OVERNIGHT"


def test_session_premarket_weekday_05am_et(conn, monkeypatch):
    _normal_round(conn, monkeypatch=monkeypatch,
                  stamp="2026-01-13T10:00:00.000000Z")  # ET 05:00
    assert _fields(conn)["session"] == "PREMARKET"


def test_session_weekend_saturday(conn, monkeypatch):
    _normal_round(conn, monkeypatch=monkeypatch,
                  stamp="2026-01-17T15:00:00.000000Z")
    assert _fields(conn)["session"] == "WEEKEND"


# --- 11. unparseable sample instant -> UNKNOWN --------------------------------
def test_unparseable_instant_session_unknown():
    assert collector._classify_sample_session("not-a-timestamp") == "UNKNOWN"
    assert collector._classify_sample_session("") == "UNKNOWN"
    assert collector._classify_sample_session(None) == "UNKNOWN"


# --- 12. written session always belongs to SESSIONS ---------------------------
def test_written_session_belongs_to_sessions(conn, monkeypatch):
    for stamp in ("2026-01-13T15:00:00.000000Z", "2026-01-17T15:00:00.000000Z",
                  "2026-01-13T07:00:00.000000Z", "2026-01-13T10:00:00.000000Z"):
        _normal_round(conn, monkeypatch=monkeypatch, stamp=stamp)
    sessions = [r[0] for r in conn.execute(
        "SELECT session FROM rh_market_states ORDER BY rowid")]
    assert len(sessions) == 4
    assert all(s in SESSIONS for s in sessions)


# --- 13. regression: existing columns unchanged -------------------------------
def test_regression_reference_mid(conn):
    _normal_round(conn)
    assert Decimal("2490.0") < Decimal(_fields(conn)["mid"]) < Decimal("2491.0")


def test_regression_age_payload_flags(conn):
    collector.collect_round(
        conn, dec0=18, dec1=6, last_good_block=None,
        rpc_fn=_block_rpc(latest=LATEST_BLOCK,
                          blocks={LATEST_NUMBER: GOOD_BLOCK}),
        now_fn=lambda: 1_000_000.0)
    f = _fields(conn)
    assert f["age"] == 1_000_000 - 0x65  # now - block timestamp, fixed clock
    assert len(f["payload"]) == 64
    int(f["payload"], 16)  # sha256 hex
    assert f["flags"] == "[]"


# --- 14. regression: REST-only columns still None ------------------------------
def test_regression_rest_columns_still_none(conn):
    _normal_round(conn)
    f = _fields(conn)
    assert f["bid"] is None
    assert f["ask"] is None
    assert f["mult"] is None
    assert f["paused"] is None
