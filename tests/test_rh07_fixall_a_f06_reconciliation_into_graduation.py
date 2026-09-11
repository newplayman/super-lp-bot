from __future__ import annotations

import sqlite3
from decimal import Decimal
import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    audit_unexplained_ledger_diffs,
    stage_b_status,
)


def test_reconciliation_failure_detected_as_diff():
    """F06: audit_unexplained_ledger_diffs must check rh_reconciliation_runs and flag non-PASS runs."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rh_journal (event_id TEXT, account_debit TEXT, account_credit TEXT, amount_raw TEXT)"
    )
    conn.execute(
        "INSERT INTO rh_journal VALUES ('ev1', 'DEBIT_ACCT', 'CREDIT_ACCT', '100')"
    )
    conn.execute("CREATE TABLE rh_reconciliation_runs (status TEXT)")
    conn.execute("INSERT INTO rh_reconciliation_runs VALUES ('UNEXPLAINED_DIFF')")

    res = audit_unexplained_ledger_diffs(conn)
    assert res["count"] == 1
    assert "rh_reconciliation_runs:status=UNEXPLAINED_DIFF" in res["details"]
    assert res["reason"] == "UNBALANCED_ENTRIES"
    conn.close()


def test_reconciliation_pass_allows_clean_audit():
    """F06: audit_unexplained_ledger_diffs passes when all reconciliation runs are PASS."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rh_journal (event_id TEXT, account_debit TEXT, account_credit TEXT, amount_raw TEXT)"
    )
    conn.execute(
        "INSERT INTO rh_journal VALUES ('ev1', 'DEBIT_ACCT', 'CREDIT_ACCT', '100')"
    )
    conn.execute("CREATE TABLE rh_reconciliation_runs (verdict TEXT)")
    conn.execute("INSERT INTO rh_reconciliation_runs VALUES ('PASS')")

    res = audit_unexplained_ledger_diffs(conn)
    assert res["count"] == 0
    assert res["reason"] == "OK"
    conn.close()


def test_reconciliation_blocker_propagates_to_stage_b():
    """F06: Reconciliation blocker attaches to stage_b_status and fails the gate."""
    res = stage_b_status(
        days_covered=14,
        weekends_covered=1,
        unexplained_ledger_diffs=0,
        invariant_violations=0,
        missed_risk_events=0,
        profile_locked=True,
        code_version_locked=True,
        policy_version_locked=True,
        capital_policy_version_locked=True,
        full_cost_profitable_episodes=10,
        oos_episode_ratio=Decimal("0.30"),
        exit_stress_passed=True,
        netcover_passed=True,
        reconciliation_blocker="RECONCILIATION_UNEXPLAINED_DIFF",
    )
    assert res["passed"] is False
    assert "RECONCILIATION_UNEXPLAINED_DIFF" in res["blockers"]


def test_reconciliation_reverse_validation_defect_simulation():
    """Reverse validation: Old code ignored rh_reconciliation_runs entirely, yielding 0 diffs."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rh_journal (event_id TEXT, account_debit TEXT, account_credit TEXT, amount_raw TEXT)"
    )
    conn.execute(
        "INSERT INTO rh_journal VALUES ('ev1', 'DEBIT_ACCT', 'CREDIT_ACCT', '100')"
    )
    conn.execute("CREATE TABLE rh_reconciliation_runs (verdict TEXT)")
    conn.execute("INSERT INTO rh_reconciliation_runs VALUES ('FAIL_MISMATCH')")

    # Defective logic: only inspects rh_journal balance
    def defective_audit_diffs(db_conn):
        rows = db_conn.execute("SELECT account_debit, account_credit, amount_raw FROM rh_journal").fetchall()
        # Journal itself is balanced (100 debit == 100 credit)
        return {"count": 0}

    defect_res = defective_audit_diffs(conn)
    assert defect_res["count"] == 0  # Defect falsely reports 0 diffs!

    # Fixed code:
    fixed_res = audit_unexplained_ledger_diffs(conn)
    assert fixed_res["count"] == 1  # Correctly identifies failed reconciliation run
    conn.close()
