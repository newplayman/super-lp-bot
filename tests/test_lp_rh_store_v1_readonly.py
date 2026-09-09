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


# --- RH-02f: block provenance on the six derived tables ----------------------
def _old_table_ddl(table_name):
    """DDL for a derived table as it existed before RH-02f (no provenance cols)."""
    for name, pk, columns in store._TABLES:
        if name == table_name:
            old_cols = [c for c in columns if "derived_block" not in c]
            defs = old_cols + ["PRIMARY KEY (" + ", ".join(pk) + ")"]
            return "CREATE TABLE " + name + " (\n    " + ",\n    ".join(defs) + "\n);"
    raise AssertionError(table_name)


@pytest.mark.parametrize("table", list(store.DERIVED_TABLES))
def test_six_derived_tables_have_provenance_columns(tmp_path, table):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        cols = {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert cols.get("derived_block_hash") == "TEXT"
        assert cols.get("derived_block_number") == "INTEGER"
    finally:
        conn.close()


def test_ensure_columns_idempotent(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store._ensure_columns(conn)
        store._ensure_columns(conn)  # second call must not raise
    finally:
        conn.close()


def test_ensure_columns_upgrades_old_db_in_place_keeps_rows(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    try:
        for table in store.DERIVED_TABLES:
            conn.execute(_old_table_ddl(table))
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO rh_gate_decisions (decision_id, candidate_key, target_mode,"
            " primary_status, terminal_bits_json, decided_at)"
            " VALUES ('d1','c1','shadow','ok','{}','2026-09-07T12:00:00Z')"
        )
        conn.commit()
        store.migrate(conn)  # real upgrade path: _ensure_columns + version check
        assert conn.execute(
            "SELECT count(*) FROM rh_gate_decisions"
        ).fetchone()[0] == 1
        cols = {r[1] for r in conn.execute("PRAGMA table_info(rh_gate_decisions)")}
        assert "derived_block_hash" in cols
        assert "derived_block_number" in cols
    finally:
        conn.close()


@pytest.mark.parametrize("table", list(store.DERIVED_TABLES))
def test_ensure_columns_preserves_primary_keys(tmp_path, table):
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    try:
        conn.execute(_old_table_ddl(table))
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        pk_before = [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[5] > 0]
        store._ensure_columns(conn)
        pk_after = [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[5] > 0]
        assert pk_before == pk_after
    finally:
        conn.close()


def _gate_row(decision_id, *, block_hash=None, block_number=None):
    row = {
        "decision_id": decision_id, "candidate_key": "c", "target_mode": "shadow",
        "primary_status": "ok", "terminal_bits_json": "{}",
        "decided_at": "2026-09-07T12:00:00Z",
    }
    if block_hash is not None:
        row["derived_block_hash"] = block_hash
    if block_number is not None:
        row["derived_block_number"] = block_number
    return row


def test_rows_derived_from_block_null_provenance_not_matched(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store.insert_row(conn, "rh_gate_decisions", _gate_row("d1"))
        result = store.rows_derived_from_block(conn, block_hash="0xaaa")
        assert result["rh_gate_decisions"] == []
    finally:
        conn.close()


def test_rows_derived_from_block_returns_matching_pks_only(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        for i in range(3):
            store.insert_row(
                conn, "rh_gate_decisions",
                _gate_row(f"a{i}", block_hash="0xaaa", block_number=100))
        for i in range(2):
            store.insert_row(
                conn, "rh_gate_decisions",
                _gate_row(f"b{i}", block_hash="0xbbb", block_number=101))
        result = store.rows_derived_from_block(conn, block_hash="0xaaa")
        assert result["rh_gate_decisions"] == [("a0",), ("a1",), ("a2",)]
    finally:
        conn.close()


def test_rows_derived_from_block_unknown_hash_returns_empty_lists(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store.insert_row(
            conn, "rh_gate_decisions",
            _gate_row("d1", block_hash="0xknown", block_number=1))
        result = store.rows_derived_from_block(conn, block_hash="0xdoes_not_exist")
        for table in store.DERIVED_TABLES:
            assert result[table] == []
    finally:
        conn.close()


def test_rows_derived_from_block_tables_without_provenance(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        # rh_gate_decisions: a row with NULL provenance (table is all-NULL).
        store.insert_row(conn, "rh_gate_decisions", _gate_row("d1"))
        # rh_market_states: a row WITH provenance (must not be flagged).
        store.insert_row(conn, "rh_market_states", {
            "asset_address": "0xW", "sample_time": "2026-09-07T12:00:00Z",
            "chain_id": 1, "session": "s", "health_flags_json": "{}",
            "derived_block_hash": "0xknown", "derived_block_number": 5,
        })
        result = store.rows_derived_from_block(conn, block_hash="0xknown")
        # Both fields present: the [] and the without-provenance flag.
        assert result["rh_gate_decisions"] == []
        assert "rh_gate_decisions" in result["tables_without_provenance"]
        assert "rh_market_states" not in result["tables_without_provenance"]
    finally:
        conn.close()


def test_pool_events_pk_still_contains_block_hash(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        pk_cols = [r[1] for r in conn.execute("PRAGMA table_info(rh_pool_events)")
                   if r[5] > 0]
        assert "block_hash" in pk_cols
        assert "block_number" not in pk_cols
    finally:
        conn.close()


def test_rows_derived_from_block_read_only_connection(tmp_path):
    db = tmp_path / "rh.db"
    conn = store.open_store(db)
    store.migrate(conn)
    store.insert_row(
        conn, "rh_gate_decisions",
        _gate_row("d1", block_hash="0xaaa", block_number=1))
    conn.commit()
    conn.close()
    ro = store.open_store(db, read_only=True)
    try:
        result = store.rows_derived_from_block(ro, block_hash="0xaaa")
        assert result["rh_gate_decisions"] == [("d1",)]
    finally:
        ro.close()


def test_provenance_columns_are_nullable(tmp_path):
    conn = store.open_store(tmp_path / "rh.db")
    try:
        store.migrate(conn)
        store.insert_row(conn, "rh_reconciliation_runs", {
            "run_id": "r1", "started_at": "2026-09-07T12:00:00Z", "verdict": "ok",
        })
        row = conn.execute(
            "SELECT derived_block_hash, derived_block_number"
            " FROM rh_reconciliation_runs"
        ).fetchone()
        assert row == (None, None)
    finally:
        conn.close()

