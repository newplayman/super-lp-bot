"""Tests for lp_rh_gas_history_v1_readonly (offline: fake rpc_fn + in-memory SQLite)."""
import sqlite3
import sys
from decimal import Decimal

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts.lp_rh_gas_history_v1_readonly import (  # noqa: E402
    ensure_table, main, record_observation, summarize,
)
from scripts.lp_rh_gas_estimator_v1_readonly import (  # noqa: E402
    round_trip_gas_usd,
)

GAS_PRICE_WEI = 232188000
NATIVE = "2484"
BLOCK_NUM = "0x1234"


def _env(result):
    return {"jsonrpc": "2.0", "id": 1, "result": result, "error": None}


def _err(message):
    return {"jsonrpc": "2.0", "id": 1, "result": None, "error": {"code": -1, "message": message}}


def make_rpc(gas_result=str(GAS_PRICE_WEI), block=BLOCK_NUM, n_receipts=8,
             gas_error=None):
    def rpc(method, params):
        if method == "eth_gasPrice":
            if gas_error is not None:
                return _err(gas_error)
            return _env(gas_result)
        if method == "eth_getBlockByNumber":
            txs = [{"gasUsed": "0x186a0", "effectiveGasPrice": "0xdebe0"}
                   for _ in range(n_receipts)]
            return _env({"number": block, "transactions": txs})
        raise ValueError("unexpected " + method)
    return rpc


def _db():
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    return conn


def _insert(conn, observed_at, gas_usd, block_number=None):
    conn.execute(
        "INSERT INTO rh_gas_observations "
        "(observed_at, gas_usd, block_number) VALUES (?, ?, ?)",
        (observed_at, gas_usd, block_number),
    )
    conn.commit()


def _count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM rh_gas_observations").fetchone()[0]


def test_ensure_table_idempotent():
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    ensure_table(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='rh_gas_observations'").fetchall()
    assert len(tables) == 1


def test_record_observation_writes_one_row():
    conn = _db()
    result = record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    assert result["written"] is True
    assert result["verdict"] == "REFRESHED"
    assert _count(conn) == 1
    gas_usd = conn.execute(
        "SELECT gas_usd FROM rh_gas_observations").fetchone()[0]
    assert isinstance(gas_usd, str)
    expected = str(round_trip_gas_usd(
        gas_price_wei=GAS_PRICE_WEI, native_price_usd=NATIVE))
    assert gas_usd == expected


def test_record_observation_rpc_failure_no_write():
    conn = _db()
    result = record_observation(
        conn, rpc_fn=make_rpc(gas_error="boom"), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    assert result["written"] is False
    assert result["verdict"] == "UNAVAILABLE"
    assert _count(conn) == 0


def test_record_observation_native_none_no_write():
    conn = _db()
    result = record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=None,
        observed_at="2026-01-01T00:00:00Z")
    assert result["written"] is False
    assert _count(conn) == 0


def test_record_observation_native_zero_no_write():
    conn = _db()
    result = record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=0,
        observed_at="2026-01-01T00:00:00Z")
    assert result["written"] is False
    assert _count(conn) == 0


def test_record_observation_native_negative_no_write():
    conn = _db()
    result = record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd="-5",
        observed_at="2026-01-01T00:00:00Z")
    assert result["written"] is False
    assert _count(conn) == 0


def test_record_observation_duplicate_key_one_row():
    conn = _db()
    record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    assert _count(conn) == 1


def test_summarize_empty_table():
    conn = _db()
    s = summarize(conn)
    assert s["n"] == 0
    assert s["median"] is None
    assert s["min"] is None
    assert s["max"] is None
    assert s["p90"] is None
    assert s["latest"] is None
    assert s["oldest_at"] is None
    assert s["newest_at"] is None


def test_summarize_three_known():
    conn = _db()
    _insert(conn, "2026-01-01T00:00:00Z", "1.0")
    _insert(conn, "2026-01-02T00:00:00Z", "3.0")
    _insert(conn, "2026-01-03T00:00:00Z", "2.0")
    s = summarize(conn)
    assert s["n"] == 3
    assert s["min"] == "1.0"
    assert s["max"] == "3.0"
    assert s["median"] == "2.0"


def test_summarize_no_float_collapse():
    conn = _db()
    _insert(conn, "2026-01-01T00:00:00Z", "0.100000000000000001")
    _insert(conn, "2026-01-02T00:00:00Z", "0.100000000000000002")
    s = summarize(conn)
    assert s["min"] == "0.100000000000000001"
    assert s["max"] == "0.100000000000000002"
    assert s["min"] != s["max"]


def test_summarize_p90_ten_known():
    conn = _db()
    for i in range(1, 11):
        _insert(conn, "2026-01-%02dT00:00:00Z" % i, "%d.0" % i)
    s = summarize(conn)
    assert s["n"] == 10
    assert Decimal(s["p90"]) == Decimal("9.1")


def test_summarize_latest_is_newest_not_max():
    conn = _db()
    _insert(conn, "2026-01-01T00:00:00Z", "5.0")
    _insert(conn, "2026-01-02T00:00:00Z", "3.0")
    s = summarize(conn)
    assert s["latest"] == "3.0"  # value at newest observed_at, not the max
    assert s["max"] == "5.0"
    assert s["newest_at"] == "2026-01-02T00:00:00Z"
    assert s["oldest_at"] == "2026-01-01T00:00:00Z"


def test_summarize_single_row():
    conn = _db()
    _insert(conn, "2026-01-01T00:00:00Z", "4.2")
    s = summarize(conn)
    assert s["n"] == 1
    assert s["min"] == s["max"] == s["median"] == s["latest"] == "4.2"


def test_main_summary_no_write(tmp_path):
    db = tmp_path / "gas.db"
    conn = sqlite3.connect(str(db))
    ensure_table(conn)
    _insert(conn, "2026-01-01T00:00:00Z", "1.0")
    conn.close()
    rc = main(["--db", str(db), "--summary"])
    assert rc == 0
    conn = sqlite3.connect(str(db))
    assert _count(conn) == 1
    conn.close()


def test_main_no_flags_no_write(tmp_path):
    db = tmp_path / "gas.db"
    rc = main([])
    assert rc == 0
    assert not db.exists()


def test_gas_usd_is_decimal_text():
    conn = _db()
    record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    gas_usd = conn.execute(
        "SELECT gas_usd FROM rh_gas_observations").fetchone()[0]
    assert isinstance(gas_usd, str)
    assert Decimal(gas_usd) == round_trip_gas_usd(
        gas_price_wei=GAS_PRICE_WEI, native_price_usd=NATIVE)


def test_native_price_usd_is_decimal_text():
    conn = _db()
    record_observation(
        conn, rpc_fn=make_rpc(), native_price_usd=NATIVE,
        observed_at="2026-01-01T00:00:00Z")
    native = conn.execute(
        "SELECT native_price_usd FROM rh_gas_observations").fetchone()[0]
    assert isinstance(native, str)
    assert native == NATIVE
