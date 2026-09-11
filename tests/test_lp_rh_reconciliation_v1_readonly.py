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
    main,
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


DEFAULT_TEST_POOL_META = {
    "dec1": 6,
    "quote_usd_per_token1": {
        "value": "1.0",
        "source": "coingecko:global-dollar",
        "observed_at": "2026-09-11T10:00:00.000000Z",
        "ttl_secs": 86400,
    },
}


@pytest.fixture(autouse=True)
def _mock_default_pool_meta(monkeypatch):
    """Ensure tests use DEFAULT_TEST_POOL_META by default rather than host production file."""
    monkeypatch.setattr(
        "scripts.lp_rh_reconciliation_v1.DEFAULT_POOL_META_PATH",
        DEFAULT_TEST_POOL_META,
    )


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
    # C3 Fee journal entry (raw token units: 15.75 * 10^6 / 1.0 = 15750000)
    insert_row(conn, "rh_journal", {
        "event_id": f"{position_id}-fee",
        "idempotency_key": f"{position_id}-fee",
        "account_debit": "LP_FEES_RECEIVABLE",
        "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1",
        "amount_raw": "15750000",
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


def test_reconciliation_no_since_regression(test_db):
    """11. No --since parameter: identical behavior to baseline regression."""
    _populate_balanced_dataset(test_db)
    res = run_reconciliation(test_db, since=None)
    assert res["verdict"] == "PASS"
    assert res["since"] is None
    for k in ("c1", "c2", "c3"):
        assert res["evidence"][k]["has_evidence"] is True
        assert res["evidence"][k]["since"] is None
        assert res["evidence"][k]["rows_examined"] > 0
    assert res["delta"] == {}


def test_reconciliation_since_after_all_data_insufficient(test_db):
    """12. --since after all data: all 3 checks have no samples -> INSUFFICIENT_EVIDENCE (never PASS)."""
    _populate_balanced_dataset(test_db)
    future_since = "2026-09-11T12:00:00Z"
    res = run_reconciliation(test_db, since=future_since)

    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert res["since"] == future_since
    for k in ("c1", "c2", "c3"):
        check_ev = res["evidence"][k]
        assert check_ev["has_evidence"] is False
        assert check_ev["since"] == future_since
        assert check_ev["rows_examined"] == 0
    assert "insufficient_evidence" in res["delta"]
    assert len(res["delta"]["insufficient_evidence"]) == 3


def test_reconciliation_since_excludes_historical_diff_pass(test_db):
    """13. --since excludes historical diff and balances in window -> PASS, rows_examined reflects window count."""
    t_old = "2026-09-11T08:00:00.000000Z"
    insert_row(test_db, "rh_shadow_positions", {
        "strategy_episode": "ep-old", "position_id": "pos-old", "pool_key": "pool-1",
        "profile": "narrow", "bucket": "b-1", "initial_token0_raw": "10", "initial_token1_raw": "20",
        "tick_lower": -10, "tick_upper": 10, "virtual_liquidity_raw": "1000", "opened_at": t_old,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-old-open-t0", "idempotency_key": "pos-old-open-t0",
        "account_debit": "LP_POSITION_TOKEN0", "account_credit": "WALLET_TOKEN0",
        "asset": "0xtoken0", "amount_raw": "10", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-old", "leg": "token0"}), "booked_at": t_old,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-old-open-t1", "idempotency_key": "pos-old-open-t1",
        "account_debit": "LP_POSITION_TOKEN1", "account_credit": "WALLET_TOKEN1",
        "asset": "0xtoken1", "amount_raw": "20", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-old", "leg": "token1"}), "booked_at": t_old,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": "pos-old", "mark_time": t_old, "accrued_fee": "50.0",
    })

    t_new = "2026-09-11T11:00:00.000000Z"
    insert_row(test_db, "rh_shadow_positions", {
        "strategy_episode": "ep-new", "position_id": "pos-new", "pool_key": "pool-1",
        "profile": "narrow", "bucket": "b-1", "initial_token0_raw": "15", "initial_token1_raw": "25",
        "tick_lower": -10, "tick_upper": 10, "virtual_liquidity_raw": "1000", "opened_at": t_new,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-new-open-t0", "idempotency_key": "pos-new-open-t0",
        "account_debit": "LP_POSITION_TOKEN0", "account_credit": "WALLET_TOKEN0",
        "asset": "0xtoken0", "amount_raw": "15", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-new", "leg": "token0"}), "booked_at": t_new,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-new-open-t1", "idempotency_key": "pos-new-open-t1",
        "account_debit": "LP_POSITION_TOKEN1", "account_credit": "WALLET_TOKEN1",
        "asset": "0xtoken1", "amount_raw": "25", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-new", "leg": "token1"}), "booked_at": t_new,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-new-fee", "idempotency_key": "pos-new-fee",
        "account_debit": "LP_FEES_RECEIVABLE", "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1", "amount_raw": "12500000", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-new", "kind": "fee"}), "booked_at": t_new,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": "pos-new", "mark_time": t_new, "accrued_fee": "12.5",
    })
    test_db.commit()

    res = run_reconciliation(test_db, since="2026-09-11T10:00:00Z")
    assert res["verdict"] == "PASS"
    assert res["evidence"]["c1"]["rows_examined"] == 3
    assert res["evidence"]["c1"]["diff_count"] == 0
    assert res["evidence"]["c2"]["rows_examined"] == 1
    assert res["evidence"]["c2"]["diff_count"] == 0
    assert res["evidence"]["c3"]["rows_examined"] == 1
    assert res["evidence"]["c3"]["positions_examined"] == 1
    assert res["evidence"]["c3"]["fee_journal_rows_examined"] == 1
    assert res["evidence"]["c3"]["diff_count"] == 0


def test_reconciliation_since_includes_historical_diff_unexplained(test_db):
    """14. --since window includes historical diff -> UNEXPLAINED_DIFF."""
    t_old = "2026-09-11T08:00:00.000000Z"
    insert_row(test_db, "rh_shadow_positions", {
        "strategy_episode": "ep-old", "position_id": "pos-old", "pool_key": "pool-1",
        "profile": "narrow", "bucket": "b-1", "initial_token0_raw": "10", "initial_token1_raw": "20",
        "tick_lower": -10, "tick_upper": 10, "virtual_liquidity_raw": "1000", "opened_at": t_old,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-old-open-t0", "idempotency_key": "pos-old-open-t0",
        "account_debit": "LP_POSITION_TOKEN0", "account_credit": "WALLET_TOKEN0",
        "asset": "0xtoken0", "amount_raw": "10", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-old", "leg": "token0"}), "booked_at": t_old,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": "pos-old-open-t1", "idempotency_key": "pos-old-open-t1",
        "account_debit": "LP_POSITION_TOKEN1", "account_credit": "WALLET_TOKEN1",
        "asset": "0xtoken1", "amount_raw": "20", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": "pos-old", "leg": "token1"}), "booked_at": t_old,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": "pos-old", "mark_time": t_old, "accrued_fee": "50.0",
    })
    test_db.commit()

    res = run_reconciliation(test_db, since="2026-09-11T07:00:00Z")
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    assert res["evidence"]["c3"]["diff_count"] == 1
    assert "c3_diffs" in res["delta"]


def test_reconciliation_since_invalid_format(tmp_path, capsys):
    """15. --since invalid format (no tz, not a date, empty) -> non-zero exit and stderr error."""
    db_file = tmp_path / "recon_inv.db"
    conn = open_store(db_file, read_only=False)
    migrate(conn)
    conn.close()

    for invalid_ts in ("2026-09-11", "not-a-date", "2026-09-11T10:52:54", ""):
        conn_mem = open_store(db_file, read_only=True)
        with pytest.raises(ValueError, match="Invalid RFC3339 timestamp"):
            run_reconciliation(conn_mem, since=invalid_ts)
        conn_mem.close()

        rc = main(["--db", str(db_file), "--since", invalid_ts])
        assert rc != 0
        captured = capsys.readouterr()
        assert "invalid --since timestamp" in captured.err


def test_evidence_json_has_since_field(test_db):
    """16. evidence_json has since field in all 3 checks (null when omitted)."""
    _populate_balanced_dataset(test_db)

    # 1. Without since: since is null
    res1 = run_reconciliation(test_db, apply=True, since=None)
    row1 = test_db.execute(
        "SELECT evidence_json FROM rh_reconciliation_runs WHERE run_id = ?",
        (res1["run_id"],)
    ).fetchone()
    assert row1 is not None
    ev1 = json.loads(row1[0])
    for k in ("c1", "c2", "c3"):
        assert "since" in ev1[k]
        assert ev1[k]["since"] is None

    # 2. With since: since is recorded
    since_val = "2026-09-11T09:00:00Z"
    res2 = run_reconciliation(test_db, apply=True, since=since_val)
    row2 = test_db.execute(
        "SELECT evidence_json FROM rh_reconciliation_runs WHERE run_id = ?",
        (res2["run_id"],)
    ).fetchone()
    assert row2 is not None
    ev2 = json.loads(row2[0])
    for k in ("c1", "c2", "c3"):
        assert "since" in ev2[k]
        assert ev2[k]["since"] == since_val


# =====================================================================
# RH-02cy: C3 Fee Accrual Unit Conversion and Fail-Close Tests (>= 6)
# =====================================================================

def test_c3_matching_conversion_pass(test_db):
    """1. Journal records raw, marks records USD, match after conversion -> C3 PASS, diff_count=0."""
    now_str = "2026-09-11T13:30:00.000000Z"
    pos_id = "pos-prod-match"
    # Exact production numbers from clean window
    insert_row(test_db, "rh_shadow_positions", {
        "strategy_episode": "ep-prod", "position_id": pos_id, "pool_key": "pool-1",
        "profile": "narrow", "bucket": "b-1", "initial_token0_raw": "100", "initial_token1_raw": "200",
        "tick_lower": -10, "tick_upper": 10, "virtual_liquidity_raw": "1000", "opened_at": now_str,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": f"{pos_id}-t0", "idempotency_key": f"{pos_id}-t0",
        "account_debit": "LP_POSITION_TOKEN0", "account_credit": "WALLET_TOKEN0",
        "asset": "0xtoken0", "amount_raw": "100", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": pos_id, "leg": "token0"}), "booked_at": now_str,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": f"{pos_id}-t1", "idempotency_key": f"{pos_id}-t1",
        "account_debit": "LP_POSITION_TOKEN1", "account_credit": "WALLET_TOKEN1",
        "asset": "0xtoken1", "amount_raw": "200", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": pos_id, "leg": "token1"}), "booked_at": now_str,
    })
    insert_row(test_db, "rh_journal", {
        "event_id": f"{pos_id}-fee", "idempotency_key": f"{pos_id}-fee",
        "account_debit": "LP_FEES_RECEIVABLE", "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1", "amount_raw": "105678.5414471455946505877164", "is_external_flow": 0,
        "ref_json": json.dumps({"position_id": pos_id, "kind": "fee"}), "booked_at": now_str,
    })
    insert_row(test_db, "rh_position_marks", {
        "position_id": pos_id, "mark_time": now_str, "price_snapshot_id": "snap-1",
        "reference_nav": "300.0", "liquidation_nav": None,
        "accrued_fee": "0.1056746313411120502635856447", "unvalued_risk_json": "{}",
    })
    test_db.commit()

    pool_meta = {
        "dec1": 6,
        "quote_usd_per_token1": {
            "value": "0.999963",
            "source": "coingecko:global-dollar",
            "observed_at": "2026-09-11T13:41:35Z",
            "ttl_secs": 86400,
        }
    }
    res = run_reconciliation(test_db, pool_meta=pool_meta, since="2026-09-11T13:29:00Z")
    assert res["verdict"] == "PASS"
    c3 = res["evidence"]["c3"]
    assert c3["has_evidence"] is True
    assert c3["diff_count"] == 0
    assert c3["reason"] == "OK"
    assert Decimal(c3["details"]["diff"]) <= Decimal("1e-18")


def test_c3_mismatch_unexplained_diff(test_db):
    """2. Mismatch after conversion (journal underreports by 1%) -> UNEXPLAINED_DIFF."""
    _populate_balanced_dataset(test_db, position_id="pos-mismatch")
    # Under-report journal fee by 1% (15750000 * 0.99 = 15592500)
    test_db.execute(
        "UPDATE rh_journal SET amount_raw = '15592500' WHERE account_debit = 'LP_FEES_RECEIVABLE'"
    )
    test_db.commit()

    res = run_reconciliation(test_db)
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    c3 = res["evidence"]["c3"]
    assert c3["has_evidence"] is True
    assert c3["diff_count"] == 1
    assert c3["reason"] == "FEE_ACCRUAL_DIFF"
    assert "c3_diffs" in res["delta"]
    assert Decimal(res["delta"]["c3_diffs"]["diff"]) < 0


def test_c3_missing_dec1_insufficient(test_db):
    """3. pool_meta missing dec1 -> C3 INSUFFICIENT_EVIDENCE (never assume dec1=6)."""
    _populate_balanced_dataset(test_db, position_id="pos-nodec1")
    meta_no_dec1 = {
        "quote_usd_per_token1": {
            "value": "1.0",
            "source": "test",
            "observed_at": "2026-09-11T10:00:00Z",
            "ttl_secs": 86400,
        }
    }
    res = run_reconciliation(test_db, pool_meta=meta_no_dec1)
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    c3 = res["evidence"]["c3"]
    assert c3["has_evidence"] is False
    assert c3["diff_count"] is None
    assert "DEC1" in c3["reason"]


def test_c3_missing_quote_insufficient(test_db):
    """4. pool_meta missing quote -> C3 INSUFFICIENT_EVIDENCE (never assume quote=1.0)."""
    _populate_balanced_dataset(test_db, position_id="pos-noquote")
    meta_no_quote = {
        "dec1": 6,
    }
    res = run_reconciliation(test_db, pool_meta=meta_no_quote)
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    c3 = res["evidence"]["c3"]
    assert c3["has_evidence"] is False
    assert c3["diff_count"] is None
    assert "QUOTE" in c3["reason"]


def test_c3_expired_quote_insufficient(test_db):
    """5. quote past TTL -> C3 INSUFFICIENT_EVIDENCE."""
    _populate_balanced_dataset(test_db, position_id="pos-expired")
    meta_expired = {
        "dec1": 6,
        "quote_usd_per_token1": {
            "value": "1.0",
            "source": "test",
            "observed_at": "2026-09-10T10:00:00Z",
            "ttl_secs": 3600,  # 1 hour TTL
        }
    }
    # Run evaluation at 2026-09-11T10:00:00Z (24h later)
    res = run_reconciliation(
        test_db,
        pool_meta=meta_expired,
        now_fn=lambda: "2026-09-11T10:00:00.000000Z",
    )
    assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
    c3 = res["evidence"]["c3"]
    assert c3["has_evidence"] is False
    assert c3["diff_count"] is None
    assert "QUOTE_EVIDENCE_EXPIRED" in c3["reason"]


def test_c3_evidence_json_records_quote_dec1_tolerance(test_db):
    """6. evidence_json records actual quote, dec1, and tolerance values."""
    _populate_balanced_dataset(test_db, position_id="pos-audit")
    res = run_reconciliation(test_db, apply=True)
    row = test_db.execute(
        "SELECT evidence_json FROM rh_reconciliation_runs WHERE run_id = ?",
        (res["run_id"],),
    ).fetchone()
    assert row is not None
    ev = json.loads(row[0])
    c3 = ev["c3"]
    assert c3["quote"] == "1.0"
    assert c3["dec1"] == 6
    assert Decimal(c3["tolerance"]) == Decimal("1e-18")
    assert c3["details"]["quote"] == "1.0"
    assert c3["details"]["dec1"] == 6
    assert Decimal(c3["details"]["tolerance"]) == Decimal("1e-18")


def test_c3_regression_c1_c2_unaffected(test_db):
    """7. Regression protection: C1 and C2 results remain identical to before."""
    _populate_balanced_dataset(test_db, position_id="pos-regr")
    # Break C1: insert unbalanced journal entry with empty credit
    insert_row(test_db, "rh_journal", {
        "event_id": "c1-imbalance", "idempotency_key": "c1-imbalance",
        "account_debit": "LP_POSITION_TOKEN0", "account_credit": "",
        "asset": "0xtoken0", "amount_raw": "999.0", "is_external_flow": 0,
        "ref_json": "{}", "booked_at": "2026-09-11T10:00:00.000000Z",
    })
    test_db.commit()

    res = run_reconciliation(test_db)
    assert res["verdict"] == "UNEXPLAINED_DIFF"
    assert res["evidence"]["c1"]["diff_count"] > 0
    assert res["evidence"]["c1"]["reason"] == "UNBALANCED_ENTRIES"
    assert "c1_diffs" in res["delta"]


def test_c3_pool_meta_file_path_and_unreadable(tmp_path, test_db):
    """8. pool_meta loaded from valid json file passes; missing file yields INSUFFICIENT_EVIDENCE."""
    _populate_balanced_dataset(test_db, position_id="pos-file")
    valid_file = tmp_path / "pool_meta_valid.json"
    valid_file.write_text(json.dumps(DEFAULT_TEST_POOL_META))

    res_ok = run_reconciliation(test_db, pool_meta=valid_file)
    assert res_ok["verdict"] == "PASS"

    non_existent = tmp_path / "does_not_exist.json"
    res_err = run_reconciliation(test_db, pool_meta=non_existent)
    assert res_err["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "POOL_META_READ_ERROR" in res_err["evidence"]["c3"]["reason"]


