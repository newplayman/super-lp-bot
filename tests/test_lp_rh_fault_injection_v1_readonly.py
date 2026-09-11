"""test_lp_rh_fault_injection_v1_readonly.py — RH-02cd 故障注入回归测试套件

自动化验证六个故障注入场景：
  1. fee_growth 置 NULL -> audit_key_field_health.passed=False, Stage A 含 STAGE_A_KEY_FIELDS_INCOMPLETE
  2. health_flags_json 含 CHAIN_DEGRADED -> market_and_chain_risk_pass=False
  3. pool_meta quote 证据过期 -> validate_quote_evidence 失败, NAV 为 None
  4. rh_contract_attestations 最新行状态为 FAILED -> audit_pool_attestation.passed=False, Stage A 含 STAGE_A_POOL_NOT_ATTESTED
  5. 合成测试证据 code_version 与 HEAD 不符 -> audit_synthetic_tests.passed=False, Stage A 含 STAGE_A_SYNTHETIC_TESTS_FAILED
  6. 六张账本表全空 -> audit_invariant_violations.violations_count is None, Stage A 含 STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE

同时保证所有场景的对照组（未注入）必须 100% 通过（非恒红验证）。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import pytest

from scripts.lp_rh_fault_injection_v1_readonly import (
    get_attested_code_version,
    run_all_fault_injections,
    run_scenario_1,
    run_scenario_2,
    run_scenario_3,
    run_scenario_4,
    run_scenario_5,
    run_scenario_6,
)


def test_fault_injection_scenario_1_fee_growth_null(tmp_path):
    res = run_scenario_1(tmp_path)
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["health_passed"] is True
    assert res["injected"]["health_passed"] is False
    assert res["expected_blocker"] in res["injected"]["blockers"]
    assert res["expected_blocker"] not in res["control"]["blockers"]


def test_fault_injection_scenario_2_chain_degraded():
    res = run_scenario_2()
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["market_and_chain_risk_pass"] is True
    assert res["injected"]["market_and_chain_risk_pass"] is False
    assert any("CHAIN_DEGRADED" in r for r in res["injected"]["reasons"])


def test_fault_injection_scenario_3_quote_expired(tmp_path):
    res = run_scenario_3(tmp_path)
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["validate_quote_err"] is None
    assert res["control"]["step_nav"] is not None
    assert res["injected"]["validate_quote_err"] == "QUOTE_EVIDENCE_EXPIRED"
    assert res["injected"]["step_nav"] is None
    assert res["injected"]["step_nav_reason"] == "QUOTE_EVIDENCE_EXPIRED"


def test_fault_injection_scenario_4_contract_attestation_failed(tmp_path):
    res = run_scenario_4(tmp_path)
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["attestation_passed"] is True
    assert res["injected"]["attestation_passed"] is False
    assert res["injected"]["attestation_status"] == "FAILED"
    assert res["expected_blocker"] in res["injected"]["blockers"]
    assert res["expected_blocker"] not in res["control"]["blockers"]


def test_fault_injection_scenario_5_synthetic_evidence_stale_code_version(tmp_path):
    res = run_scenario_5(tmp_path)
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["audit_passed"] is True
    assert res["injected"]["audit_passed"] is False
    assert res["injected"]["reason"] == "SYNTHETIC_EVIDENCE_STALE_CODE_VERSION"
    assert "STAGE_A_SYNTHETIC_TESTS_FAILED" in res["injected"]["blockers"]
    assert "STAGE_A_SYNTHETIC_TESTS_FAILED" not in res["control"]["blockers"]
 
 
def test_fault_injection_scenario_5_head_diverged_from_attested_version(tmp_path):
    """防复发验证：构造「整仓 HEAD 与 ATTESTED 版本不相等」的状态，
    验证场景 5 的对照组仍须通过（严格以 ATTESTED 口径而非整仓 HEAD 为准）。
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # 初始化独立的临时 git 仓库
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)

    # 1. 提交受证明路径文件 scripts/x.py
    scripts_dir = repo_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "x.py").write_text("# attested code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: attested code update"], cwd=repo_dir, check=True, capture_output=True)

    attested_sha = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=repo_dir, check=True, capture_output=True, text=True,
    ).stdout.strip()

    # 2. 提交非受证明路径文件 reports/y.md，使整仓 HEAD 向前推移
    reports_dir = repo_dir / "reports"
    reports_dir.mkdir()
    (reports_dir / "y.md").write_text("# un-attested report\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "docs: report update"], cwd=repo_dir, check=True, capture_output=True)

    head_sha = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=repo_dir, check=True, capture_output=True, text=True,
    ).stdout.strip()

    # 验证前置状态：HEAD 与 ATTESTED 版本确已分叉
    assert head_sha != attested_sha, "整仓 HEAD 与 ATTESTED 版本必须分叉不相等"
    assert get_attested_code_version(repo_dir) == attested_sha

    # 执行场景 5：对照组仍必须通过，注入组仍必须拦截
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    res = run_scenario_5(scratch, repo_root=repo_dir)

    assert res["control_passed"] is True, "当整仓 HEAD 与 ATTESTED 版本分叉时，对照组仍须通过"
    assert res["is_intercepted"] is True, "注入组仍须被拦截"
    assert res["control"]["audit_passed"] is True
    assert res["control"]["evidence_code_version"] == attested_sha
    assert res["control"]["evidence_code_version"] != head_sha
    assert res["injected"]["audit_passed"] is False
    assert res["injected"]["reason"] == "SYNTHETIC_EVIDENCE_STALE_CODE_VERSION"
    assert "STAGE_A_SYNTHETIC_TESTS_FAILED" in res["injected"]["blockers"]
    assert "STAGE_A_SYNTHETIC_TESTS_FAILED" not in res["control"]["blockers"]


def test_fault_injection_scenario_6_ledger_tables_empty(tmp_path):
    res = run_scenario_6(tmp_path)
    assert res["control_passed"] is True, "对照组未通过"
    assert res["is_intercepted"] is True, "注入组未被拦截"
    assert res["control"]["audit_passed"] is True
    assert res["control"]["violations_count"] == 0
    assert res["injected"]["audit_passed"] is False
    assert res["injected"]["violations_count"] is None  # 必须是 None 而非 0
    assert res["expected_blocker"] in res["injected"]["blockers"]
    assert res["expected_blocker"] not in res["control"]["blockers"]
    assert "STAGE_A_INVARIANT_VIOLATIONS" not in res["injected"]["blockers"]


def test_fault_injection_e2e_run_and_report(tmp_path):
    report_file = tmp_path / "FAULT_INJECTION_REPORT.md"
    scratch = tmp_path / "scratch"
    all_ok, results = run_all_fault_injections(scratch, report_out=report_file)
    assert all_ok is True
    assert len(results) == 6
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "# RH-02cd — 故障注入演练报告" in content
    assert "PASS" in content
    assert "STAGE_A_KEY_FIELDS_INCOMPLETE" in content
    assert "CHAIN_DEGRADED" in content
    assert "QUOTE_EVIDENCE_EXPIRED" in content
    assert "STAGE_A_POOL_NOT_ATTESTED" in content
    assert "SYNTHETIC_EVIDENCE_STALE_CODE_VERSION" in content
    assert "STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE" in content
