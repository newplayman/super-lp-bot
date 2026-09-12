import sqlite3
import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    audit_unexplained_ledger_diffs,
    select_graduation_reconciliation_evidence,
)
from scripts.lp_rh_store_v1_readonly import open_store, migrate


def test_audit_unexplained_ledger_diffs_checks_latest_run_only(tmp_path):
    """R2-05: Verify old failed reconciliation runs do not poison current audit if latest runs pass."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_journal (event_id TEXT, account_debit TEXT, account_credit TEXT, amount_raw TEXT)")
    conn.execute("""
        CREATE TABLE rh_reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            verdict TEXT,
            diff_count INTEGER
        )
    """)

    # Journal is balanced
    conn.execute("INSERT INTO rh_journal VALUES (?, ?, ?, ?)",
                 ("ev-1", "WETH", "USDC", "1000"))
    conn.execute("INSERT INTO rh_journal VALUES (?, ?, ?, ?)",
                 ("ev-2", "USDC", "WETH", "1000"))

    # An old reconciliation run failed long ago
    conn.execute("INSERT INTO rh_reconciliation_runs VALUES (?, ?, ?, ?)",
                 ("run-old-fail", "2026-08-01T00:00:00Z", "FAIL", 5))

    # The 5 most recent runs all passed
    for i in range(1, 6):
        conn.execute("INSERT INTO rh_reconciliation_runs VALUES (?, ?, ?, ?)",
                     (f"run-pass-{i}", f"2026-09-11T{10+i:02d}:00:00Z", "PASS", 0))

    audit = audit_unexplained_ledger_diffs(conn)
    assert audit["count"] == 0
    assert audit["reason"] == "OK"

    conn.close()


def test_select_graduation_reconciliation_evidence_filters(tmp_path):
    """R2-05: Verify select_graduation_reconciliation_evidence bounds evidence by profile and window."""
    db_file = tmp_path / "recon.db"
    conn = open_store(db_file)
    migrate(conn)

    # Insert runs with verdict PASS and FAIL
    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict
        ) VALUES (?, ?, ?, ?)
    """, (
        "run-pass-1", "2026-09-11T12:05:00Z", "2026-09-11T12:06:00Z", "PASS"
    ))

    # All runs passed in window
    evidence = select_graduation_reconciliation_evidence(conn, window_start="2026-09-11T12:00:00Z")
    assert evidence["runs_examined"] == 1
    assert evidence["reconciliation_blocker"] is None

    # Filtered by window_start after run-pass-1
    evidence_after = select_graduation_reconciliation_evidence(
        conn, window_start="2026-09-11T13:00:00Z"
    )
    assert evidence_after["runs_examined"] == 0
    assert evidence_after["reconciliation_blocker"] == "RECONCILIATION_EVIDENCE_MISSING"

    # Insert a newer failing run
    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict
        ) VALUES (?, ?, ?, ?)
    """, (
        "run-fail-2", "2026-09-11T12:10:00Z", "2026-09-11T12:11:00Z", "FAIL"
    ))

    evidence_fail = select_graduation_reconciliation_evidence(conn, window_start="2026-09-11T12:00:00Z")
    assert evidence_fail["runs_examined"] == 2
    assert evidence_fail["reconciliation_blocker"] == "RECONCILIATION_FAIL"

    conn.close()
