from __future__ import annotations

import json
import sqlite3

import pytest

from scripts import lp_rh_store_v1_readonly as store

EXPECTED_TABLES = frozenset({
    "rh_source_snapshots", "rh_assets", "rh_contract_attestations",
    "rh_pool_registry", "rh_pool_events", "rh_market_states",
    "rh_rpc_health", "rh_economic_evaluations", "rh_gate_decisions",
    "rh_shadow_positions", "rh_journal", "rh_position_marks",
    "rh_bucket_reservations", "rh_tx_intents", "rh_tx_receipts",
    "rh_reconciliation_runs",
})


def _rh_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rh_%'"
    ).fetchall()
    return [row[0] for row in rows]


def _journal_row(event_id="e1", idem="k1", amount="123"):
    return {
        "event_id": event_id, "idempotency_key": idem,
        "account_debit": "a", "account_credit": "b", "asset": "WETH",
        "amount_raw": amount, "is_external_flow": 0,
        "booked_at": "2026-09-07T12:00:00Z",
    }


# --- schema / migrate -------------------------------------------------------
def test_migrate_creates_all_sixteen_tables(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        assert set(_rh_tables(conn)) == EXPECTED_TABLES
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        assert store.migrate(conn) == 1
        assert store.migrate(conn) == 1
        assert len(_rh_tables(conn)) == 16
    finally:
        conn.close()


def test_wal_mode_and_foreign_keys(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        conn.close()


def test_no_real_column_types(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        for table in _rh_tables(conn):
            for record in conn.execute(f"PRAGMA table_info({table})"):
                assert record[2] in {"TEXT", "INTEGER"}, (table, record[1], record[2])
    finally:
        conn.close()


# --- decimal / UTC guards ---------------------------------------------------
def test_decimal_text_rejects_float():
    with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
        store.assert_decimal_text(1.5, "amount_raw")


def test_decimal_text_rejects_bool():
    with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
        store.assert_decimal_text(True, "amount_raw")


def test_decimal_text_accepts_big_int_and_int():
    big = "123456789012345678901234567890"
    assert store.assert_decimal_text(big, "x") == big
    assert store.assert_decimal_text(123, "x") == "123"
    assert store.assert_decimal_text("-0.5", "x") == "-0.5"


def test_decimal_text_none_passthrough():
    assert store.assert_decimal_text(None, "x") is None


def test_decimal_text_rejects_bad_string():
    with pytest.raises(ValueError, match="INVALID_DECIMAL_TEXT"):
        store.assert_decimal_text("1.2.3", "x")


def test_utc_rfc3339_valid():
    assert store.assert_utc_rfc3339("2026-09-07T12:00:00Z", "t") == "2026-09-07T12:00:00Z"
    assert store.assert_utc_rfc3339("2026-09-07T12:00:00.123+00:00", "t") == "2026-09-07T12:00:00.123+00:00"
    assert store.assert_utc_rfc3339(None, "t") is None


@pytest.mark.parametrize("bad", [
    "2026-09-07 12:00:00", "2026-09-07T12:00:00+02:00",
    "2026-09-07T12:00:00", 1757246400,
])
def test_utc_rfc3339_invalid(bad):
    with pytest.raises(ValueError, match="NON_UTC_TIMESTAMP"):
        store.assert_utc_rfc3339(bad, "t")


# --- insert_row -------------------------------------------------------------
def test_insert_row_rejects_float_money(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        row = _journal_row(amount=1.5)
        with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
            store.insert_row(conn, "rh_journal", row)
    finally:
        conn.close()


def test_insert_row_valid_and_idempotency_conflict(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store.insert_row(conn, "rh_journal", _journal_row(event_id="e1", idem="k1"))
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_row(conn, "rh_journal", _journal_row(event_id="e2", idem="k1"))
        got = conn.execute("SELECT amount_raw FROM rh_journal WHERE event_id='e1'").fetchone()
        assert got == ("123",)
    finally:
        conn.close()


def test_insert_row_unknown_table(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        with pytest.raises(ValueError, match="UNKNOWN_TABLE"):
            store.insert_row(conn, "not_a_table", {})
    finally:
        conn.close()


def test_insert_row_empty_row(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        with pytest.raises(ValueError, match="EMPTY_ROW"):
            store.insert_row(conn, "rh_journal", {})
    finally:
        conn.close()


def _pool_event(block_hash, block_number):
    return {
        "chain_id": 1, "block_hash": block_hash, "tx_hash": "t1",
        "log_index": 0, "block_number": block_number, "pool_key": "p",
        "event_type": "swap", "amount0_raw": "5", "observed_at": "2026-09-07T12:00:00Z",
    }


def test_pool_events_dedup_by_hash_not_block_number(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store.insert_row(conn, "rh_pool_events", _pool_event("b1", 100))
        with pytest.raises(sqlite3.IntegrityError):
            store.insert_row(conn, "rh_pool_events", _pool_event("b1", 100))
        store.insert_row(conn, "rh_pool_events", _pool_event("b2", 100))
        assert conn.execute("SELECT count(*) FROM rh_pool_events").fetchone()[0] == 2
    finally:
        conn.close()


# --- budget -----------------------------------------------------------------
def test_budget_status_ok(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    store.migrate(conn)
    conn.close()
    assert store.budget_status(tmp_path / "rh.db")["state"] == "OK"


def test_budget_status_warn_or_over(tmp_path, monkeypatch):
    conn = store.open_store(tmp_path / "rh.db")
    store.migrate(conn)
    conn.close()
    monkeypatch.setattr(store, "SOFT_BUDGET_BYTES", 1)
    assert store.budget_status(tmp_path / "rh.db")["state"] in {"WARN", "OVER"}


# --- CLI --------------------------------------------------------------------
def test_main_init_lists_sixteen_tables(tmp_path, capsys):
    db = tmp_path / "rh.db"
    assert store.main(["--db", str(db), "--init"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema_version"] == 1
    assert set(out["tables"]) == EXPECTED_TABLES
    assert out["budget"]["state"] == "OK"


def test_main_status_read_only(tmp_path, capsys):
    db = tmp_path / "rh.db"
    store.main(["--db", str(db), "--init"])
    capsys.readouterr()
    assert store.main(["--db", str(db), "--status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["tables"]) == EXPECTED_TABLES


def test_main_no_flag_returns_2(capsys):
    assert store.main([]) == 2

