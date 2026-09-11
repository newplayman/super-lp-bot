"""Tests for scripts/lp_rh_coverage_report_v1_readonly.py (RH-02 deliverable audit).

Covers all 7 mandatory requirements:
1. Window with gap -> coverage < 100%, denominator is planned window not actual row count.
2. Deleting gap rows -> coverage still < 100% (proves no cheating by trimming bad window).
3. Empty database -> UNKNOWN / NOT_MEASURED with reasons, never 0, 100%, or OK.
4. Field non-null rate: all-NULL field reports 0%, does not affect other fields.
5. Missing classification: unclassifiable gap -> counted in UNCLASSIFIED.
6. Missing provider_health.db -> budget_status is UNKNOWN with reason, not OK.
7. Both reports generated and are valid Markdown / JSON.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import pytest

from scripts.lp_rh_coverage_report_v1_readonly import (
    analyze_planned_window,
    audit_key_fields,
    audit_rpc_budget,
    audit_2026_09_07,
    classify_gap,
    run_coverage_audit,
    MISSING_CALENDAR_HOLIDAY,
    MISSING_PRICE_MISSING,
    MISSING_RPC_FAILURE,
    MISSING_UNCLASSIFIED,
)


def _create_mock_scanner_db(db_path: Path, rows=()) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE rh_market_states (
            asset_address TEXT,
            sample_time TEXT PRIMARY KEY,
            chain_id INTEGER,
            session TEXT,
            reference_mid TEXT,
            fee_growth_global_0 TEXT,
            fee_growth_global_1 TEXT,
            source_event_time TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE rh_rpc_health (
            provider TEXT,
            method TEXT,
            sample_time TEXT,
            latency_ms INTEGER,
            error TEXT,
            state TEXT
        )
    """)
    for r in rows:
        conn.execute(
            "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?, ?)", r
        )
    conn.commit()
    conn.close()


def _create_mock_provider_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE rh_provider_capability (
            sample_time TEXT,
            provider TEXT,
            capability TEXT,
            ok INTEGER,
            latency_ms INTEGER,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE rh_provider_rollup (
            sample_time TEXT,
            usable_count INTEGER,
            usable_providers_json TEXT,
            live_gate_status TEXT
        )
    """)
    conn.execute(
        "INSERT INTO rh_provider_capability VALUES ('2026-09-08T12:00:00Z', 'ordofi', 'get_block', 1, 50, NULL)"
    )
    conn.execute(
        "INSERT INTO rh_provider_capability VALUES ('2026-09-08T12:00:15Z', 'ordofi', 'get_block', 1, 45, NULL)"
    )
    conn.execute(
        "INSERT INTO rh_provider_rollup VALUES ('2026-09-08T12:00:00Z', 1, '[\"ordofi\"]', 'OK')"
    )
    conn.commit()
    conn.close()


def test_coverage_with_gap_denominator_is_planned_window():
    """1. 窗口内有缺口 -> 覆盖率 < 100%，且分母是计划窗口而非实际行数。"""
    # 40 planned intervals over 600s (interval = 15s)
    # Timestamps: 0, 15, 30, ..., 150 (11 samples), then GAP from 150 to 300 (misses 9 samples), then 300 to 600 (21 samples)
    # Total actual = 11 + 21 = 32 samples.
    # Expected samples = 600 / 15 = 40.
    sample_times = []
    base_t = 1757325600  # 2026-09-08T10:00:00Z
    for sec in range(0, 165, 15):
        dt = datetime.fromtimestamp(base_t + sec, tz=timezone.utc)
        sample_times.append(dt.isoformat().replace("+00:00", "Z"))
    for sec in range(300, 615, 15):
        dt = datetime.fromtimestamp(base_t + sec, tz=timezone.utc)
        sample_times.append(dt.isoformat().replace("+00:00", "Z"))

    res = analyze_planned_window(sample_times, expected_interval_secs=15)
    assert res["status"] == "OK"
    assert res["span_secs"] == 600.0
    # Denominator MUST be planned window (40), NOT actual count (32)
    assert res["expected_samples"] == 40
    assert res["actual_samples"] == 32
    assert res["coverage_ratio"] == Decimal("32") / Decimal("40")
    assert res["coverage_ratio"] < Decimal("1.0")
    assert len(res["gaps"]) == 1
    assert res["gaps"][0]["missed_samples"] == 10


def test_deleted_gap_still_yields_sub_100_coverage():
    """2. 把缺口那段整段删掉 -> 覆盖率仍然 < 100% (证明没有「删坏窗口刷满分」)。"""
    # Suppose evaluation window is planned from t=0 to t=600.
    # Even if bad data inside the window is completely deleted / omitted from DB,
    # the planned window remains 40 samples, and coverage remains < 100%.
    w_start = "2026-09-08T10:00:00Z"
    w_end = "2026-09-08T10:10:00Z"
    # Only 10 samples exist in this 600s window because bad data was dropped
    sample_times = [
        "2026-09-08T10:00:00Z",
        "2026-09-08T10:00:15Z",
        "2026-09-08T10:00:30Z",
        "2026-09-08T10:09:45Z",
        "2026-09-08T10:10:00Z",
    ]
    res = analyze_planned_window(
        sample_times,
        expected_interval_secs=15,
        window_start=w_start,
        window_end=w_end,
    )
    assert res["expected_samples"] == 40
    assert res["actual_samples"] == 5
    assert res["coverage_ratio"] == Decimal("5") / Decimal("40")
    assert res["coverage_ratio"] < Decimal("1.0")


def test_empty_database_fail_closed_unknown_or_not_measured(tmp_path):
    """3. 空库 -> 每项都是 UNKNOWN / NOT_MEASURED 加原因，不是 0 也不是 100%。"""
    empty_db = tmp_path / "empty_scanner.db"
    conn = sqlite3.connect(empty_db)
    conn.execute("CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT)")
    conn.commit()
    conn.close()

    # Window analysis on empty
    w_res = analyze_planned_window([], expected_interval_secs=15)
    assert w_res["status"] == "NOT_MEASURED"
    assert w_res["coverage_ratio"] is None
    assert w_res["reason"] == "EMPTY_DATABASE_OR_INVALID_WINDOW"

    # Key fields on empty
    c_ro = sqlite3.connect(f"file:{empty_db}?mode=ro", uri=True)
    f_res = audit_key_fields(c_ro, total_samples=0)
    for field, item in f_res.items():
        assert item["status"] == "NOT_MEASURED"
        assert item["ratio"] is None
        assert item["reason"] in ("EMPTY_DATABASE", f"COLUMN_NOT_IN_SCHEMA: '{field}' not in rh_market_states")
    c_ro.close()

    # Budget on non-existent provider db
    b_res = audit_rpc_budget(tmp_path / "missing_p.db", empty_db)
    assert b_res["budget_status"] == "UNKNOWN"
    assert "PROVIDER_DB_NOT_FOUND" in b_res["budget_status_reason"]
    assert b_res["budget_status"] != "OK"


def test_field_non_null_all_null_reports_zero_pct(tmp_path):
    """4. 字段非空率: 某字段全 NULL -> 该字段报 0%，不影响其他字段。"""
    db_path = tmp_path / "test_fields.db"
    rows = [
        ("0x1", "2026-09-08T10:00:00Z", 1, "RTH", "100.5", "1000", None, "2026-09-08T09:59:59Z"),
        ("0x1", "2026-09-08T10:00:15Z", 1, "RTH", "100.6", "1010", None, "2026-09-08T10:00:14Z"),
    ]
    _create_mock_scanner_db(db_path, rows)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    f_res = audit_key_fields(conn, total_samples=len(rows))
    conn.close()

    # fee_growth_global_0 is 100% (2 / 2)
    assert f_res["fee_growth_global_0"]["status"] == "OK"
    assert f_res["fee_growth_global_0"]["ratio"] == Decimal("1.0")

    # fee_growth_global_1 is all NULL -> 0.0%
    assert f_res["fee_growth_global_1"]["status"] == "OK"
    assert f_res["fee_growth_global_1"]["ratio"] == Decimal("0.0")
    assert f_res["fee_growth_global_1"]["non_null_count"] == 0
    assert f_res["fee_growth_global_1"]["denominator"] == 2

    # Missing column in table reports NOT_MEASURED without breaking others
    assert f_res["sqrt_price_x96"]["status"] == "NOT_MEASURED"
    assert "COLUMN_NOT_IN_SCHEMA" in f_res["sqrt_price_x96"]["reason"]


def test_missing_classification_unclassified():
    """5. 缺失分类: 造一条分类不出来的 -> 计入 UNCLASSIFIED。"""
    # A weekday gap during regular trading with no RPC errors and no price missing
    gap = {
        "start": "2026-09-08T14:00:00Z",  # Tuesday RTH
        "end": "2026-09-08T14:05:00Z",
        "duration_secs": 300,
        "missed_samples": 20,
    }
    # No matching RPC errors
    rpc_rows = [{
        "provider": "ordofi",
        "sample_time": "2026-09-08T14:01:00Z",
        "latency_ms": 50,
        "error": None,
        "state": "NORMAL",
    }]
    # Normal market states
    market_rows = [{
        "sample_time": "2026-09-08T14:00:00Z",
        "reference_mid": "100.0",
        "session": "RTH",
    }]
    cat = classify_gap(gap, rpc_rows, market_rows)
    assert cat == MISSING_UNCLASSIFIED


def test_missing_provider_db_yields_unknown_budget_status(tmp_path):
    """6. provider_health.db 不存在 -> budget_status 为 UNKNOWN 加 reason，不是 OK。"""
    missing_p = tmp_path / "non_existent_provider_health.db"
    scanner_p = tmp_path / "dummy_scanner.db"
    _create_mock_scanner_db(scanner_p)

    res = audit_rpc_budget(missing_p, scanner_p)
    assert res["budget_status"] == "UNKNOWN"
    assert "PROVIDER_DB_NOT_FOUND" in res["budget_status_reason"]
    assert res["budget_status"] != "OK"


def test_generate_reports_valid_markdown_and_json(tmp_path):
    """7. 两份报告都能生成且是合法 Markdown / JSON。"""
    s_db = tmp_path / "scanner.db"
    p_db = tmp_path / "provider_health.db"
    rows = [
        ("0x1", "2026-09-08T10:00:00Z", 1, "RTH", "100.5", "1000", "2000", "2026-09-08T09:59:59Z"),
        ("0x1", "2026-09-08T10:00:15Z", 1, "RTH", "100.6", "1010", "2010", "2026-09-08T10:00:14Z"),
    ]
    _create_mock_scanner_db(s_db, rows)
    _create_mock_provider_db(p_db)

    out_dir = tmp_path / "reports_out"
    md_file, json_file = run_coverage_audit(
        scanner_db_path=s_db,
        provider_db_path=p_db,
        out_dir=out_dir,
        interval_secs=15,
    )
    assert md_file.exists()
    assert json_file.exists()

    md_text = md_file.read_text(encoding="utf-8")
    assert "# DATA_COVERAGE_REPORT" in md_text
    assert "覆盖率分母口径说明" in md_text
    assert "fee_growth_global_0" in md_text
    assert "UNCLASSIFIED" in md_text

    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert "providers" in json_data
    assert "ordofi" in json_data["providers"]
    assert json_data["budget_status"] == "UNKNOWN"
    assert "budget_status_reason" in json_data


def test_2026_09_07_holiday_audit_behavior(tmp_path):
    """8. 2026-09-07 劳动节休市样本识别审计。"""
    db_path = tmp_path / "holiday_scanner.db"
    rows = [
        ("0x1", "2026-09-07T14:30:00Z", 1, "HOLIDAY", "100.5", "1000", "2000", "2026-09-07T14:29:59Z"),
        ("0x1", "2026-09-07T14:30:15Z", 1, "HOLIDAY", "100.6", "1010", "2010", "2026-09-07T14:30:14Z"),
    ]
    _create_mock_scanner_db(db_path, rows)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    res = audit_2026_09_07(conn)
    conn.close()

    assert res["status"] == "OK"
    assert res["calendar_rule_verified"] is True
    assert res["samples_found"] == 2
    assert res["holiday_samples"] == 2
    assert res["non_holiday_samples"] == 0
