from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from scripts.lp_rh_readiness_v1_readonly import (
    audit_key_field_health,
)


def test_unified_window_denominator_no_shrinking():
    """F07: The evaluation denominator must be unified across all columns.
    A late-added column with only 1 populated sample out of 1000 rows must fail with ratio=1/1000.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE rh_market_states (
            asset_address TEXT,
            sample_time TEXT,
            reference_mid TEXT,
            session TEXT,
            fee_growth_global_0 TEXT,
            fee_growth_global_1 TEXT
        )
    """)
    asset = "0xpool"
    start = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    rows = []
    n = 1000
    for i in range(n):
        ts = (start + timedelta(seconds=15 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fg = "100" if i == n - 1 else None
        rows.append((asset, ts, "2500.0", "REGULAR", fg, fg))
    conn.executemany("INSERT INTO rh_market_states VALUES (?,?,?,?,?,?)", rows)

    res = audit_key_field_health(conn, asset_address=asset)
    assert res["passed"] is False

    fg0 = res["columns"]["fee_growth_global_0"]
    assert fg0["passed"] is False
    assert fg0["window_rows"] == 1000  # Unified denominator! Not shrunk to 1!
    assert fg0["non_null_count"] == 1
    assert fg0["non_null_ratio"] == Decimal("1") / Decimal("1000")
    assert fg0["first_populated_at"] is not None
    conn.close()


def test_unified_window_all_columns_passing():
    """F07: All columns pass when populated >= 99% within the unified evaluation window."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE rh_market_states (
            asset_address TEXT,
            sample_time TEXT,
            reference_mid TEXT,
            session TEXT,
            fee_growth_global_0 TEXT,
            fee_growth_global_1 TEXT
        )
    """)
    asset = "0xpool"
    start = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    rows = []
    n = 100
    for i in range(n):
        ts = (start + timedelta(seconds=15 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((asset, ts, "2500.0", "REGULAR", "100", "200"))
    conn.executemany("INSERT INTO rh_market_states VALUES (?,?,?,?,?,?)", rows)

    res = audit_key_field_health(conn, asset_address=asset)
    assert res["passed"] is True
    for col_name, col_data in res["columns"].items():
        assert col_data["window_rows"] == 100
        assert col_data["passed"] is True
        assert col_data["non_null_ratio"] == Decimal("1")
    conn.close()


def test_unified_window_reverse_validation_defect_simulation():
    """Reverse validation: RH-02bj shrunk the denominator to only post-first_populated rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE rh_market_states (
            asset_address TEXT,
            sample_time TEXT,
            reference_mid TEXT,
            session TEXT,
            fee_growth_global_0 TEXT,
            fee_growth_global_1 TEXT
        )
    """)
    asset = "0xpool"
    start = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    rows = []
    n = 1000
    for i in range(n):
        ts = (start + timedelta(seconds=15 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fg = "100" if i == n - 1 else None
        rows.append((asset, ts, "2500.0", "REGULAR", fg, fg))
    conn.executemany("INSERT INTO rh_market_states VALUES (?,?,?,?,?,?)", rows)

    # Defect simulation: Shrink window to start from first_populated_time
    def defective_key_field_calc(db_conn, col):
        first_time = db_conn.execute(f"SELECT MIN(sample_time) FROM rh_market_states WHERE {col} IS NOT NULL").fetchone()[0]
        # In defect, window is rows >= first_time
        w_rows = db_conn.execute(f"SELECT COUNT(*) FROM rh_market_states WHERE sample_time >= ?", (first_time,)).fetchone()[0]
        pop_count = db_conn.execute(f"SELECT COUNT({col}) FROM rh_market_states WHERE sample_time >= ?", (first_time,)).fetchone()[0]
        ratio = pop_count / w_rows
        return {"window_rows": w_rows, "ratio": ratio, "passed": ratio >= 0.99}

    defect_res = defective_key_field_calc(conn, "fee_growth_global_0")
    # Defect: 1 row post-first_time, 1 populated -> 100% ratio! False pass!
    assert defect_res["window_rows"] == 1
    assert defect_res["ratio"] == 1.0
    assert defect_res["passed"] is True

    # Fixed implementation: unified denominator across table/window
    fixed_res = audit_key_field_health(conn, asset_address=asset)
    fg0 = fixed_res["columns"]["fee_growth_global_0"]
    assert fg0["window_rows"] == 1000
    assert fg0["passed"] is False
    conn.close()
