from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import pytest

from scripts import lp_rh_reorg_rollback_v1_readonly as rb
from scripts import lp_rh_store_v1_readonly as store

DERIVED = store.DERIVED_TABLES


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    return conn


def _gate_row(decision_id, *, block_hash=None):
    row = {
        "decision_id": decision_id, "candidate_key": "c",
        "target_mode": "shadow", "primary_status": "ok",
        "terminal_bits_json": "{}", "decided_at": "2026-09-07T12:00:00Z",
    }
    if block_hash is not None:
        row["derived_block_hash"] = block_hash
        row["derived_block_number"] = 100
    return row


def _seed(conn):
    """Three gate rows derived from 0xaaa, two from 0xbbb."""
    for i in range(3):
        store.insert_row(conn, "rh_gate_decisions",
                         _gate_row(f"a{i}", block_hash="0xaaa"))
    for i in range(2):
        store.insert_row(conn, "rh_gate_decisions",
                         _gate_row(f"b{i}", block_hash="0xbbb"))


def _counts(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in DERIVED}


def _gate_state(conn) -> dict:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT decision_id, invalidated_by_block "
        "FROM rh_gate_decisions ORDER BY decision_id")}


def _market_state_row():
    return {
        "asset_address": "0xW", "sample_time": "2026-09-07T12:00:00Z",
        "chain_id": 1, "session": "s", "health_flags_json": "{}",
    }


def test_plan_counts_only_orphaned_block_rows():
    conn = _conn()
    _seed(conn)
    plan = rb.plan_rollback(conn, orphaned_block_hash="0xaaa")
    assert plan["affected_total"] == 3
    assert plan["affected"]["rh_gate_decisions"] == [("a0",), ("a1",), ("a2",)]
    assert plan["orphaned_block_hash"] == "0xaaa"


def test_apply_marks_only_orphaned_rows():
    conn = _conn()
    _seed(conn)
    result = rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    state = _gate_state(conn)
    assert result["marked_total"] == 3
    for i in range(3):
        assert state[f"a{i}"] == "0xaaa"
    for i in range(2):
        assert state[f"b{i}"] is None


def test_apply_is_idempotent():
    conn = _conn()
    _seed(conn)
    first = rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    after_first = _gate_state(conn)
    second = rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    assert first["marked_total"] == 3
    assert second["marked_total"] == 0
    assert second["already_marked"] == 3
    assert _gate_state(conn) == after_first


def test_apply_never_deletes_any_row():
    conn = _conn()
    _seed(conn)
    before = _counts(conn)
    rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    after = _counts(conn)
    for table in DERIVED:
        assert after[table] == before[table]


def test_plan_undecidable_when_table_lacks_provenance():
    conn = _conn()
    _seed(conn)
    store.insert_row(conn, "rh_market_states", _market_state_row())
    plan = rb.plan_rollback(conn, orphaned_block_hash="0xaaa")
    assert plan["undecidable"] is True
    assert "rh_market_states" in plan["tables_without_provenance"]


def test_apply_still_marks_when_undecidable():
    conn = _conn()
    _seed(conn)
    store.insert_row(conn, "rh_market_states", _market_state_row())
    result = rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    assert result["marked_total"] == 3
    assert result["undecidable"] is True
    assert _gate_state(conn)["a0"] == "0xaaa"


def test_plan_decidable_when_all_provenance_recorded():
    conn = _conn()
    _seed(conn)
    plan = rb.plan_rollback(conn, orphaned_block_hash="0xaaa")
    assert plan["undecidable"] is False
    assert plan["tables_without_provenance"] == []


def test_active_rows_only_excludes_invalidated():
    conn = _conn()
    _seed(conn)
    rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    fragment = rb.active_rows_only("rh_gate_decisions")
    assert fragment == "rh_gate_decisions WHERE invalidated_by_block IS NULL"
    active = conn.execute("SELECT COUNT(*) FROM " + fragment).fetchone()[0]
    assert active == 2


def test_main_dry_run_is_default_and_does_not_modify(tmp_path):
    db = tmp_path / "rh.db"
    conn = store.open_store(db)
    store.migrate(conn)
    _seed(conn)
    before = conn.execute(
        "SELECT * FROM rh_gate_decisions ORDER BY decision_id").fetchall()
    conn.commit()
    conn.close()
    rc = rb.main(["--db", str(db), "--orphaned-block-hash", "0xaaa"])
    assert rc == 0
    conn = store.open_store(db)
    after = conn.execute(
        "SELECT * FROM rh_gate_decisions ORDER BY decision_id").fetchall()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(rh_gate_decisions)")]
    conn.close()
    assert after == before
    assert "invalidated_by_block" not in cols


def test_main_apply_marks_and_writes_out(tmp_path):
    db = tmp_path / "rh.db"
    out = tmp_path / "result.json"
    conn = store.open_store(db)
    store.migrate(conn)
    _seed(conn)
    conn.commit()
    conn.close()
    rc = rb.main(["--db", str(db), "--orphaned-block-hash", "0xaaa",
                  "--apply", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["mode"] == "apply"
    assert payload["marked_total"] == 3
    conn = store.open_store(db)
    state = _gate_state(conn)
    conn.close()
    assert state["a0"] == "0xaaa"
    assert state["b0"] is None


def test_ensure_columns_idempotent_and_pk_unchanged():
    conn = _conn()
    _seed(conn)
    pk_before = {
        t: [(r[1], r[5]) for r in conn.execute(f"PRAGMA table_info({t})")
            if r[5] > 0]
        for t in DERIVED}
    rb._ensure_columns(conn)
    rb._ensure_columns(conn)
    for table in DERIVED:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        assert cols.count("invalidated_by_block") == 1
        pk_after = [(r[1], r[5]) for r in
                    conn.execute(f"PRAGMA table_info({table})") if r[5] > 0]
        assert pk_after == pk_before[table]


def test_rollback_unknown_hash_is_noop():
    conn = _conn()
    _seed(conn)
    plan = rb.plan_rollback(conn, orphaned_block_hash="0xdoes_not_exist")
    assert plan["affected_total"] == 0
    result = rb.apply_rollback(conn, orphaned_block_hash="0xdoes_not_exist",
                               plan=plan)
    assert result["marked_total"] == 0
    assert result["already_marked"] == 0


def test_plan_is_read_only():
    conn = _conn()
    _seed(conn)
    rb.plan_rollback(conn, orphaned_block_hash="0xaaa")
    cols = [r[1] for r in
            conn.execute("PRAGMA table_info(rh_gate_decisions)")]
    assert "invalidated_by_block" not in cols


def test_apply_without_plan_matches_explicit_plan():
    conn = _conn()
    _seed(conn)
    implicit = rb.apply_rollback(conn, orphaned_block_hash="0xaaa")
    conn2 = _conn()
    _seed(conn2)
    plan = rb.plan_rollback(conn2, orphaned_block_hash="0xaaa")
    explicit = rb.apply_rollback(conn2, orphaned_block_hash="0xaaa", plan=plan)
    assert implicit["marked"] == explicit["marked"]
    assert implicit["marked_total"] == explicit["marked_total"] == 3


def test_apply_rejects_plan_for_other_block():
    conn = _conn()
    _seed(conn)
    plan = rb.plan_rollback(conn, orphaned_block_hash="0xaaa")
    with pytest.raises(ValueError):
        rb.apply_rollback(conn, orphaned_block_hash="0xbbb", plan=plan)
