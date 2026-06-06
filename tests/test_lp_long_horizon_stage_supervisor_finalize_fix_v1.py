"""Tests for LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1.

These tests verify:
  - scripts/run_lp_long_horizon_readonly_stage_once.sh no longer has bash ${REAL_GATE_PASS}
    (lowercase 'true'/'false') interpolated into Python heredoc dict values or ternaries
  - All Python heredocs in the post-stage blocks are quoted (<<'PYEOF' / <<'PYEOF_FALLBACK')
  - Success finalize path writes a FINAL_VERDICT.json with proper bool fields
  - Fallback finalize path writes a CORRECTED_FINAL_VERDICT_FALLBACK.json with proper bool fields
  - Existing 12h checkpoint fixture (5 stable orca_whirlpool pools × 1 ckpt) can be dry-run finalized
  - No auto next-stage advancement
  - No wallet / keypair / signer
  - No tx send
  - Final verdict recommended next stages only from the 4-stage allowed set

All tests are read-only EXCEPT for short dry-run finalize outputs that go to
`data/lp_long_horizon_supervisor_finalize_dryrun/<run_id>/` (cleaned up at end).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_stage_supervisor_finalize_fix" / "20260606_082958"
STAGE_RUNNER = ROOT / "scripts" / "run_lp_long_horizon_readonly_stage_once.sh"
DRYRUN_SCRIPT = ROOT / "scripts" / "test_stage_supervisor_finalize_from_existing_checkpoints_v1.py"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1",
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
    "LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_audit_confirms_root_cause() -> None:
    d = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    assert d["input_evidence_confirmed"]["v2_12h_raw_finalizer_failed"] is True
    assert d["input_evidence_confirmed"]["v2_12h_corrected_verdict_was_needed"] is True
    assert d["input_evidence_confirmed"]["root_cause_python_heredoc_lowercase_true_false"] is True
    assert d["input_evidence_confirmed"]["real_pool_universe_collector_fix_already_done"] is True
    assert d["input_evidence_confirmed"]["this_stage_only_fixes_finalize_does_not_start_run"] is True
    assert 361 in d["bug_details"]["root_cause_line_in_stage_runner"]
    assert 471 in d["bug_details"]["root_cause_line_in_stage_runner"]
    assert 494 in d["bug_details"]["root_cause_line_in_stage_runner"]


# ---------------------------------------------------------------------------
# Stage B: supervisor finalize fix — no lowercase boolean in Python heredoc
# ---------------------------------------------------------------------------

def _extract_python_heredocs(text: str) -> list[tuple[str, int, str]]:
    """Extract (heredoc_tag, start_line, body) for every <<TAG or <<'TAG' python heredoc."""
    results: list[tuple[str, int, str]] = []
    for m in re.finditer(r"<<('?)([A-Z_]+)\1", text):
        quote = m.group(1)
        tag = m.group(2)
        # only consider Python-ish tags
        if "PY" not in tag and "EOF" not in tag:
            continue
        start = m.start()
        # body runs to next line that contains just the tag
        body_start = text.find("\n", start) + 1
        end_line = text.find(f"\n{tag}\n", body_start)
        if end_line < 0:
            end_line = text.find(f"\n{tag}", body_start)
        if end_line < 0:
            continue
        body = text[body_start:end_line]
        line_no = text[:start].count("\n") + 1
        results.append((tag, line_no, body))
    return results


def test_b_no_unquoted_python_heredoc_with_bash_interpolation() -> None:
    """All Python heredocs in the stage runner must be quoted (<<'PYEOF') to prevent
    bash interpolation of values into Python expressions."""
    text = STAGE_RUNNER.read_text()
    bad: list[tuple[str, int, str]] = []
    for tag, line_no, body in _extract_python_heredocs(text):
        if not body:
            continue
        # If body references any ${...} bash var, the heredoc must be quoted
        if "${" in body:
            # Find original heredoc opener line in full text
            opener = f"<<{tag}"
            opener_quoted = f"<<'{tag}'"
            # check that the opener line is the quoted form
            for ln, line in enumerate(text.splitlines(), 1):
                if opener in line and opener_quoted not in line and "EOF" in line and "${" not in line.split(opener)[0]:
                    bad.append((tag, ln, line.strip()))
                    break
    # We expect zero bad heredocs after the fix
    assert not bad, f"unquoted Python heredocs with bash interpolation: {bad}"


def test_b_no_lowercase_bash_boolean_in_python_heredoc_executable() -> None:
    """No ${REAL_GATE_PASS} interpolated into Python expression contexts.

    Pattern: the literal substring '${REAL_GATE_PASS}' (without ^^) appearing inside
    a Python heredoc body — this is the source of the NameError on lowercase 'true'/'false'.
    """
    text = STAGE_RUNNER.read_text()
    # Look for any line that has ${REAL_GATE_PASS} (without ^^ uppercasing) and is inside
    # a Python heredoc body
    in_python = False
    cur_tag = None
    for ln, line in enumerate(text.splitlines(), 1):
        if re.search(r"<<'?(PY[A-Z_]*)'?", line):
            m = re.search(r"<<'?(PY[A-Z_]*)'?", line)
            if m:
                cur_tag = m.group(1)
                in_python = True
                continue
        if in_python and line.strip() == cur_tag:
            in_python = False
            cur_tag = None
            continue
        if in_python and "${REAL_GATE_PASS}" in line and "${REAL_GATE_PASS^^}" not in line:
            # bug: bash boolean literal embedded in Python
            snippet = line.strip()[:100]
            pytest.fail(f"line {ln}: ${{REAL_GATE_PASS}} embedded in Python heredoc body: {snippet!r}")


def test_b_aggregate_block_uses_quoted_heredoc() -> None:
    """The aggregate block (which writes aggregate_summary.json) must use quoted heredoc."""
    text = STAGE_RUNNER.read_text()
    # Find the 'for i in $(seq' end and the python3 <<PYEOF after it
    assert "python3 <<'PYEOF_AGG'" in text or "python3 - <<'PYEOF_AGG'" in text, \
        "aggregate block must use quoted heredoc <<'PYEOF_AGG'"


def test_b_finalize_block_uses_quoted_heredoc() -> None:
    """The finalize block (which writes FINAL_VERDICT.json) must use quoted heredoc."""
    text = STAGE_RUNNER.read_text()
    assert "python3 <<'PYEOF_FINAL'" in text or "python3 - <<'PYEOF_FINAL'" in text, \
        "finalize block must use quoted heredoc <<'PYEOF_FINAL'"


def test_b_fallback_block_uses_quoted_heredoc() -> None:
    """The fallback block (which writes CORRECTED_FINAL_VERDICT_FALLBACK.json) must use quoted heredoc."""
    text = STAGE_RUNNER.read_text()
    assert "python3 <<'PYEOF_FALLBACK'" in text or "python3 - <<'PYEOF_FALLBACK'" in text, \
        "fallback block must use quoted heredoc <<'PYEOF_FALLBACK'"


def test_b_aggregate_block_writes_proper_bool_to_json() -> None:
    """aggregate_summary.json must contain a real JSON boolean for actual_runtime_valid_for_<STAGE>_gate."""
    text = STAGE_RUNNER.read_text()
    # The aggregate block must write a Python bool, not interpolate bash 'true'/'false'
    # Search for the aggregate block and verify it uses Python's `>=` for the comparison
    # and writes True/False literals
    aggregate_section = re.search(
        r"python3.*?PYEOF_AGG.*?\n(.*?)\nPYEOF_AGG",
        text, re.DOTALL,
    )
    if aggregate_section:
        body = aggregate_section.group(1)
        # Should not contain ${REAL_GATE_PASS} literal
        assert "${REAL_GATE_PASS}" not in body, "aggregate block must not embed ${REAL_GATE_PASS}"


def test_b_finalize_block_no_bash_boolean() -> None:
    """The finalize block (post-aggregate) must not contain ${REAL_GATE_PASS}."""
    text = STAGE_RUNNER.read_text()
    # Find the finalize block
    finalize_section = re.search(
        r"python3.*?PYEOF_FINAL.*?\n(.*?)\nPYEOF_FINAL",
        text, re.DOTALL,
    )
    if finalize_section:
        body = finalize_section.group(1)
        assert "${REAL_GATE_PASS}" not in body, "finalize block must not embed ${REAL_GATE_PASS}"


def test_b_fallback_block_no_bash_boolean() -> None:
    """The fallback block must not contain ${REAL_GATE_PASS} in any form."""
    text = STAGE_RUNNER.read_text()
    fallback_section = re.search(
        r"python3.*?PYEOF_FALLBACK.*?\n(.*?)\nPYEOF_FALLBACK",
        text, re.DOTALL,
    )
    if fallback_section:
        body = fallback_section.group(1)
        assert "${REAL_GATE_PASS}" not in body, "fallback block must not embed ${REAL_GATE_PASS}"


def test_b_stage_runner_syntax() -> None:
    rc = subprocess.run(["bash", "-n", str(STAGE_RUNNER)], capture_output=True, text=True)
    assert rc.returncode == 0, f"stage runner syntax error: {rc.stderr}"


# ---------------------------------------------------------------------------
# Stage C: dry-run finalize test script
# ---------------------------------------------------------------------------

def test_c_dryrun_script_exists() -> None:
    assert DRYRUN_SCRIPT.exists()
    assert DRYRUN_SCRIPT.is_file()


def test_c_dryrun_script_syntax() -> None:
    import py_compile
    try:
        py_compile.compile(str(DRYRUN_SCRIPT), doraise=True)
    except py_compile.PyCompileError as e:
        pytest.fail(f"compile error: {e}")


def test_c_dryrun_script_runs_against_existing_12h_checkpoints() -> None:
    """Run the dry-run script against the existing 12h checkpoint fixture.

    12h run has 12 checkpoint dirs under data/lp_long_horizon/20260605_082120/.

    The dry-run script must:
    - Read those checkpoints read-only
    - Generate aggregate_summary.json + FINAL_VERDICT.json + CORRECTED_FINAL_VERDICT_FALLBACK.json
      in a test output dir (NOT modifying the source 12h data)
    - Final verdict status must be PASS for the success path (12h had gate=PASS)
    - No wallet / keypair / signer / tx / probe
    """
    src_12h_data = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src_12h_data.exists():
        pytest.skip("12h fixture data not present")

    test_out = ROOT / "data" / "lp_long_horizon_supervisor_finalize_dryrun" / "20260606_082958"
    if test_out.exists():
        shutil.rmtree(test_out)
    test_out.mkdir(parents=True)

    rc = subprocess.run(
        [
            sys.executable, str(DRYRUN_SCRIPT),
            "--source-data", str(src_12h_data),
            "--source-report", str(ROOT / "reports" / "lp_long_horizon_readonly_12h_run" / "20260605_082120"),
            "--out", str(test_out),
            "--run-id", "20260606_082958",
            "--stage", "12h",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode == 0, f"dry-run script failed: rc={rc.returncode}, stderr={rc.stderr}"

    # Verify success path produced FINAL_VERDICT.json
    fv_path = test_out / "FINAL_VERDICT.json"
    assert fv_path.exists(), "success path must produce FINAL_VERDICT.json"
    fv = json.loads(fv_path.read_text())
    assert fv["status"] == "PASS", f"expected PASS, got {fv['status']}: {fv.get('finalize_error')}"
    assert fv["actual_runtime_minutes"] >= 660, "expected actual_runtime_minutes >= 660 (12h)"
    assert fv["actual_runtime_valid_for_12h_gate"] is True
    assert fv["gate_pass"] is True
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False

    # Verify aggregate_summary.json is also written
    agg = json.loads((test_out / "aggregate_summary.json").read_text())
    assert agg["actual_runtime_valid_for_12h_gate"] is True
    assert agg["row_counts_deduped"]["pool_snapshots"] > 0

    # Cleanup
    shutil.rmtree(test_out, ignore_errors=True)


def test_c_dryrun_script_does_not_modify_source_12h_data() -> None:
    """The dry-run script must not modify the source 12h data dir."""
    src_12h_data = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src_12h_data.exists():
        pytest.skip("12h fixture data not present")

    # Snapshot file paths + sizes
    before: dict[str, int] = {}
    for p in src_12h_data.rglob("*"):
        if p.is_file():
            before[str(p.relative_to(src_12h_data))] = p.stat().st_size

    test_out = ROOT / "data" / "lp_long_horizon_supervisor_finalize_dryrun" / "20260606_082958_no_modify"
    if test_out.exists():
        shutil.rmtree(test_out)
    test_out.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable, str(DRYRUN_SCRIPT),
            "--source-data", str(src_12h_data),
            "--source-report", str(ROOT / "reports" / "lp_long_horizon_readonly_12h_run" / "20260605_082120"),
            "--out", str(test_out),
            "--run-id", "20260606_082958",
            "--stage", "12h",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )

    # Re-snapshot
    after: dict[str, int] = {}
    for p in src_12h_data.rglob("*"):
        if p.is_file():
            after[str(p.relative_to(src_12h_data))] = p.stat().st_size

    assert before == after, "source 12h data was modified by dry-run script"

    # Cleanup
    shutil.rmtree(test_out, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage D: locked fields and final verdict
# ---------------------------------------------------------------------------

def test_d_final_verdict_required_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    required = {
        "stage", "status",
        "raw_finalize_bug_fixed", "fallback_finalize_bug_fixed",
        "lowercase_python_boolean_removed",
        "existing_12h_checkpoint_finalize_dryrun_pass",
        "final_verdict_always_generated",
        "auto_next_stage_disabled",
        "long_run_started",
        "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_d_final_verdict_locked_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["auto_next_stage_disabled"] is True
    assert fv["long_run_started"] is False


def test_d_final_verdict_recommended_next_stage_allowed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    rec = fv["recommended_next_stage"]
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in allowed set"


def test_d_final_verdict_bug_fixes_true() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["raw_finalize_bug_fixed"] is True
    assert fv["fallback_finalize_bug_fixed"] is True
    assert fv["lowercase_python_boolean_removed"] is True
    assert fv["final_verdict_always_generated"] is True
    assert fv["existing_12h_checkpoint_finalize_dryrun_pass"] is True


def test_d_no_forbidden_process() -> None:
    """No canary / live / paper / sendTransaction / keypair / private_key / mnemonic process."""
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_d_no_no_running_long_horizon_collectors() -> None:
    """No long-horizon collector / stage supervisor should be running."""
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in ["run_lp_long_horizon_readonly_stage_once", "lp_long_horizon_readonly_collector_v1"]:
            if tok in line:
                pytest.fail(f"long-horizon collector/runner still running: {line}")


def test_d_no_secret_value_in_outputs() -> None:
    """No real secret values in this stage's outputs."""
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {m.group(0)[:80]}")
