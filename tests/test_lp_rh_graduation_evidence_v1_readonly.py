#!/usr/bin/env python3
"""test_lp_rh_graduation_evidence_v1_readonly.py — RH-02cf 验收测试套件

测试 scripts/lp_rh_graduation_evidence_v1.py 毕业收尾证据与交付物生成器。
测试必须在 tmp_path 中构造数据库与产出目录，绝不污染 reports/。
禁止在测试中真正执行全量 pytest（使用 mock 或 --skip-tests）。
"""
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import (
    DEFAULT_DB_PATH as PROD_DB_PATH,
    insert_row,
    migrate,
    open_store,
)
from scripts.lp_rh_graduation_evidence_v1 import (
    build_verdict,
    generate_graduation_evidence,
    main,
    parse_fault_injection_report,
    parse_pytest_summary,
)

CORE_ASSET = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"


def _init_test_db(db_path: Path) -> None:
    """Create a minimal valid RH sqlite database for readiness audit."""
    conn = open_store(db_path, read_only=False)
    migrate(conn)
    # Insert a minimal sample to satisfy schema queries
    insert_row(
        conn,
        "rh_market_states",
        {
            "asset_address": CORE_ASSET,
            "sample_time": "2026-09-10T10:00:00Z",
            "chain_id": 4663,
            "session": "RTH",
            "health_flags_json": "[]",
            "reference_mid": "2400",
            "fee_growth_global_0": "1000",
            "fee_growth_global_1": "1000",
        },
    )
    conn.commit()
    conn.close()


def test_skip_tests_generates_dashboard_and_verdict_without_log(tmp_path: Path):
    """1. --skip-tests 时：dashboard 与 verdict 生成，FULL_TEST_RAW.log 不生成，
    verdict 里 full_test 为 null。"""
    db_path = tmp_path / "scanner.db"
    out_dir = tmp_path / "out"
    _init_test_db(db_path)

    exit_code, verdict = generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=True,
    )

    assert exit_code == 0
    assert (out_dir / "READINESS_DASHBOARD.md").is_file()
    assert (out_dir / "GRADUATION_VERDICT.json").is_file()
    assert not (out_dir / "FULL_TEST_RAW.log").exists()
    assert verdict["full_test"] is None


def test_stage_a_not_passed_verdict_is_not_graduated_and_contains_blocker(tmp_path: Path):
    """2. Stage A 未通过时 verdict == 'NOT_GRADUATED'，且 verdict_reasons 含该 blocker 名。"""
    db_path = tmp_path / "scanner.db"
    out_dir = tmp_path / "out"
    _init_test_db(db_path)

    exit_code, verdict = generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=True,
    )

    assert verdict["verdict"] == "NOT_GRADUATED"
    # Stage A must have failed due to duration (< 72h)
    assert verdict["stage_a"]["passed"] is False
    assert "HOURS_COVERED_INSUFFICIENT" in verdict["stage_a"]["blockers"]
    # Check that reason is formatted in verdict_reasons
    assert any("HOURS_COVERED_INSUFFICIENT" in r for r in verdict["verdict_reasons"])


def test_tiny_live_authorized_always_false_and_warns_when_all_pass():
    """3. tiny_live_authorized 在三者全通过时仍须为 false 且 verdict_reasons 里带所有者批准提醒。"""
    fake_state = {
        "as_of": "2026-09-10T12:00:00Z",
        "stage_a": {
            "passed": True,
            "blockers": [],
            "hours_covered": 75.0,
            "hours_required": 72,
            "coverage_ratio": "0.999",
        },
        "stage_b": {
            "passed": True,
            "blockers": [],
            "days_covered": 15,
            "days_required": 14,
        },
        "live_gate": {
            "live_allowed": True,
            "blockers": [],
        },
    }

    verdict = build_verdict(
        state=fake_state,
        full_test={"total": 100, "passed": 100, "failed": 0, "exit_code": 0},
        fault_injection={"report_present": True, "scenarios_passed": 6, "scenarios_total": 6},
        code_version="a2f26259c9fd",
        working_tree_clean=True,
        db_path="reports/lp_rh/scanner.db",
        generated_at="2026-09-10T12:00:00Z",
    )

    assert verdict["tiny_live_authorized"] is False
    assert verdict["verdict"] == "SHADOW_COMPLETE"
    # Must record reminder about owner approval
    assert any("代码判定通过不等于所有者批准" in r or "OWNER_APPROVAL_REQUIRED" in r for r in verdict["verdict_reasons"])


def test_fault_injection_missing_or_unparseable_returns_none_not_zero(tmp_path: Path):
    """4. FAULT_INJECTION_REPORT.md 不存在 -> report_present is False, scenarios_passed is None (不是 0)。
    若存在但无法解析，也必须是 None 而不是猜 6/6 或 0。"""
    missing_path = tmp_path / "NON_EXISTENT_REPORT.md"
    res_missing = parse_fault_injection_report(missing_path)
    assert res_missing["report_present"] is False
    assert res_missing["scenarios_passed"] is None
    assert res_missing["scenarios_total"] is None

    unparseable_path = tmp_path / "FAULT_INJECTION_REPORT.md"
    unparseable_path.write_text("# Corrupted report\nNo scenario info\n", encoding="utf-8")
    res_unparseable = parse_fault_injection_report(unparseable_path)
    assert res_unparseable["report_present"] is True
    assert res_unparseable["scenarios_passed"] is None
    assert res_unparseable["scenarios_total"] is None


def test_missing_section_fails_close_with_null_and_evidence_unavailable():
    """5. 缺失的一节写 null 且 verdict_reasons 里有 EVIDENCE_UNAVAILABLE: 前缀的条目。"""
    # Provide empty state with no stage_a, stage_b, live_gate
    empty_state: Dict[str, Any] = {}
    verdict = build_verdict(
        state=empty_state,
        full_test=None,
        fault_injection=None,
        code_version="a2f26259c9fd",
        working_tree_clean=True,
        db_path="scanner.db",
        generated_at="2026-09-10T12:00:00Z",
    )

    assert verdict["stage_a"] is None
    assert verdict["stage_b"] is None
    assert verdict["live_gate"] is None
    assert verdict["fault_injection"] is None
    assert "EVIDENCE_UNAVAILABLE:stage_a" in verdict["verdict_reasons"]
    assert "EVIDENCE_UNAVAILABLE:stage_b" in verdict["verdict_reasons"]
    assert "EVIDENCE_UNAVAILABLE:live_gate" in verdict["verdict_reasons"]
    assert "EVIDENCE_UNAVAILABLE:fault_injection" in verdict["verdict_reasons"]
    assert verdict["verdict"] == "NOT_GRADUATED"


def test_verdict_json_schema_has_all_top_level_keys(tmp_path: Path):
    """6. 生成的 JSON 可被 json.load 解析，含全部顶层键。"""
    db_path = tmp_path / "scanner.db"
    out_dir = tmp_path / "out"
    _init_test_db(db_path)

    generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=True,
    )

    verdict_file = out_dir / "GRADUATION_VERDICT.json"
    with open(verdict_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = [
        "schema_version",
        "generated_at",
        "code_version",
        "working_tree_clean",
        "db_path",
        "as_of",
        "stage_a",
        "stage_b",
        "live_gate",
        "full_test",
        "fault_injection",
        "verdict",
        "verdict_reasons",
        "tiny_live_authorized",
    ]
    for key in required_keys:
        assert key in data, f"Missing top-level key: {key}"


def test_readiness_dashboard_header_contains_head_and_timestamp(tmp_path: Path):
    """7. dashboard 文件开头含 HEAD 与生成时刻。"""
    db_path = tmp_path / "scanner.db"
    out_dir = tmp_path / "out"
    _init_test_db(db_path)

    generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=True,
    )

    dashboard_content = (out_dir / "READINESS_DASHBOARD.md").read_text(encoding="utf-8")
    first_lines = "\n".join(dashboard_content.splitlines()[:15])
    assert "generated_at:" in first_lines
    assert "code_version:" in first_lines
    assert "working_tree_clean:" in first_lines


def test_full_test_run_with_mocked_subprocess(tmp_path: Path, monkeypatch):
    """Verify test runner writes raw log and correctly records exit_code and counts."""
    db_path = tmp_path / "scanner.db"
    out_dir = tmp_path / "out"
    _init_test_db(db_path)

    fake_pytest_output = (
        "============================= test session starts ==============================\n"
        "tests/test_a.py ...\n"
        "4755 passed, 14 skipped in 50.95s\n"
    )

    class MockCompletedProcess:
        stdout = fake_pytest_output
        stderr = ""
        returncode = 0

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockCompletedProcess())

    exit_code, verdict = generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=False,
    )

    assert (out_dir / "FULL_TEST_RAW.log").is_file()
    log_content = (out_dir / "FULL_TEST_RAW.log").read_text(encoding="utf-8")
    assert "# FULL_TEST_RAW.log" in log_content
    assert "4755 passed" in log_content

    assert verdict["full_test"] is not None
    assert verdict["full_test"]["passed"] == 4755
    assert verdict["full_test"]["total"] == 4755
    assert verdict["full_test"]["failed"] == 0
    assert verdict["full_test"]["exit_code"] == 0


def test_real_prod_db_readonly_run_output_to_tmp(tmp_path: Path):
    """验证使用真实生产库 reports/lp_rh/scanner.db (只读 mode=ro) 生成交付物到 tmp_path:
    - 产物正常写入 tmp_path
    - verdict 判定为 NOT_GRADUATED
    - verdict_reasons 包含 HOURS_COVERED_INSUFFICIENT
    - tiny_live_authorized 必为 False
    """
    if not PROD_DB_PATH.exists():
        pytest.skip("Prod scanner.db does not exist in local environment")

    out_dir = tmp_path / "grad"
    exit_code, verdict = generate_graduation_evidence(
        db_path=PROD_DB_PATH,
        out_dir=out_dir,
        asset_address=CORE_ASSET,
        skip_tests=True,
    )

    assert exit_code == 0
    assert (out_dir / "READINESS_DASHBOARD.md").is_file()
    assert (out_dir / "GRADUATION_VERDICT.json").is_file()
    assert not (out_dir / "FULL_TEST_RAW.log").exists()

    assert verdict["verdict"] == "NOT_GRADUATED"
    assert verdict["tiny_live_authorized"] is False
    assert any("HOURS_COVERED_INSUFFICIENT" in r for r in verdict["verdict_reasons"])

