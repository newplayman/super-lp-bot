"""Unit tests for lp_rh_paper_readiness_v1 module."""
from __future__ import annotations

import json
import subprocess
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


def test_compute_paper_readiness_invokes_subprocess_for_pytest(monkeypatch, tmp_path):
    """Subprocess.run([sys.executable, "-m", "pytest", ...]) is invoked for g1 and g3."""
    calls: list[list[str]] = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        # Write a minimal JUnit XML at the path the caller reads.
        junit_idx = cmd.index("--junitxml") + 1
        junit_path = Path(cmd[junit_idx])
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        _write_junit(junit_path, tests=10, failures=0, errors=0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr("subprocess.run", mock_run)
    rmod.g1_all_pytest_pass()
    rmod.g3_entry_integration_tests_pass()

    assert len(calls) == 2
    assert calls[0][0] == rmod.sys.executable
    assert calls[0][1] == "-m"
    assert calls[0][2] == "pytest"
    assert "tests/" in calls[0]
    assert "--junitxml" in calls[0]
    assert calls[1][0] == rmod.sys.executable


def test_g14_g15_g16_read_counters_file(tmp_path: Path):
    """Zero counters pass; non-zero fails.

    CA-01 (PAPER_ACCEPTANCE_REPAIR_V2): counters file MUST carry the
    head SHA so _read_counters can cross-check the recorded counters
    against the live git HEAD.  Tests now write the current HEAD into
    the file fixture.
    """
    counters_file = tmp_path / "runtime_counters.json"
    counters_file.write_text(
        json.dumps({"head": _current_head(), "keys_created": 0, "signatures": 0, "broadcasts": 0}),
        encoding="utf-8",
    )
    assert g14_keys_created_zero(counters_file)["pass"] is True
    assert g15_signatures_zero(counters_file)["pass"] is True
    assert g16_broadcasts_zero(counters_file)["pass"] is True

    counters_file.write_text(
        json.dumps({"head": _current_head(), "keys_created": 1, "signatures": 0, "broadcasts": 0}),
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


# ---------------------------------------------------------------------------
# PAPER_ACCEPTANCE_REPAIR_V1 §1: REQUIRED-gate verdict-blocking tests.
# ---------------------------------------------------------------------------

def _write_junit(path: Path, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> None:
    path.write_text(
        f'<?xml version="1.0"?><testsuite name="t" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"></testsuite>',
        encoding="utf-8",
    )


def _current_head() -> str:
    """Return the live git HEAD SHA so counters file fixtures can match."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return ""


def test_required_test_timeout_blocks(monkeypatch, tmp_path):
    """g1 timeout -> reason SUBPROCESS_TIMEOUT -> verdict FAIL."""
    def mock_run(cmd, *args, **kwargs):
        import subprocess
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr("subprocess.run", mock_run)
    # Make all other gates pass.
    for name in rmod.GATE_NAMES:
        if name == "g1_all_pytest_pass":
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g1_all_pytest_pass"]["pass"] is False
    assert res["gates"]["g1_all_pytest_pass"]["reason"] == "SUBPROCESS_TIMEOUT"


def test_required_no_junit_blocks(monkeypatch):
    """g1 returns no junit file -> reason FILE_MISSING -> verdict FAIL."""
    def mock_run(cmd, *args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc
    monkeypatch.setattr("subprocess.run", mock_run)
    for name in rmod.GATE_NAMES:
        if name == "g1_all_pytest_pass":
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g1_all_pytest_pass"]["reason"] in ("FILE_MISSING", "PARSE_ERROR")


def test_required_empty_junit_blocks(monkeypatch, tmp_path):
    """g1 junit with tests=0 -> reason NOT_DETERMINABLE -> verdict FAIL."""
    def mock_run(cmd, *args, **kwargs):
        junit_idx = cmd.index("--junitxml") + 1
        junit_path = Path(cmd[junit_idx])
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        _write_junit(junit_path, tests=0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc
    monkeypatch.setattr("subprocess.run", mock_run)
    for name in rmod.GATE_NAMES:
        if name == "g1_all_pytest_pass":
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g1_all_pytest_pass"]["reason"] == "NOT_DETERMINABLE"


def test_advisory_missing_db_blocks_advisory_only(monkeypatch):
    """ADVISORY failure alone does not block verdict, but is reported."""
    for name in rmod.GATE_NAMES:
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    # ADVISORY g11 fails with a UNKNOWN-class reason (DB_PATH_NOT_SET)
    monkeypatch.setattr(
        rmod, "g11_two_providers_usable",
        lambda *a, **kw: {"pass": False, "evidence": {}, "reason": "DB_PATH_NOT_SET"},
    )
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "PASS", "ADVISORY failure alone must not block"
    assert res["gates"]["g11_two_providers_usable"]["pass"] is False
    assert res["summary"]["advisory_unknown"] == 1
    # And if a REQUIRED also fails, verdict is FAIL.
    monkeypatch.setattr(
        rmod, "g6_no_grant_no_virtual_position",
        lambda *a, **kw: {"pass": False, "evidence": {}, "reason": "test failure"},
    )
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"


def test_counters_missing_file_blocks(monkeypatch, tmp_path):
    """Missing runtime counters file -> OBSERVED:UNOBSERVED -> verdict FAIL.

    CA-01 (PAPER_ACCEPTANCE_REPAIR_V2): previously this test expected
    OBSERVED:FILE_MISSING.  The new contract returns OBSERVED:UNOBSERVED
    so callers cannot rely on a hard-coded sentinel; the broader
    UNOBSERVED family still triggers verdict FAIL.
    """
    # Patch env so no production file is found.
    monkeypatch.setenv("LPBOT_RUNTIME_COUNTERS_PATH", str(tmp_path / "no-such-file.json"))
    for name in rmod.GATE_NAMES:
        if name in ("g14_keys_created_zero", "g15_signatures_zero", "g16_broadcasts_zero"):
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g14_keys_created_zero"]["reason"] == "OBSERVED:UNOBSERVED"
    assert res["gates"]["g15_signatures_zero"]["reason"] == "OBSERVED:UNOBSERVED"
    assert res["gates"]["g16_broadcasts_zero"]["reason"] == "OBSERVED:UNOBSERVED"


def test_counters_parse_error_blocks(monkeypatch, tmp_path):
    """Bad JSON -> OBSERVED:PARSE_ERROR -> verdict FAIL."""
    f = tmp_path / "counters.json"
    f.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("LPBOT_RUNTIME_COUNTERS_PATH", str(f))
    for name in rmod.GATE_NAMES:
        if name in ("g14_keys_created_zero", "g15_signatures_zero", "g16_broadcasts_zero"):
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g14_keys_created_zero"]["reason"] == "OBSERVED:PARSE_ERROR"


def test_counters_wrong_head_blocks(monkeypatch, tmp_path):
    """Counters file with mismatched head -> OBSERVED:HEAD_MISMATCH -> verdict FAIL."""
    f = tmp_path / "counters.json"
    f.write_text(json.dumps({
        "head": "0000000000000000000000000000000000000000",
        "keys_created": 0, "signatures": 0, "broadcasts": 0,
    }), encoding="utf-8")
    monkeypatch.setenv("LPBOT_RUNTIME_COUNTERS_PATH", str(f))
    for name in rmod.GATE_NAMES:
        if name in ("g14_keys_created_zero", "g15_signatures_zero", "g16_broadcasts_zero"):
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g14_keys_created_zero"]["reason"] == "OBSERVED:HEAD_MISMATCH"


def test_nonzero_counters_blocks(monkeypatch, tmp_path):
    """keys_created=1 -> verdict FAIL.

    CA-01 (PAPER_ACCEPTANCE_REPAIR_V2): counters file MUST carry the head
    SHA so _read_counters cross-checks before the integer comparison.
    """
    f = tmp_path / "counters.json"
    f.write_text(json.dumps({
        "head": _current_head(), "keys_created": 1, "signatures": 0, "broadcasts": 0,
    }), encoding="utf-8")
    monkeypatch.setenv("LPBOT_RUNTIME_COUNTERS_PATH", str(f))
    for name in rmod.GATE_NAMES:
        if name in ("g14_keys_created_zero", "g15_signatures_zero", "g16_broadcasts_zero"):
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert "keys_created is 1" in res["gates"]["g14_keys_created_zero"]["reason"]


def test_required_pass_passes(monkeypatch, tmp_path):
    """All REQUIRED gates pass with valid evidence -> verdict PASS."""
    # Valid junit file
    def mock_run_subprocess(cmd, *args, **kwargs):
        if "--junitxml" in cmd:
            junit_idx = cmd.index("--junitxml") + 1
            junit_path = Path(cmd[junit_idx])
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            _write_junit(junit_path, tests=10, failures=0, errors=0)
        if "audit_repro.py" in str(cmd):
            json_out = cmd[cmd.index("--json-out") + 1]
            Path(json_out).write_text(json.dumps({
                "head": _git_head(monkeypatch),
                "mode": "AST_EXTRACTED_FULL",
                "run_id": "test-run-id",
                "probe_errors": 0,
                "defects_reproduced": 0,
            }), encoding="utf-8")
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc
    monkeypatch.setattr("subprocess.run", mock_run_subprocess)

    # Valid counters file
    f = tmp_path / "counters.json"
    f.write_text(json.dumps({
        "head": _git_head(monkeypatch), "run_id": "test-run-id",
        "keys_created": 0, "signatures": 0, "broadcasts": 0,
    }), encoding="utf-8")
    monkeypatch.setenv("LPBOT_RUNTIME_COUNTERS_PATH", str(f))

    for name in rmod.GATE_NAMES:
        if name in ("g11_two_providers_usable", "g12_live_allowed_false", "g13_tiny_live_authorized_false"):
            monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
        elif name in ("g1_all_pytest_pass", "g3_entry_integration_tests_pass",
                       "g2_audit_regression_pass"):
            continue
        else:
            monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "PASS", res


def _git_head(monkeypatch_or_none=None):
    import subprocess
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return ""


def test_wrong_audit_head_blocks(monkeypatch, tmp_path):
    """Audit head mismatch -> reason HEAD_MISMATCH -> verdict FAIL."""
    real_head = _git_head(monkeypatch)
    def mock_run(cmd, *args, **kwargs):
        if "audit_repro.py" in str(cmd):
            json_out = cmd[cmd.index("--json-out") + 1]
            Path(json_out).write_text(json.dumps({
                "head": "0000000000000000000000000000000000000000",
                "mode": "AST_EXTRACTED_FULL",
                "run_id": "test-run-id",
                "probe_errors": 0,
                "defects_reproduced": 0,
            }), encoding="utf-8")
        elif "--junitxml" in cmd:
            junit_idx = cmd.index("--junitxml") + 1
            junit_path = Path(cmd[junit_idx])
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            _write_junit(junit_path, tests=10, failures=0, errors=0)
        elif cmd[:3] == ["git", "rev-parse", "HEAD"]:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = real_head
            mock_proc.stderr = ""
            return mock_proc
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc
    monkeypatch.setattr("subprocess.run", mock_run)
    for name in rmod.GATE_NAMES:
        if name == "g2_audit_regression_pass":
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g2_audit_regression_pass"]["reason"] == "HEAD_MISMATCH"


def test_wrong_audit_mode_blocks(monkeypatch, tmp_path):
    """Audit mode not in VALID_AUDIT_MODES -> reason NOT_DETERMINABLE -> verdict FAIL."""
    def mock_run(cmd, *args, **kwargs):
        if "audit_repro.py" in str(cmd):
            json_out = cmd[cmd.index("--json-out") + 1]
            Path(json_out).write_text(json.dumps({
                "head": _git_head(monkeypatch),
                "mode": "TOTALLY_MADE_UP_MODE",
                "run_id": "test-run-id",
                "probe_errors": 0,
                "defects_reproduced": 0,
            }), encoding="utf-8")
        elif "--junitxml" in cmd:
            junit_idx = cmd.index("--junitxml") + 1
            junit_path = Path(cmd[junit_idx])
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            _write_junit(junit_path, tests=10, failures=0, errors=0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc
    monkeypatch.setattr("subprocess.run", mock_run)
    for name in rmod.GATE_NAMES:
        if name == "g2_audit_regression_pass":
            continue
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "FAIL"
    assert res["gates"]["g2_audit_regression_pass"]["reason"] == "NOT_DETERMINABLE"


def test_required_pass_passes_minimal(monkeypatch, tmp_path):
    """Sanity test: with all gates stubbed to PASS, the verdict is PASS (no I/O)."""
    for name in rmod.GATE_NAMES:
        monkeypatch.setattr(rmod, name, lambda *a, **kw: {"pass": True, "evidence": {}, "reason": None})
    res = rmod.compute_paper_readiness()
    assert res["verdict"] == "PASS"
    assert res["summary"]["passed"] == 16
    assert res["summary"]["failed"] == 0


def test_inconclusive_reasons_alias():
    """INCONCLUSIVE_REASONS is kept as an alias of UNKNOWN_REASONS."""
    from scripts.lp_rh_paper_readiness_v1 import INCONCLUSIVE_REASONS, UNKNOWN_REASONS
    assert INCONCLUSIVE_REASONS is UNKNOWN_REASONS
    assert "FILE_MISSING" in INCONCLUSIVE_REASONS
    assert "OBSERVED:HEAD_MISMATCH" in INCONCLUSIVE_REASONS


def test_required_gates_constant():
    """CA-01 (PAPER_ACCEPTANCE_REPAIR_V2): REQUIRED_GATES has 15 entries;
    only g11_two_providers_usable is advisory (RPC not observable in
    read-only research path).  g12 / g13 / g14 / g15 / g16 must block the
    overall verdict — live_allowed and tiny_live_authorized cannot sit in
    advisory or a real config flip would silently clear the gate."""
    assert len(rmod.REQUIRED_GATES) == 15
    assert "g11_two_providers_usable" in rmod.ADVISORY_GATES
    assert "g12_live_allowed_false" not in rmod.ADVISORY_GATES
    assert "g13_tiny_live_authorized_false" not in rmod.ADVISORY_GATES
    assert "g12_live_allowed_false" in rmod.REQUIRED_GATES
    assert "g13_tiny_live_authorized_false" in rmod.REQUIRED_GATES
    assert "g14_keys_created_zero" in rmod.REQUIRED_GATES
    assert "g16_broadcasts_zero" in rmod.REQUIRED_GATES


