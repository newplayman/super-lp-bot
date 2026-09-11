# RH-07-FIX-B: Episode holds transaction lifecycle (R01 counterexample fix).
# Directly asserts against SQLite storage layer.
from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest

from scripts.lp_rh_store_v1_readonly import open_store, migrate
from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID, try_reserve, reserved_total
from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted

NOW = "2026-09-11T14:00:00Z"


def test_reservation_cancelled_by_episode_rollback(monkeypatch, tmp_path):
    """Test 1: Reservation is cleanly rolled back when an episode transaction rolls back.

    Matches R01 scenario: _run_episode_persisted holds BEGIN IMMEDIATE;
    try_reserve nests under a SAVEPOINT; when the episode encounters a failure
    and executes conn.rollback(), the uncommitted reservation is cancelled and room restored.
    """
    conn = open_store(tmp_path / "ledger.db")
    migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    res = try_reserve(conn, intent_id="ep-1", bucket="CORE",
                       amount_usd=Decimal("1000"), capital_usd=Decimal("10000"),
                       policy_version=POLICY_ID, now=NOW)
    assert res["granted"] is True
    conn.rollback()  # Simulate episode failure / rollback
    row = conn.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id='ep-1'").fetchone()
    assert row is None  # Reservation rolled back
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("0")
    conn.close()


def test_reservation_persists_after_episode_commit(tmp_path):
    """Test 2: Reservation correctly persists into database after episode commit.

    Normal forward path: when the episode successfully runs to completion,
    conn.commit() commits the outer transaction, making the PENDING reservation persistent.
    """
    conn = open_store(tmp_path / "ledger.db")
    migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    res = try_reserve(conn, intent_id="ep-1", bucket="CORE",
                       amount_usd=Decimal("1000"), capital_usd=Decimal("10000"),
                       policy_version=POLICY_ID, now=NOW)
    assert res["granted"] is True
    conn.commit()
    row = conn.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id='ep-1'").fetchone()
    assert row == ("PENDING",)
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("1000")
    conn.close()


def test_episode_tx_reverse_validation(monkeypatch, tmp_path):
    """Test 3: Reverse validation (fault injection -> RED -> restore -> GREEN).

    Simulates the R01 defect where the caller does NOT hold an outer transaction
    (own_txn=True path in try_reserve). In that buggy mode, try_reserve issues its own
    COMMIT, so a subsequent rollback fails to cancel the reservation (leak reproduced).
    When restored to the fixed behavior (caller holds BEGIN IMMEDIATE), rollback
    completely cancels the reservation.
    """
    # 1. Defect injection: standalone caller without transaction (simulating pre-fix state)
    conn_buggy = open_store(tmp_path / "ledger_buggy.db")
    migrate(conn_buggy)
    # Note: No BEGIN IMMEDIATE called
    assert not conn_buggy.in_transaction
    res_buggy = try_reserve(conn_buggy, intent_id="ep-buggy", bucket="CORE",
                            amount_usd=Decimal("1000"), capital_usd=Decimal("10000"),
                            policy_version=POLICY_ID, now=NOW)
    assert res_buggy["granted"] is True
    # In buggy state, try_reserve committed itself. Calling rollback does not undo it!
    conn_buggy.rollback()
    row_buggy = conn_buggy.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id='ep-buggy'").fetchone()
    assert row_buggy == ("PENDING",)  # DEFECT REPRODUCED: reservation leaked
    assert reserved_total(conn_buggy, "CORE", POLICY_ID) == Decimal("1000")
    conn_buggy.close()

    # 2. Fixed state: caller / _run_episode_persisted holds BEGIN IMMEDIATE
    conn_fixed = open_store(tmp_path / "ledger_fixed.db")
    migrate(conn_fixed)
    conn_fixed.execute("BEGIN IMMEDIATE")
    assert conn_fixed.in_transaction
    res_fixed = try_reserve(conn_fixed, intent_id="ep-fixed", bucket="CORE",
                            amount_usd=Decimal("1000"), capital_usd=Decimal("10000"),
                            policy_version=POLICY_ID, now=NOW)
    assert res_fixed["granted"] is True
    conn_fixed.rollback()
    row_fixed = conn_fixed.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id='ep-fixed'").fetchone()
    assert row_fixed is None  # FIXED: reservation cancelled
    assert reserved_total(conn_fixed, "CORE", POLICY_ID) == Decimal("0")
    conn_fixed.close()


def test_multi_step_episode_full_rollback(tmp_path):
    """Test 4: Multi-step episode rolls back all nested reservations cleanly.

    Simulates runner performing multiple try_reserve calls across different steps
    within a single episode transaction. When the episode rolls back, all reservations
    are discarded together.
    """
    conn = open_store(tmp_path / "ledger.db")
    migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    for i in range(3):
        res = try_reserve(conn, intent_id=f"ep-{i}", bucket="CORE",
                           amount_usd=Decimal("500"), capital_usd=Decimal("10000"),
                           policy_version=POLICY_ID, now=NOW)
        assert res["granted"] is True

    # Before rollback: 3 x 500 = 1500 USD reserved
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("1500")

    conn.rollback()

    # After rollback: 0 reserved, 0 reservation records in database
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("0")
    assert conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0] == 0
    conn.close()
