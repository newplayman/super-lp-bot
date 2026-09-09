#!/usr/bin/env python3
"""Tests for the RH-02r column health sentinel (offline, in-memory SQLite)."""
import sqlite3
import sys

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts.lp_rh_column_health_v1_readonly import (  # noqa: E402
    classify_column,
    column_stats,
    format_report,
    main,
    scan_database,
)

# rh_a: 3 rows covering every classification shape at once.
#   all_null: NULL in all 3 rows        -> EMPTY
#   constant: 'UNKNOWN' in all 3 rows   -> CONSTANT (the session defect)
#   varied:   three distinct values     -> POPULATED
#   partial:  one NULL, two values      -> POPULATED (never EMPTY)
# rh_empty: 0 rows                      -> every column NO_ROWS
# rh_single: 1 row, one valued col, one NULL col
# other_x: must never appear under the default 'rh_' prefix
TEST_SCHEMA = """
CREATE TABLE rh_a (all_null TEXT, constant TEXT, varied TEXT, partial TEXT);
INSERT INTO rh_a VALUES (NULL, 'UNKNOWN', 'v1', 'p1');
INSERT INTO rh_a VALUES (NULL, 'UNKNOWN', 'v2', NULL);
INSERT INTO rh_a VALUES (NULL, 'UNKNOWN', 'v3', 'p3');
CREATE TABLE rh_empty (x TEXT, y TEXT);
CREATE TABLE rh_single (valued TEXT, nullish TEXT);
INSERT INTO rh_single VALUES ('abc', NULL);
CREATE TABLE other_x (z TEXT);
INSERT INTO other_x VALUES ('w');
"""


def make_db():
    """In-memory SQLite connection with the standard test tables."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(TEST_SCHEMA)
    return conn


def stat(column, null_count, distinct_count, sample=None):
    return {"column": column, "null_count": null_count,
            "distinct_count": distinct_count, "sample": sample}


def test_all_null_column_is_empty():
    # 3 rows, column entirely NULL -> EMPTY
    assert classify_column(stat("c", 3, 0), total_rows=3) == "EMPTY"


def test_constant_column():
    # no NULLs, one distinct value (session always "UNKNOWN") -> CONSTANT
    assert classify_column(stat("session", 0, 1, "UNKNOWN"),
                           total_rows=3) == "CONSTANT"


def test_varied_column_is_populated():
    assert classify_column(stat("c", 0, 3), total_rows=3) == "POPULATED"


def test_partial_null_column_is_populated_not_empty():
    # 1 NULL out of 3 -> POPULATED, never EMPTY
    assert classify_column(stat("c", 1, 2), total_rows=3) == "POPULATED"


def test_zero_rows_is_no_rows_without_zero_division():
    # empty table: every column NO_ROWS, no ZeroDivisionError, and the
    # NO_ROWS columns must not leak into the EMPTY summary
    conn = make_db()
    scan = scan_database(conn, prefix="rh_")
    empty = scan["tables"]["rh_empty"]
    assert empty["total_rows"] == 0
    for s in empty["columns"]:
        assert classify_column(s, total_rows=0) == "NO_ROWS"
    assert "rh_empty.x" not in scan["summary"]["empty_columns"]
    assert "rh_empty.y" not in scan["summary"]["empty_columns"]


def test_single_row_table_classification():
    conn = make_db()
    scan = scan_database(conn, prefix="rh_")
    single = scan["tables"]["rh_single"]
    assert single["total_rows"] == 1
    labels = {s["column"]: classify_column(s, total_rows=1)
              for s in single["columns"]}
    assert labels["valued"] == "CONSTANT"
    assert labels["nullish"] == "EMPTY"


def test_scan_only_prefix_tables():
    conn = make_db()
    scan = scan_database(conn, prefix="rh_")
    assert "other_x" not in scan["tables"]
    assert set(scan["tables"]) == {"rh_a", "rh_empty", "rh_single"}


def test_scan_empty_prefix_scans_all():
    conn = make_db()
    scan = scan_database(conn, prefix="")
    assert "other_x" in scan["tables"]
    assert "rh_a" in scan["tables"]


def test_summary_empty_columns_sorted_dotted():
    conn = make_db()
    scan = scan_database(conn, prefix="rh_")
    empties = scan["summary"]["empty_columns"]
    assert "rh_a.all_null" in empties
    assert "rh_single.nullish" in empties
    assert empties == sorted(empties)
    for item in empties:
        assert "." in item


def test_summary_constant_columns_sorted_dotted():
    conn = make_db()
    scan = scan_database(conn, prefix="rh_")
    constants = scan["summary"]["constant_columns"]
    assert "rh_a.constant" in constants
    assert "rh_single.valued" in constants
    assert constants == sorted(constants)
    for item in constants:
        assert "." in item


def test_summary_lists_empty_not_none_when_clean():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_clean (a TEXT, b TEXT)")
    conn.executemany("INSERT INTO rh_clean VALUES (?, ?)",
                     [("x", "1"), ("y", "2"), ("z", "3")])
    scan = scan_database(conn, prefix="rh_")
    assert scan["summary"]["empty_columns"] == []
    assert scan["summary"]["constant_columns"] == []


def test_sample_first_non_null_and_none_when_all_null():
    conn = make_db()
    stats = {s["column"]: s for s in column_stats(conn, "rh_a")}
    assert stats["partial"]["sample"] == "p1"  # first non-NULL value
    assert stats["all_null"]["sample"] is None


def test_sample_truncated_to_60_chars():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE rh_long (v TEXT)")
    conn.execute("INSERT INTO rh_long VALUES (?)", ("x" * 100,))
    stats = column_stats(conn, "rh_long")
    assert len(stats[0]["sample"]) == 60
    assert stats[0]["sample"] == "x" * 60


def test_scan_is_read_only():
    # full-table snapshot before and after: row counts and content unchanged
    conn = make_db()
    names = ("rh_a", "rh_empty", "rh_single", "other_x")
    snapshot = {
        name: conn.execute(
            f"SELECT * FROM {name} ORDER BY rowid").fetchall()
        for name in names
    }
    scan_database(conn, prefix="")
    for name in names:
        assert conn.execute(
            f"SELECT * FROM {name} ORDER BY rowid").fetchall() == snapshot[name]


def _write_db(tmp_path, name="scanner.db"):
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.executescript(TEST_SCHEMA)
    conn.commit()
    conn.close()
    return path


def test_main_without_fail_on_empty_returns_zero(tmp_path):
    path = _write_db(tmp_path)
    assert main(["--db", str(path), "--prefix", "rh_"]) == 0


def test_main_fail_on_empty_with_empty_columns_returns_one(tmp_path):
    path = _write_db(tmp_path)
    assert main(["--db", str(path), "--prefix", "rh_",
                 "--fail-on-empty"]) == 1


def test_main_fail_on_empty_without_empty_columns_returns_zero(tmp_path):
    path = tmp_path / "clean.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE rh_clean (a TEXT, b TEXT)")
    conn.executemany("INSERT INTO rh_clean VALUES (?, ?)",
                     [("x", "1"), ("y", "2"), ("z", "3")])
    conn.commit()
    conn.close()
    assert main(["--db", str(path), "--prefix", "rh_",
                 "--fail-on-empty"]) == 0


def test_format_report_marks_classifications():
    conn = make_db()
    report = format_report(scan_database(conn, prefix="rh_"))
    assert "rh_a (total_rows=3)" in report
    assert "EMPTY" in report
    assert "CONSTANT" in report
    assert "POPULATED" in report
    assert "NO_ROWS" in report
    assert "rh_a.all_null" in report
