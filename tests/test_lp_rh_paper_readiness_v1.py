"""Unit tests for lp_rh_paper_readiness_v1 module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

import scripts.lp_rh_paper_readiness_v1 as rmod
from scripts.lp_rh_paper_readiness_v1 import (
    GATE_NAMES,
    INCONCLUSIVE_REASONS,
    compute_paper_readiness,
    g12_live_allowed_false,
    g13_tiny_live_authorized_false,
    g14_keys_created_zero,
    g15_signatures_zero,
    g16_broadcasts_zero,
    render_report,
)


def test_compute_paper_readiness_all_pass(monkeypatch):
    """Monkeypatch each gate to pass -> verdict is PASS and passed==16."""
    for name in GATE_NAMES:
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = compute_paper_readiness()
    assert res["verdict"] == "PASS"
    assert res["summary"]["passed"] == 16
    assert res["summary"]["failed"] == 0
    assert res["summary"]["inconclusive"] == 0


def test_compute_paper_readiness_one_fail(monkeypatch):
    """One gate fails -> verdict is FAIL."""
    for name in GATE_NAMES:
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    monkeypatch.setattr(
        rmod,
        "g6_no_grant_no_virtual_position",
        lambda *a, **kw: {"pass": False, "evidence": {}, "reason": "Virtual position created without grant"},
    )
    res = compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["summary"]["passed"] == 15
    assert res["summary"]["failed"] == 1
    assert res["gates"]["g6_no_grant_no_virtual_position"]["pass"] is False


def test_compute_paper_readiness_inconclusive_does_not_fail(monkeypatch):
    """Inconclusive gate (DB_PATH_NOT_SET) increments inconclusive, verdict remains PASS."""
    assert "DB_PATH_NOT_SET" in INCONCLUSIVE_REASONS
    for name in GATE_NAMES:
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    monkeypatch.setattr(
        rmod,
        "g11_two_providers_usable",
        lambda *a, **kw: {"pass": False, "evidence": {}, "reason": "DB_PATH_NOT_SET"},
    )
    res = compute_paper_readiness()
    assert res["verdict"] == "PASS"
    assert res["summary"]["passed"] == 15
    assert res["summary"]["failed"] == 0
    assert res["summary"]["inconclusive"] == 1


def test_render_report_writes_markdown(tmp_path: Path):
    """render_report creates markdown file with PASS/FAIL and all gate names."""
    report_file = tmp_path / "readiness_report.md"
    gates_data = {
        name: {"pass": True, "evidence": {}, "reason": None} for name in GATE_NAMES
    }
    gates_data["g1_all_pytest_pass"] = {"pass": False, "evidence": {}, "reason": "1 failed"}
    sample_verdict = {
        "verdict": "FAIL",
        "gates": gates_data,
        "summary": {"passed": 15, "failed": 1, "inconclusive": 0},
    }
    render_report(sample_verdict, out_path=report_file)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "FAIL" in content
    assert "Passed" in content
    for name in GATE_NAMES:
        assert name in content


def test_compute_paper_readiness_invokes_subprocess_for_pytest(monkeypatch):
    """Subprocess.run(["pytest", ...]) is invoked for g1 and g3."""
    calls: list[list[str]] = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "10 passed in 0.1s"
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr("subprocess.run", mock_run)
    rmod.g1_all_pytest_pass()
    rmod.g3_entry_integration_tests_pass()

    assert len(calls) == 2
    assert calls[0][0] == "pytest"
    assert calls[0][1] == "tests/"
    assert calls[1][0] == "pytest"


def test_g14_g15_g16_read_counters_file(tmp_path: Path):
    """Zero counters pass; non-zero fails."""
    counters_file = tmp_path / "runtime_counters.json"
    counters_file.write_text(
        json.dumps({"keys_created": 0, "signatures": 0, "broadcasts": 0}),
        encoding="utf-8",
    )
    assert g14_keys_created_zero(counters_file)["pass"] is True
    assert g15_signatures_zero(counters_file)["pass"] is True
    assert g16_broadcasts_zero(counters_file)["pass"] is True

    counters_file.write_text(
        json.dumps({"keys_created": 1, "signatures": 0, "broadcasts": 0}),
        encoding="utf-8",
    )
    res14 = g14_keys_created_zero(counters_file)
    assert res14["pass"] is False
    assert "keys_created is 1" in res14["reason"]


def test_g12_g13_read_config_toml(tmp_path: Path):
    """Check live_allowed and tiny_live_authorized flags."""
    cfg = tmp_path / "config.shadow.toml"
    cfg.write_text("dry_run = true\nmode = 'shadow'\n", encoding="utf-8")
    assert g12_live_allowed_false(cfg)["pass"] is True
    assert g13_tiny_live_authorized_false(cfg)["pass"] is True

    cfg.write_text("live_allowed = true\n", encoding="utf-8")
    res12 = g12_live_allowed_false(cfg)
    assert res12["pass"] is False
    assert "live_allowed = true" in res12["reason"]

    cfg.write_text("tiny_live_authorized = true\n", encoding="utf-8")
    res13 = g13_tiny_live_authorized_false(cfg)
    assert res13["pass"] is False
    assert "tiny_live_authorized = true" in res13["reason"]


def test_g4_full_cost_nav_wired_on_real_runner():
    """Real runner file contains scenario reference and full cost NAV computation."""
    res = rmod.g4_full_cost_nav_wired()
    assert res["pass"] is True
    assert res["evidence"]["has_scenario_reference"] is True
    assert res["evidence"]["has_full_cost_nav"] is True

