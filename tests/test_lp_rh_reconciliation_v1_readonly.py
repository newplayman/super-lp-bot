"""Tests for lp_rh_reconciliation_v1.py (RH-RECON-V1).

Ensures fail-close behavior: empty tables or lack of evidence must never produce PASS.
Checks C1 double-entry balance, C2 shadow opening legs, and C3 fee accruals.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import pytest

from scripts.lp_rh_store_v1_readonly import migrate, open_store, insert_row, _UTC_RE
from scripts.lp_rh_reconciliation_v1 import (
    run_reconciliation,
    check_c1_double_entry_balance,
    check_c2_opening_legs,
    check_c3_fee_accrual,
)


@pytest.fixture
def test_db(tmp_path):
    """Create an isolated test database with full schema initialized via migrate()."""
    db_file = tmp_path / "test_scanner.db"
    conn = open_store(db_file, read_only=False)
    migrate(conn)
    conn.commit()
    yield conn
    conn.close()


def _populate_balanced_dataset(conn: sqlite3.Connection, *, position_id="pos-test-1"):
    """Populate standard balanced dataset for C1, C2, and C3."""
    now_str = "2026-09-11T10:00:00.000000Z"
    # C2 Shadow position
    insert_row(conn, "rh_shadow_positions", {
        "strategy_episode": "ep-1",
        "position_id": position_id,
        "pool_key": "pool-1",
        "profile": "narrow",
        "bucket": "bucket-1",
        "initial_token0_raw": "100.5",
        "initial_token1_raw": "200.25",
        "tick_lower": -100,
        "tick_upper": 100,
        "virtual_liquidity_raw": "1000000",
        "opened_at": now_str,
        "closed_at": None,
    })
    # C2 Journal entries (token0 and token1 opening legs)
    insert_row(conn, "rh_journal", {
        "event_id": f"{position_id}-open-t0",
        "idempotency_key": f"{position_id}-open-t0",
        "account_debit": "LP_POSITION_TOKEN0",
        "account_credit": "WALLET_TOKEN0",
        "asset": "0xtoken0",
        "amount_raw": "100.5",
        "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": position_id, "leg": "token0"}),
        "booked_at": now_str,
    })
    insert_row(conn, "rh_journal", {
        "event_id": f"{position_id}-open-t1",
        "idempotency_key": f"{position_id}-open-t1",
        "account_debit": "LP_POSITION_TOKEN1",
        "account_credit": "WALLET_TOKEN1",
        "asset": "0xtoken1",
        "amount_raw": "200.25",
        "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": position_id, "leg": "token1"}),
        "booked_at": now_str,
    })
    # C3 Fee journal entry
    insert_row(conn, "rh_journal", {
        "event_id": f"{position_id}-fee",
        "idempotency_key": f"{position_id}-fee",
        "account_debit": "LP_FEES_RECEIVABLE",
        "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1",
        "amount_raw": "15.75",
        "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": position_id, "kind": "fee"}),
        "booked_at": now_str,
    })
    # C3 Position mark
    insert_row(conn, "rh_position_marks", {
        "position_id": position_id,
        "mark_time": now_str,
        "price_snapshot_id": "snap-1",
        "reference_nav": "316.5",
        "liquidation_nav": None,
        "accrued_fee": "15.75",
        "unvalued_risk_json": "{}",
        "derived_block_hash": None,
        "derived_block_number": None,
    })
    conn.commit()


def test_reconciliation_all_pass(test_db):
    """1. All three checks have evidence and balance -> PASS."""
    _populate_balanced_dataset(test_db)
    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "PASS"
    assert res["delta"] == {}
    assert res["evidence"]["c1"]["has_evidence"] is True
    assert res["evidence"]["c2"]["has_evidence"] is True
    assert res["evidence"]["c3"]["has_evidence"] is True


def test_reconciliation_empty_journal_insufficient(test_db):
    """2. rh_journal empty -> INSUFFICIENT_EVIDENCE (never PASS)."""
    now_str = "2026-09-11T10:00:00.000000Z"
    insert_row(test_db, "rh_shadow_positions", {
        "strategy_episode": "ep-1",
        "position_id": "pos-1",
        "pool_key": "p-1",
        "profile": "narrow",
        "bucket": "b-1",
        "initial_token0_raw": "100",
        "initial_token1_raw": "200",
        "opened_at": now_str,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": "pos-1",
        "mark_time": now_str,
        "accrued_fee": "10",
    })
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert res["evidence"]["c1"]["has_evidence"] is False
    assert res["evidence"]["c1"]["reason"] == "NO_JOURNAL_EVIDENCE"
    reasons = [item["reason"] for item in res["delta"]["insufficient_evidence"]]
    assert any("NO_JOURNAL_EVIDENCE" in r for r in reasons)


def test_reconciliation_empty_shadow_positions_insufficient(test_db):
    """3. rh_shadow_positions empty -> INSUFFICIENT_EVIDENCE."""
    now_str = "2026-09-11T10:00:00.000000Z"
    insert_row(test_db, "rh_journal", {
        "event_id": "ev-1",
        "idempotency_key": "ev-1",
        "account_debit": "LP_FEES_RECEIVABLE",
        "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1",
        "amount_raw": "10",
        "is_external_flow": 0,
        "booked_at": now_str,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": "pos-1",
        "mark_time": now_str,
        "accrued_fee": "10",
    })
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert res["evidence"]["c2"]["has_evidence"] is False
    assert res["evidence"]["c2"]["reason"] == "NO_SHADOW_POSITIONS_EVIDENCE"
    reasons = [item["reason"] for item in res["delta"]["insufficient_evidence"]]
    assert "NO_SHADOW_POSITIONS_EVIDENCE" in reasons


def test_reconciliation_c3_fee_missing_in_journal_unexplained(test_db):
    """4. No fee entry in journal but position marks have accrued_fee -> UNEXPLAINED_DIFF."""
    _populate_balanced_dataset(test_db)
    # Remove fee journal entry
    test_db.execute("DELETE FROM rh_journal WHERE account_debit = 'LP_FEES_RECEIVABLE'")
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    assert res["evidence"]["c3"]["has_evidence"] is True
    assert res["evidence"]["c3"]["diff_count"] == 1
    assert res["evidence"]["c3"]["reason"] == "FEE_ACCRUAL_DIFF"
    assert "c3_diffs" in res["delta"]
    assert res["delta"]["c3_diffs"]["fee_journal_total"] == "0"
    assert Decimal(res["delta"]["c3_diffs"]["marks_fee_total"]) > 0


def test_reconciliation_c3_no_fees_anywhere_insufficient(test_db):
    """5. No fee journal entry and accrued_fee is 0/NULL -> C3 lacks sample -> INSUFFICIENT_EVIDENCE."""
    _populate_balanced_dataset(test_db)
    # Delete fee journal entry and set mark accrued_fee to NULL
    test_db.execute("DELETE FROM rh_journal WHERE account_debit = 'LP_FEES_RECEIVABLE'")
    test_db.execute("UPDATE rh_position_marks SET accrued_fee = NULL")
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert res["evidence"]["c3"]["has_evidence"] is False
    assert "NO_FEE_EVIDENCE" in res["evidence"]["c3"]["reason"]
    reasons = [item["reason"] for item in res["delta"]["insufficient_evidence"]]
    assert any("NO_FEE_EVIDENCE" in r for r in reasons)


def test_reconciliation_c2_amount_mismatch_unexplained(test_db):
    """6. C2 journal amount is 1 less than position initial_token0_raw -> UNEXPLAINED_DIFF with position_id."""
    _populate_balanced_dataset(test_db, position_id="pos-mismatch-99")
    # Intentionally alter token0 amount in journal to be 1 less
    test_db.execute("UPDATE rh_journal SET amount_raw = '99.5' WHERE event_id = 'pos-mismatch-99-open-t0'")
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    assert res["evidence"]["c2"]["has_evidence"] is True
    assert res["evidence"]["c2"]["diff_count"] == 1
    assert res["evidence"]["c2"]["reason"] == "OPENING_LEGS_DIFF"
    assert "c2_diffs" in res["delta"]
    c2_diff = res["delta"]["c2_diffs"][0]
    assert c2_diff["position_id"] == "pos-mismatch-99"
    assert Decimal(c2_diff["token0"]["diff"]) == Decimal("-1.0")


def test_reconciliation_dry_run_no_write(test_db):
    """7. Dry-run default does not write to rh_reconciliation_runs."""
    _populate_balanced_dataset(test_db)
    res = run_reconciliation(test_db, apply=False)
    assert res["applied"] is False

    count = test_db.execute("SELECT COUNT(*) FROM rh_reconciliation_runs").fetchone()[0]
    assert count == 0


def test_reconciliation_apply_writes_valid_record(test_db):
    """8. --apply writes 1 row per run, run_id unique, timestamps UTC RFC3339 ending with Z."""
    _populate_balanced_dataset(test_db)
    res1 = run_reconciliation(test_db, apply=True)
    res2 = run_reconciliation(test_db, apply=True)

    rows = test_db.execute(
        "SELECT run_id, started_at, finished_at, evidence_json, delta_json, verdict "
        "FROM rh_reconciliation_runs ORDER BY started_at ASC"
    ).fetchall()

    assert len(rows) == 2
    run_ids = [r[0] for r in rows]
    assert run_ids[0] != run_ids[1]
    assert res1["run_id"] == run_ids[0]
    assert res2["run_id"] == run_ids[1]

    for run_id, started_at, finished_at, ev_json, dl_json, verdict in rows:
        assert _UTC_RE.match(started_at)
        assert started_at.endswith("Z")
        assert _UTC_RE.match(finished_at)
        assert finished_at.endswith("Z")
        assert verdict == "PASS"
        ev = json.loads(ev_json)
        dl = json.loads(dl_json)
        assert "c1" in ev and "c2" in ev and "c3" in ev
        assert isinstance(dl, dict)


def test_evidence_json_has_rows_examined(test_db):
    """9. evidence_json records rows_examined for every check."""
    _populate_balanced_dataset(test_db)
    res = run_reconciliation(test_db, apply=True)

    row = test_db.execute("SELECT evidence_json FROM rh_reconciliation_runs LIMIT 1").fetchone()
    assert row is not None
    ev = json.loads(row[0])

    for key in ("c1", "c2", "c3"):
        assert key in ev, f"Missing check key {key} in evidence_json"
        assert "rows_examined" in ev[key], f"Missing rows_examined in {key}"
        assert isinstance(ev[key]["rows_examined"], int)
        assert ev[key]["rows_examined"] > 0


def test_reconciliation_c1_unbalanced_unexplained(test_db):
    """10. C1 double-entry imbalance yields UNEXPLAINED_DIFF."""
    _populate_balanced_dataset(test_db)
    now_str = "2026-09-11T10:00:00.000000Z"
    # Insert an entry with an empty credit account
    insert_row(test_db, "rh_journal", {
        "event_id": "unbalanced-entry-1",
        "idempotency_key": "unbalanced-entry-1",
        "account_debit": "LP_POSITION_TOKEN0",
        "account_credit": "",
        "asset": "0xtoken0",
        "amount_raw": "50",
        "is_external_flow": 0,
        "booked_at": now_str,
    })
    test_db.commit()

    res = run_reconciliation(test_db, apply=False)
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    assert res["evidence"]["c1"]["has_evidence"] is True
    assert res["evidence"]["c1"]["diff_count"] > 0
    assert res["evidence"]["c1"]["reason"] == "UNBALANCED_ENTRIES"
    assert "c1_diffs" in res["delta"]
