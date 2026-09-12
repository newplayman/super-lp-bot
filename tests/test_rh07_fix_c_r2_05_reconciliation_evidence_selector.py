"""R2-05 + R3 / Package G2+G3: reconciliation evidence selector binds
profile/code_version/policy_version; missing columns / mismatched
versions do NOT silently pass.

Re-audit 04e8a45 / 6fda329 confirmed:
  * ``select_graduation_reconciliation_evidence`` added ``WHERE profile
    = ?`` only when the column existed in the live schema; when it
    didn't, the filter was silently dropped.
  * Real schema (rh_reconciliation_runs in lp_rh_store_v1_readonly.py)
    did NOT have profile / code_version / policy_version columns.
  * The 6fda329 caller passed only ``profile="CORE"``; even after schema
    migration, code_version and policy_version filters were never
    invoked at all.

R3 fixes:
  * Schema gains the three columns (DEFAULT 'UNKNOWN', NOT NULL).
  * Selector fails close (``SCHEMA_BINDING_MISSING``) when the
    caller asks for any binding whose column is missing.
  * Selector applies ``WHERE profile/code_version/policy_version = ?``
    unconditionally when the caller supplies those values.
  * Caller in ``_build_state`` always passes current code_version +
    policy_version.
"""

import sqlite3

import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    audit_unexplained_ledger_diffs,
    select_graduation_reconciliation_evidence,
)
from scripts.lp_rh_store_v1_readonly import open_store, migrate


def test_audit_unexplained_ledger_diffs_checks_latest_run_only(tmp_path):
    """R2-05: Old failed reconciliation runs do not poison current audit if latest runs pass."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rh_journal (event_id TEXT, account_debit TEXT, account_credit TEXT, amount_raw TEXT)"
    )
    conn.execute("""
        CREATE TABLE rh_reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            verdict TEXT,
            diff_count INTEGER
        )
    """)

    conn.execute("INSERT INTO rh_journal VALUES (?, ?, ?, ?)",
                 ("ev-1", "WETH", "USDC", "1000"))
    conn.execute("INSERT INTO rh_journal VALUES (?, ?, ?, ?)",
                 ("ev-2", "USDC", "WETH", "1000"))

    conn.execute("INSERT INTO rh_reconciliation_runs VALUES (?, ?, ?, ?)",
                 ("run-old-fail", "2026-08-01T00:00:00Z", "FAIL", 5))

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

    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict,
            profile, code_version, policy_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "run-pass-1", "2026-09-11T12:05:00Z", "2026-09-11T12:06:00Z",
        "PASS", "CORE", "current", "current",
    ))

    evidence = select_graduation_reconciliation_evidence(
        conn, profile="CORE", code_version="current", policy_version="current",
        window_start="2026-09-11T12:00:00Z",
    )
    assert evidence["runs_examined"] == 1
    assert evidence["reconciliation_blocker"] is None

    evidence_after = select_graduation_reconciliation_evidence(
        conn, profile="CORE", code_version="current", policy_version="current",
        window_start="2026-09-11T13:00:00Z",
    )
    assert evidence_after["runs_examined"] == 0
    assert evidence_after["reconciliation_blocker"] == "RECONCILIATION_EVIDENCE_MISSING"

    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict,
            profile, code_version, policy_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "run-fail-2", "2026-09-11T12:10:00Z", "2026-09-11T12:11:00Z",
        "FAIL", "CORE", "current", "current",
    ))

    evidence_fail = select_graduation_reconciliation_evidence(
        conn, profile="CORE", code_version="current", policy_version="current",
        window_start="2026-09-11T12:00:00Z",
    )
    assert evidence_fail["runs_examined"] == 2
    assert evidence_fail["reconciliation_blocker"] == "RECONCILIATION_FAIL"
    conn.close()


def test_old_code_version_run_does_not_satisfy_new_code_version(tmp_path):
    """R3 / Package G: a PASS run written under code_version='old' must
    NOT satisfy a selector asking for code_version='new'.  The 6fda329
    code dropped the code_version filter silently because the column
    did not exist; once the column exists, mismatched versions must
    short-circuit to RECONCILIATION_EVIDENCE_MISSING.
    """
    db_file = tmp_path / "version.db"
    conn = open_store(db_file)
    migrate(conn)

    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict,
            profile, code_version, policy_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "run-old", "2026-09-11T12:05:00Z", "2026-09-11T12:06:00Z",
        "PASS", "CORE", "old-version", "rh_50_30_20_proposed_v1",
    ))

    evidence = select_graduation_reconciliation_evidence(
        conn, profile="CORE",
        code_version="new-version",
        policy_version="rh_50_30_20_proposed_v1",
        window_start="2026-09-11T12:00:00Z",
    )
    assert evidence["runs_examined"] == 0, (
        "an old code_version PASS run must not satisfy a new-version selector"
    )
    assert evidence["reconciliation_blocker"] == "RECONCILIATION_EVIDENCE_MISSING"
    conn.close()


def test_old_policy_version_run_does_not_satisfy_new_policy(tmp_path):
    """R3 / Package G: same binding for policy_version."""
    db_file = tmp_path / "policy.db"
    conn = open_store(db_file)
    migrate(conn)

    conn.execute("""
        INSERT INTO rh_reconciliation_runs (
            run_id, started_at, finished_at, verdict,
            profile, code_version, policy_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "run-old-policy", "2026-09-11T12:05:00Z", "2026-09-11T12:06:00Z",
        "PASS", "CORE", "any-version", "old-policy-v0",
    ))

    evidence = select_graduation_reconciliation_evidence(
        conn, profile="CORE",
        code_version="any-version",
        policy_version="new-policy-v1",
        window_start="2026-09-11T12:00:00Z",
    )
    assert evidence["runs_examined"] == 0
    assert evidence["reconciliation_blocker"] == "RECONCILIATION_EVIDENCE_MISSING"
    conn.close()


def test_schema_binding_missing_fails_close(tmp_path):
    """R3 / Package G2: when the live schema lacks a binding column the
    caller asks for, the selector returns SCHEMA_BINDING_MISSING.  This
    is the regression 6fda329 missed — the old code silently dropped
    the filter, so an old PASS run could re-promote into a new
    graduation window whose selector was meant to require the new
    binding.
    """
    conn = sqlite3.connect(":memory:")
    # Build a rh_reconciliation_runs WITHOUT the binding columns.
    conn.execute("""
        CREATE TABLE rh_reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            verdict TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO rh_reconciliation_runs VALUES (?, ?, ?, ?)",
        ("run-x", "2026-09-11T12:00:00Z", "2026-09-11T12:01:00Z", "PASS"),
    )

    # When the caller asks for ``profile``, the column is missing —
    # the selector must fail close.
    evidence = select_graduation_reconciliation_evidence(
        conn, profile="CORE",
    )
    assert evidence["status"] == "SCHEMA_BINDING_MISSING"
    assert evidence["missing_column"] == "profile"
    assert "RECONCILIATION_SCHEMA_BINDING_MISSING:profile" in evidence["reconciliation_blocker"]

    evidence_code = select_graduation_reconciliation_evidence(
        conn, profile=None, code_version="abc123",
    )
    assert evidence_code["status"] == "SCHEMA_BINDING_MISSING"
    assert evidence_code["missing_column"] == "code_version"

    evidence_policy = select_graduation_reconciliation_evidence(
        conn, profile=None, code_version=None,
        policy_version="rh_50_30_20_proposed_v1",
    )
    assert evidence_policy["status"] == "SCHEMA_BINDING_MISSING"
    assert evidence_policy["missing_column"] == "policy_version"
    conn.close()


def test_real_schema_carries_binding_columns(tmp_path):
    """R3 / Package G1: ``migrate()`` must leave rh_reconciliation_runs
    with profile / code_version / policy_version columns, including
    after a fresh DB creation."""
    db_file = tmp_path / "fresh.db"
    conn = open_store(db_file)
    migrate(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(rh_reconciliation_runs)").fetchall()}
    assert "profile" in cols
    assert "code_version" in cols
    assert "policy_version" in cols

    # Insert without explicit binding values; the schema DEFAULT 'UNKNOWN'
    # must apply.
    conn.execute("""
        INSERT INTO rh_reconciliation_runs (run_id, started_at, verdict)
        VALUES (?, ?, ?)
    """, ("run-default", "2026-09-11T12:00:00Z", "PASS"))
    row = conn.execute(
        "SELECT profile, code_version, policy_version FROM rh_reconciliation_runs WHERE run_id = ?",
        ("run-default",),
    ).fetchone()
    assert row == ("UNKNOWN", "UNKNOWN", "UNKNOWN")
    conn.close()


def test_existing_db_gets_binding_columns_via_migration(tmp_path):
    """R3 / Package G1: a DB created under the OLD schema (no binding
    columns) gains them via ``migrate()`` running _ensure_columns.  This
    is the additive migration path."""
    db_file = tmp_path / "legacy.db"
    conn = open_store(db_file)
    # Create the table WITHOUT the binding columns.
    conn.execute("""
        CREATE TABLE rh_reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            evidence_json TEXT,
            delta_json TEXT,
            verdict TEXT NOT NULL,
            derived_block_hash TEXT,
            derived_block_number INTEGER
        )
    """)
    conn.commit()

    migrate(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(rh_reconciliation_runs)").fetchall()}
    assert "profile" in cols
    assert "code_version" in cols
    assert "policy_version" in cols
    conn.close()
