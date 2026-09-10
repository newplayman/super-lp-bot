from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from scripts import lp_rh_bucket_ledger_v1_readonly as ledger
from scripts import lp_rh_store_v1_readonly as store

NOW = "2026-09-07T12:00:00Z"
C100 = Decimal("100")


@pytest.fixture
def conn(tmp_path):
    c = store.open_store(tmp_path / "rh.db")
    ledger.migrate_checked(c)
    yield c
    c.close()


def _pending_count(c, bucket=None):
    sql = "SELECT count(*) FROM rh_bucket_reservations WHERE status='PENDING'"
    args = ()
    if bucket is not None:
        sql += " AND bucket=?"
        args = (bucket,)
    return c.execute(sql, args).fetchone()[0]


# --- pure math -------------------------------------------------------------
def test_bucket_active_cap_c100_exact():
    assert ledger.bucket_active_cap(C100, "CORE") == Decimal("42.5")
    assert ledger.bucket_active_cap(C100, "STOCK") == Decimal("21")
    assert ledger.bucket_active_cap(C100, "MEME") == Decimal("8")


def test_bucket_budget_c100():
    assert ledger.bucket_budget(C100, "CORE") == Decimal("50")
    assert ledger.bucket_budget(C100, "MEME") == Decimal("20")


# --- T27: atomic competing reservations ------------------------------------
def test_t27_competing_reservations(conn):
    r1 = ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                            amount_usd=Decimal("40"), capital_usd=C100, now=NOW)
    assert r1["granted"] is True
    assert r1["room_after"] == "2.5"
    r2 = ledger.try_reserve(conn, intent_id="i2", bucket="CORE",
                            amount_usd=Decimal("10"), capital_usd=C100, now=NOW)
    assert r2["granted"] is False
    assert r2["reason"] == "BUCKET_ACTIVE_CAP_EXCEEDED"
    assert _pending_count(conn, "CORE") == 1


# --- BROADCAST_UNKNOWN counts toward occupancy -----------------------------
def test_broadcast_unknown_counts_toward_occupancy(conn):
    r1 = ledger.try_reserve(conn, intent_id="i1", bucket="MEME",
                            amount_usd=Decimal("5"), capital_usd=C100, now=NOW)
    assert r1["granted"] is True
    ledger.set_status(conn, "i1", "BROADCAST_UNKNOWN", now=NOW)
    r2 = ledger.try_reserve(conn, intent_id="i2", bucket="MEME",
                            amount_usd=Decimal("4"), capital_usd=C100, now=NOW)
    assert r2["granted"] is False
    assert r2["reason"] == "BUCKET_ACTIVE_CAP_EXCEEDED"


# --- release ----------------------------------------------------------------
def test_release_broadcast_unknown_rejected(conn):
    ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                       amount_usd=Decimal("10"), capital_usd=C100, now=NOW)
    ledger.set_status(conn, "i1", "BROADCAST_UNKNOWN", now=NOW)
    with pytest.raises(ValueError, match="CANNOT_RELEASE_BROADCAST_UNKNOWN"):
        ledger.release(conn, "i1", now=NOW, reason="test")


def test_release_pending_frees_room(conn):
    ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                       amount_usd=Decimal("40"), capital_usd=C100, now=NOW)
    assert ledger.release(conn, "i1", now=NOW, reason="cancelled") is True
    r = ledger.try_reserve(conn, intent_id="i2", bucket="CORE",
                           amount_usd=Decimal("42.5"), capital_usd=C100, now=NOW)
    assert r["granted"] is True


def test_release_unknown_intent_returns_false(conn):
    assert ledger.release(conn, "nope", now=NOW, reason="x") is False


# --- validation -------------------------------------------------------------
def test_try_reserve_non_positive_amount(conn):
    with pytest.raises(ValueError, match="NON_POSITIVE_RESERVATION"):
        ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                           amount_usd=Decimal("0"), capital_usd=C100, now=NOW)
    with pytest.raises(ValueError, match="NON_POSITIVE_RESERVATION"):
        ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                           amount_usd=Decimal("-5"), capital_usd=C100, now=NOW)


def test_try_reserve_unknown_bucket(conn):
    with pytest.raises(ValueError, match="UNKNOWN_BUCKET"):
        ledger.try_reserve(conn, intent_id="i1", bucket="FOO",
                           amount_usd=Decimal("1"), capital_usd=C100, now=NOW)


def test_try_reserve_duplicate_intent_id(conn):
    ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                       amount_usd=Decimal("10"), capital_usd=C100, now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                           amount_usd=Decimal("10"), capital_usd=C100, now=NOW)


def test_set_status_invalid_rejected(conn):
    ledger.try_reserve(conn, intent_id="i1", bucket="CORE",
                       amount_usd=Decimal("10"), capital_usd=C100, now=NOW)
    with pytest.raises(ValueError, match="INVALID_STATUS"):
        ledger.set_status(conn, "i1", "BOGUS", now=NOW)


# --- T25: capital policy conflict (report only, never auto-adjust) ---------
def test_t25_capital_policy_conflict():
    capital = Decimal("100")
    legacy_min = Decimal("50")
    result = ledger.capital_policy_conflict(capital, legacy_min_position=legacy_min)
    assert result["conflict"] is True
    assert result["code"] == "CAPITAL_POLICY_CONFLICT"
    assert result["core_cap"] == "42.5"
    assert result["legacy_min"] == "50"
    # inputs must not be mutated
    assert capital == Decimal("100")
    assert legacy_min == Decimal("50")


def test_capital_policy_conflict_none_when_cap_sufficient():
    result = ledger.capital_policy_conflict(Decimal("200"),
                                            legacy_min_position=Decimal("50"))
    assert result["conflict"] is False
    assert result["code"] is None
    assert result["core_cap"] == "85"


# --- migrate guard ----------------------------------------------------------
def test_migrate_inside_transaction_raises(tmp_path):
    c = store.open_store(tmp_path / "rh.db")
    try:
        c.execute("BEGIN")
        try:
            with pytest.raises(RuntimeError, match="MIGRATE_INSIDE_TRANSACTION"):
                ledger.migrate_checked(c)
        finally:
            c.execute("ROLLBACK")
    finally:
        c.close()


def test_try_reserve_works_inside_an_open_transaction(tmp_path):
    """The runner calls try_reserve mid-episode, with rows already written.

    open_store leaves sqlite3 in implicit-transaction mode, so the first
    insert_row opens a transaction and a later BEGIN IMMEDIATE raises
    "cannot start a transaction within a transaction". This never fired before
    2026-09-10: the terminal gate rejects every step outside New York RTH, so
    try_reserve was only ever reached on a clean connection. The first RTH
    window would have crashed the whole episode.
    """
    from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store
    from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID, try_reserve

    conn = open_store(tmp_path / "txn.db")
    migrate(conn)
    insert_row(conn, "rh_gate_decisions", {
        "decision_id": "d1", "candidate_key": "c1", "target_mode": "SHADOW",
        "primary_status": "COMPUTED_FAIL", "terminal_bits_json": "{}",
        "decided_at": "2026-09-10T14:00:00Z",
    })
    assert conn.in_transaction, "fixture premise: a transaction is open"

    res = try_reserve(conn, intent_id="i1", bucket="CORE",
                      amount_usd=Decimal("10"), capital_usd=Decimal("10000"),
                      policy_version=POLICY_ID, now="2026-10-10T14:00:00Z")
    assert res["granted"] is True

    # The caller's transaction survives: its earlier row is still pending, and
    # committing it persists both.
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0] == 1
    conn.close()


def test_try_reserve_denial_inside_transaction_keeps_caller_rows(tmp_path):
    """A denied reservation must roll back only itself, not the caller's work."""
    from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store
    from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID, try_reserve

    conn = open_store(tmp_path / "txn2.db")
    migrate(conn)
    insert_row(conn, "rh_gate_decisions", {
        "decision_id": "d1", "candidate_key": "c1", "target_mode": "SHADOW",
        "primary_status": "COMPUTED_FAIL", "terminal_bits_json": "{}",
        "decided_at": "2026-09-10T14:00:00Z",
    })
    # Far beyond the CORE active cap, so this is denied.
    res = try_reserve(conn, intent_id="i1", bucket="CORE",
                      amount_usd=Decimal("999999"), capital_usd=Decimal("10000"),
                      policy_version=POLICY_ID, now="2026-10-10T14:00:00Z")
    assert res["granted"] is False
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0] == 0
    conn.close()
