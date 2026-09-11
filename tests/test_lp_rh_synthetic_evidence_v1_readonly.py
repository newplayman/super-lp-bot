"""Tests for scripts/lp_rh_synthetic_evidence_v1.py (read-only)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "lp_rh_synthetic_evidence_v1.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("lp_rh_synthetic_evidence_v1", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


generator = _load_module()


def test_parse_pytest_summary_all_passed():
    text = "4611 passed in 123.45s"
    res = generator.parse_pytest_summary(text)
    assert res["total"] == 4611
    assert res["passed"] == 4611
    assert res["failed"] == 0
    assert res["duration_secs"] == 123.45


def test_parse_pytest_summary_with_failures():
    text = "4609 passed, 2 failed in 130.01s"
    res = generator.parse_pytest_summary(text)
    assert res["passed"] == 4609
    assert res["failed"] == 2
    assert res["total"] == 4611
    assert res["duration_secs"] == 130.01


def test_parse_pytest_summary_complex_mix():
    text = "12 failed, 4599 passed, 3 skipped, 1 error in 140.2s"
    res = generator.parse_pytest_summary(text)
    assert res["failed"] == 12
    assert res["passed"] == 4599
    assert res["skipped"] == 3
    assert res["errors"] == 1
    assert res["total"] == 4615
    assert res["duration_secs"] == 140.2


def test_parse_pytest_summary_unrelated_text():
    text = "完全无关的一段文字"
    res = generator.parse_pytest_summary(text)
    for k in generator.SUMMARY_KEYS:
        assert res[k] is None


def test_build_evidence_zero_tests_not_passed(monkeypatch):
    monkeypatch.setattr(generator, "resolve_code_version", lambda repo: ("0123456789ab", True))
    mock_proc = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="0 passed in 0.05s\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    ev = generator.build_evidence(repo=REPO_ROOT, tests_path="tests/", run=True)
    assert ev["exit_code"] == 0
    assert ev["total"] == 0
    assert ev["all_passed"] is False


def test_build_evidence_failed_tests(monkeypatch):
    monkeypatch.setattr(generator, "resolve_code_version", lambda repo: ("0123456789ab", True))
    mock_proc = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="4609 passed, 2 failed in 130.01s\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    ev = generator.build_evidence(repo=REPO_ROOT, tests_path="tests/", run=True)
    assert ev["exit_code"] == 1
    assert ev["failed"] == 2
    assert ev["all_passed"] is False


def test_build_evidence_parse_failure(monkeypatch):
    monkeypatch.setattr(generator, "resolve_code_version", lambda repo: ("0123456789ab", True))
    mock_proc = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="internal error or unexpected output without summary\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    ev = generator.build_evidence(repo=REPO_ROOT, tests_path="tests/", run=True)
    assert ev["exit_code"] == 0
    assert ev["total"] is None
    assert ev["all_passed"] is False


def test_resolve_code_version_non_git_dir(tmp_path):
    with pytest.raises(RuntimeError):
        generator.resolve_code_version(str(tmp_path))


def test_dry_run_does_not_write_file(tmp_path, capsys):
    out_file = tmp_path / "never.json"
    rc = generator.main(["--repo", str(REPO_ROOT), "--dry-run", "--out", str(out_file)])
    assert rc == 0
    assert not out_file.exists()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["code_version_source"] == generator.CODE_VERSION_SOURCE
    assert data["exit_code"] is None
    assert data["total"] is None
    assert data["all_passed"] is False


def test_build_evidence_all_passed_success(monkeypatch):
    monkeypatch.setattr(generator, "resolve_code_version", lambda repo: ("0123456789ab", True))
    mock_proc = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="4611 passed in 123.45s\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

    ev = generator.build_evidence(repo=REPO_ROOT, tests_path="tests/", run=True)
    assert ev["exit_code"] == 0
    assert ev["total"] == 4611
    assert ev["passed"] == 4611
    assert ev["failed"] == 0
    assert ev["errors"] == 0
    assert ev["all_passed"] is True


def test_main_runtime_error_returns_2(tmp_path, capsys):
    rc = generator.main(["--repo", str(tmp_path), "--out", str(tmp_path / "out.json")])
    assert rc == 2
    assert not (tmp_path / "out.json").exists()
    err = capsys.readouterr().err
    assert "error:" in err or "git" in err


def _make_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    def _run(*cmd):
        subprocess.run(["git", *cmd], cwd=str(repo), check=True, capture_output=True, text=True)

    _run("init")
    _run("config", "user.name", "Test Runner")
    _run("config", "user.email", "test@example.com")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "tool.py").write_text("# tool\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_tool.py").write_text("# test\n", encoding="utf-8")
    (repo / "configs").mkdir()
    (repo / "configs" / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    _run("add", ".")
    _run("commit", "-m", "Initial commit with attested paths")
    return repo


def test_parity_generator_and_readiness_code_version(tmp_path):
    """1. 两侧口径一致：同一个仓库状态下，生成侧算出的 version 与比对侧算出的 version 必须相等。"""
    from scripts.lp_rh_readiness_v1_readonly import audit_synthetic_tests
    repo = _make_test_repo(tmp_path)
    sha_gen, clean_gen = generator.resolve_code_version(str(repo))
    assert clean_gen is True
    assert len(sha_gen) == 12

    ev_file = repo / "ev.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": sha_gen,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-11T00:00:00Z",
    }), encoding="utf-8")
    audit = audit_synthetic_tests(ev_file, repo_root=str(repo))
    assert audit["head_version"] == sha_gen
    assert audit["passed"] is True

    # Also verify parity on live repo
    live_sha, _ = generator.resolve_code_version(str(REPO_ROOT))
    live_audit = audit_synthetic_tests(ev_file, repo_root=str(REPO_ROOT))
    assert live_audit["head_version"] == live_sha


def test_unattested_paths_do_not_stale_evidence(tmp_path):
    """2. 只改 docs/ 或 reports/ 或根目录 .md 的提交 -> version 不变 -> 证据不过期。"""
    from scripts.lp_rh_readiness_v1_readonly import audit_synthetic_tests
    repo = _make_test_repo(tmp_path)
    v0, _ = generator.resolve_code_version(str(repo))

    ev_file = repo / "ev.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": v0,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-11T00:00:00Z",
    }), encoding="utf-8")

    # Modify docs, reports, and root .md
    docs_dir = repo / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    reports_dir = repo / "reports" / "lp_rh"
    reports_dir.mkdir(parents=True)
    (reports_dir / "some_report.json").write_text("{}", encoding="utf-8")
    (repo / "README.md").write_text("# Title\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "docs and reports update"], cwd=str(repo), check=True, capture_output=True)

    v_after, _ = generator.resolve_code_version(str(repo))
    assert v_after == v0

    audit = audit_synthetic_tests(ev_file, repo_root=str(repo))
    assert audit["head_version"] == v0
    assert audit["passed"] is True
    assert audit["reason"] == "OK"


def test_scripts_change_stales_evidence(tmp_path):
    """3. 改 scripts/ 下的文件的提交 -> version 变 -> 证据过期。"""
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_STALE_CODE_VERSION,
    )
    repo = _make_test_repo(tmp_path)
    v0, _ = generator.resolve_code_version(str(repo))

    ev_file = repo / "ev.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": v0,
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-11T00:00:00Z",
    }), encoding="utf-8")

    (repo / "scripts" / "tool.py").write_text("# updated tool\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "update scripts"], cwd=str(repo), check=True, capture_output=True)

    v1, _ = generator.resolve_code_version(str(repo))
    assert v1 != v0

    audit = audit_synthetic_tests(ev_file, repo_root=str(repo))
    assert audit["head_version"] == v1
    assert audit["passed"] is False
    assert audit["reason"] == SYNTHETIC_EVIDENCE_STALE_CODE_VERSION


def test_tests_change_updates_version(tmp_path):
    """4. 改 tests/ 下的文件 -> version 变。"""
    repo = _make_test_repo(tmp_path)
    v0, _ = generator.resolve_code_version(str(repo))

    (repo / "tests" / "test_tool.py").write_text("# updated test\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "update tests"], cwd=str(repo), check=True, capture_output=True)

    v1, _ = generator.resolve_code_version(str(repo))
    assert v1 != v0


def test_configs_change_updates_version(tmp_path):
    """5. 改 configs/ 下的文件 -> version 变。"""
    repo = _make_test_repo(tmp_path)
    v0, _ = generator.resolve_code_version(str(repo))

    (repo / "configs" / "config.json").write_text('{"key": "val"}\n', encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "update configs"], cwd=str(repo), check=True, capture_output=True)

    v1, _ = generator.resolve_code_version(str(repo))
    assert v1 != v0


def test_pytest_ini_change_updates_version(tmp_path):
    """6. 改 pytest.ini -> version 变。"""
    repo = _make_test_repo(tmp_path)
    v0, _ = generator.resolve_code_version(str(repo))

    (repo / "pytest.ini").write_text("[pytest]\naddopts = -v\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "update pytest.ini"], cwd=str(repo), check=True, capture_output=True)

    v1, _ = generator.resolve_code_version(str(repo))
    assert v1 != v0


def test_empty_git_log_output_fail_close(tmp_path):
    """7. git log 对这些路径返回空输出 -> 沿用失败处理，不得当成通过。"""
    from scripts.lp_rh_readiness_v1_readonly import (
        audit_synthetic_tests,
        SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED,
    )
    repo = tmp_path / "repo_no_attested"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True, capture_output=True)
    (repo / "unrelated.txt").write_text("only unrelated\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "only unrelated file"], cwd=str(repo), check=True, capture_output=True)

    # 1. Generator side must fail-close (raise RuntimeError), NOT pass or return empty string
    with pytest.raises(RuntimeError) as exc_info:
        generator.resolve_code_version(str(repo))
    assert "unexpected git log sha" in str(exc_info.value) or "git log" in str(exc_info.value)

    # 2. Readiness auditor side must fail-close (passed=None, reason=HEAD_UNRESOLVED), NEVER True
    ev_file = repo / "ev.json"
    ev_file.write_text(json.dumps({
        "schema_version": 1,
        "code_version": "1234567890ab",
        "working_tree_clean": True,
        "all_passed": True,
        "generated_at": "2026-09-11T00:00:00Z",
    }), encoding="utf-8")
    audit = audit_synthetic_tests(ev_file, repo_root=str(repo))
    assert audit["passed"] is None
    assert audit["head_version"] is None
    assert audit["reason"] == SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED
