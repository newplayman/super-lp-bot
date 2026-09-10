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
