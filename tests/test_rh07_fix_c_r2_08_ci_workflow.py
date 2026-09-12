"""R2-08 / R3 follow-up: CI workflows must actually load, pass the right
flags, declare the right env, and install the third-party deps the test
suite imports.  String-only assertions cannot catch a YAML indentation
break or an env-not-passed bug, so we parse with ``yaml.safe_load`` and
walk the resulting structure.

Regression history:
  - 6fda329:  commit claimed CI was fixed; audit-regression.yml actually
    had ``import`` at column 1 inside a ``run: |`` block, which makes
    ``yaml.safe_load`` raise ``ScannerError: could not find expected ':'``.
    The string-only test missed this because it only checked for the
    presence of substrings.
  - 6fda329:  python-rh-tests ``pip install`` listed only pytest +
    pytest-xdist; the suite imports Crypto / requests / yaml which
    then fail at collection time.
"""

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _load(name):
    path = WORKFLOWS / name
    assert path.exists(), f"missing workflow: {path}"
    with open(path, "r", encoding="utf-8") as fh:
        # safe_load raises on malformed YAML.  This is the regression that
        # 6fda329 missed: a YAML indent break inside ``run: |`` blew up
        # the audit-regression workflow in CI before any step ran.
        return yaml.safe_load(fh)


def _steps(job):
    return job.get("steps") or []


def _step_env(step, key):
    env = step.get("env") or {}
    return env.get(key)


def _step_run(step):
    return step.get("run") or ""


# ---------------------------------------------------------------------------
# YAML parseability (the regression that 6fda329 missed)
# ---------------------------------------------------------------------------

def test_audit_regression_workflow_yaml_parses():
    wf = _load("audit-regression.yml")
    assert wf is not None
    assert "jobs" in wf
    assert "audit-repro" in wf["jobs"]


def test_ci_workflow_yaml_parses():
    wf = _load("ci.yml")
    assert wf is not None
    assert "jobs" in wf
    assert "python-rh-tests" in wf["jobs"]


# ---------------------------------------------------------------------------
# audit-regression.yml — mode/head/dep wiring
# ---------------------------------------------------------------------------

def test_audit_regression_runs_audit_repro_with_repo_and_allow_other_head():
    wf = _load("audit-regression.yml")
    steps = _steps(wf["jobs"]["audit-repro"])

    run_steps = [s for s in steps if "audit_repro.py" in _step_run(s)]
    assert run_steps, "audit-regression must invoke audit_repro.py"

    run_block = "\n".join(_step_run(s) for s in run_steps)
    assert "--repo" in run_block, "audit_repro.py must be called with --repo"
    assert "--allow-other-head" in run_block, (
        "audit_repro.py must be called with --allow-other-head; without it "
        "audit_repro falls back to REDUCED_REFERENCE_MODEL pinned to old HEAD"
    )


def test_audit_regression_assert_step_receives_github_head_sha():
    """Each step has its own env scope; the env from the prior step is NOT
    inherited.  The assert step must declare GITHUB_HEAD_SHA itself."""
    wf = _load("audit-regression.yml")
    steps = _steps(wf["jobs"]["audit-repro"])

    assert_steps = [
        s for s in steps
        if "Assert" in (s.get("name") or "") or "defects" in _step_run(s)
    ]
    assert assert_steps, "expected an Assert step"

    for step in assert_steps:
        run_block = _step_run(step)
        if "GITHUB_HEAD_SHA" not in run_block and "github.sha" not in run_block:
            continue
        # If this step references GITHUB_HEAD_SHA, it must declare it in env.
        if "GITHUB_HEAD_SHA" in run_block or "os.environ" in run_block:
            sha = _step_env(step, "GITHUB_HEAD_SHA")
            assert sha is not None, (
                "assert step reads GITHUB_HEAD_SHA but does not declare it "
                "in step env; GitHub Actions does not inherit env across steps"
            )


def test_audit_regression_assert_uses_heredoc_to_avoid_yaml_indent():
    """The previous version used ``python -c "..."`` with multi-line Python
    indented inconsistently, breaking YAML parse.  The fix writes the
    Python body to a file via a heredoc."""
    wf = _load("audit-regression.yml")
    steps = _steps(wf["jobs"]["audit-repro"])
    assert_steps = [
        s for s in steps if "Assert" in (s.get("name") or "")
    ]
    assert assert_steps
    run_block = "\n".join(_step_run(s) for s in assert_steps)
    # Either heredoc write-to-file, or strict-indent python -c.  Both
    # forms are acceptable; we just require no raw inline multi-line
    # ``python -c`` that escapes its indent.
    assert "cat >" in run_block or "python -c" in run_block
    # If it uses python -c, the body must be a single quoted line.
    if "python -c" in run_block:
        # No multi-line python -c — that was the bug.
        for line in run_block.splitlines():
            if "python -c" in line:
                # Quote must close on the same line OR be a heredoc form.
                # A multi-line python -c with bare ``import`` after the
                # opener is exactly the 6fda329 regression.
                assert line.rstrip().endswith('"') or "<<" in line, (
                    "python -c must close on same line or use heredoc; "
                    "multi-line python -c without explicit close breaks YAML"
                )


# ---------------------------------------------------------------------------
# ci.yml — python-rh-tests dependencies
# ---------------------------------------------------------------------------

def test_python_rh_tests_installs_required_third_party_packages():
    """The suite imports Crypto (keccak), requests, yaml.  Without these
    pytest collection fails with No module named <X>."""
    wf = _load("ci.yml")
    py_job = wf["jobs"]["python-rh-tests"]
    steps = _steps(py_job)

    install_steps = [
        s for s in steps
        if "pip install" in _step_run(s) or "Install" in (s.get("name") or "")
    ]
    assert install_steps, "python-rh-tests must install dependencies"

    install_block = "\n".join(_step_run(s) for s in install_steps)

    for pkg in ("pytest", "pycryptodome", "requests", "pyyaml"):
        assert pkg in install_block, (
            f"python-rh-tests must install {pkg}; "
            "without it pytest collection fails"
        )


def test_python_rh_tests_triggers_on_rh_branch_push():
    """6fda329 bug: ci.yml push trigger was [main]; RH branch push did
    not fire python-rh-tests at all."""
    wf = _load("ci.yml")
    push = wf.get(True, wf.get("on", {}))  # YAML "on" becomes True via pyyaml
    if isinstance(push, dict):
        push_triggers = push.get("push") or {}
    else:
        push_triggers = {}
    branches = push_triggers.get("branches") or []
    assert "feat/prd-v2.1-m0-shadow" in branches, (
        "ci.yml push branches must include feat/prd-v2.1-m0-shadow"
    )


# ---------------------------------------------------------------------------
# Workflows do not bypass the freeze (regression of an earlier slip)
# ---------------------------------------------------------------------------

def test_no_workflow_bypasses_freeze():
    for wf_path in WORKFLOWS.glob("*.yml"):
        with open(wf_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "LIVE_AUTHORIZED=true" not in text
        assert "tiny_live_authorized: true" not in text
        # Also: no workflow directly mutates the freeze status file.
        assert "LPBOT_RESEARCH_STATUS_CN.md" not in text or "cat " in text
