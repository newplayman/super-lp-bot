from __future__ import annotations

import sqlite3
import sys

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts import lp_rh_reorg_resolution_v1_readonly as mod
from scripts import lp_rh_reorg_rollback_v1_readonly as rb
from scripts import lp_rh_store_v1_readonly as store

DERIVED = store.DERIVED_TABLES
NOW = "2026-09-09T00:00:00Z"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store.migrate(conn)
    rb._ensure_columns(conn)
    return conn


def _gate_row(decision_id, *, block_hash=None):
    row = {
        "decision_id": decision_id, "candidate_key": "c",
        "target_mode": "shadow", "primary_status": "ok",
        "terminal_bits_json": "{}", "decided_at": NOW,
    }
    if block_hash is not None:
        row["derived_block_hash"] = block_hash
        row["derived_block_number"] = 100
    return row


def _market_state_row():
    return {
        "asset_address": "0xW", "sample_time": NOW,
        "chain_id": 1, "session": "s", "health_flags_json": "{}",
    }


def _gate_state(conn) -> dict:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT decision_id, invalidated_by_block "
        "FROM rh_gate_decisions ORDER BY decision_id")}


def _counts(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in DERIVED}


def _contested(conn) -> dict:
    """(block_number, hash_a, hash_b) -> (canonical, orphan, status)."""
    return {(r[0], r[1], r[2]): (r[5], r[6], r[7])
            for r in conn.execute(
                "SELECT block_number, hash_a, hash_b, first_seen_at, "
                "resolved_at, canonical_hash, orphaned_hash, status "
                "FROM rh_reorg_contested")}


def test_record_contested_is_contested_and_no_rollback():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    result = mod.record_contested(conn, block_number=1, hash_a="0xaaa",
                                  hash_b="0xbbb", now=NOW)
    assert result["status"] == "CONTESTED"
    assert _contested(conn)[(1, "0xaaa", "0xbbb")][2] == "CONTESTED"
    assert _gate_state(conn)["g1"] is None
    for table in DERIVED:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE invalidated_by_block IS NOT NULL").fetchone()[0]
        assert n == 0


def test_record_contested_idempotent_one_row():
    conn = _conn()
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    r2 = mod.record_contested(conn, block_number=1, hash_a="0xaaa",
                              hash_b="0xbbb", now=NOW)
    assert r2["created"] is False
    assert len(_contested(conn)) == 1


def test_resolve_fn_returns_hash_a():
    conn = _conn()
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xaaa", now=NOW)
    canon, orphan, status = _contested(conn)[(1, "0xaaa", "0xbbb")]
    assert canon == "0xaaa"
    assert orphan == "0xbbb"
    assert status == "RESOLVED"


def test_resolve_fn_returns_hash_b():
    conn = _conn()
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xbbb", now=NOW)
    canon, orphan, status = _contested(conn)[(1, "0xaaa", "0xbbb")]
    assert canon == "0xbbb"
    assert orphan == "0xaaa"
    assert status == "RESOLVED"


def test_resolve_fn_none_stays_contested_no_rollback():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: None, now=NOW)
    canon, orphan, status = _contested(conn)[(1, "0xaaa", "0xbbb")]
    assert orphan is None
    assert status == "CONTESTED"
    assert _gate_state(conn)["g1"] is None


def test_resolve_fn_third_hash_unresolvable_no_rollback():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    result = mod.resolve_contested(conn, block_number=1,
                                   canonical_hash_fn=lambda bn: "0xzzz",
                                   now=NOW)
    canon, orphan, status = _contested(conn)[(1, "0xaaa", "0xbbb")]
    assert orphan is None
    assert status == "UNRESOLVABLE"
    assert result["unresolvable"] == 1
    assert _gate_state(conn)["g1"] is None


def test_apply_only_resolved_rows():
    conn = _conn()
    for h in ("0xaaa", "0xbbb", "0xccc", "0xddd", "0xeee", "0xfff"):
        store.insert_row(conn, "rh_gate_decisions", _gate_row("g_" + h, block_hash=h))
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.record_contested(conn, block_number=2, hash_a="0xccc", hash_b="0xddd", now=NOW)
    mod.resolve_contested(conn, block_number=2,
                          canonical_hash_fn=lambda bn: "0xzzz", now=NOW)
    mod.record_contested(conn, block_number=3, hash_a="0xeee", hash_b="0xfff", now=NOW)
    mod.resolve_contested(conn, block_number=3,
                          canonical_hash_fn=lambda bn: "0xeee", now=NOW)
    result = mod.apply_resolved_rollbacks(conn, now=NOW)
    assert result["resolved_count"] == 1
    state = _gate_state(conn)
    assert state["g_0xfff"] == "0xfff"
    for h in ("0xaaa", "0xbbb", "0xccc", "0xddd", "0xeee"):
        assert state["g_" + h] is None


def test_rollback_marker_equals_orphaned_hash():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xbbb", now=NOW)
    mod.apply_resolved_rollbacks(conn, now=NOW)
    assert _gate_state(conn)["g1"] == "0xaaa"


def test_apply_never_deletes_any_row():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    before = _counts(conn)
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xbbb", now=NOW)
    mod.apply_resolved_rollbacks(conn, now=NOW)
    after = _counts(conn)
    for table in DERIVED:
        assert after[table] == before[table]


def test_apply_is_idempotent():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xbbb", now=NOW)
    first = mod.apply_resolved_rollbacks(conn, now=NOW)
    assert sum(v["marked_total"] for v in first["rolled_back"].values()) == 1
    second = mod.apply_resolved_rollbacks(conn, now=NOW)
    assert sum(v["marked_total"] for v in second["rolled_back"].values()) == 0


def test_undecidable_tables_propagated():
    conn = _conn()
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    store.insert_row(conn, "rh_market_states", _market_state_row())
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    mod.resolve_contested(conn, block_number=1,
                          canonical_hash_fn=lambda bn: "0xbbb", now=NOW)
    result = mod.apply_resolved_rollbacks(conn, now=NOW)
    assert "rh_market_states" in result["undecidable_tables"]


def test_min_depth_not_reached_stays_contested():
    conn = _conn()
    mod.record_contested(conn, block_number=1, hash_a="0xaaa", hash_b="0xbbb", now=NOW)
    result = mod.resolve_contested(conn, block_number=1,
                                   canonical_hash_fn=lambda bn: None, now=NOW,
                                   min_depth=64)
    assert result["still_contested"] == 1
    assert result["resolved"] == 0
    assert _contested(conn)[(1, "0xaaa", "0xbbb")][2] == "CONTESTED"


def test_main_no_action_flags_noop(tmp_path):
    db = tmp_path / "rh.db"
    conn = store.open_store(db)
    store.migrate(conn)
    store.insert_row(conn, "rh_gate_decisions", _gate_row("g1", block_hash="0xaaa"))
    conn.commit()
    before = conn.execute("SELECT * FROM rh_gate_decisions").fetchall()
    conn.close()
    rc = mod.main(["--db", str(db)])
    assert rc == 0
    conn = store.open_store(db)
    after = conn.execute("SELECT * FROM rh_gate_decisions").fetchall()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert after == before
    assert "rh_reorg_contested" not in tables


def test_ensure_table_idempotent():
    conn = _conn()
    mod.ensure_table(conn)
    mod.ensure_table(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "rh_reorg_contested" in tables
