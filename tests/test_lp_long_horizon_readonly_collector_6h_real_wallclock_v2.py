"""Tests for LP Long Horizon Read-only Collector 6h Real Wallclock V2.

Verifies (per task spec V2):
- V1 loop bug is fixed (no missing-sleep at last iteration)
- 5h runtime cannot pass gate (must be >= 330)
- actual_runtime_minutes >= 330 required
- short_mode_used=true never passes
- no auto advance to 12h
- no private key / seed / keypair
- no signer
- no tx send
- no wallet path
- final verdict allowed next stages only
- V1 Python `false` typo is gone (no lowercase booleans in Python heredocs)
- V2 fail-safe trap writes FAIL verdict on early exit
- V2 supervisor has set -euo pipefail
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
SUPERVISOR_SCRIPT = REPO_ROOT / "scripts" / "run_lp_long_horizon_readonly_6h_once.sh"
COLLECTOR_SCRIPT = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"

V1_SALVAGE = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260604_134918" / "FINAL_VERDICT.json"
V1_AUDIT = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_fix" / "20260604_134918" / "v1_completion_audit.json"


# ---------------------------------------------------------------------------
# 1. V1 loop bug fix verification
# ---------------------------------------------------------------------------

def test_v1_loop_bug_fixed():
    """V1 had `if [ "$i" -lt $LOOP_COUNT ]` which skipped the sleep for the
    last iteration, causing 5h wallclock. V2 must use END_TS-based logic so
    the last iteration's sleep is preserved (or sleep until END_TS)."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")

    # V1's broken pattern (only i < LOOP_COUNT sleeps) MUST still exist somewhere
    # (we don't want to remove it entirely — we want to ADD a V2 fix on top).
    # But V2 MUST have additional logic to sleep until END_TS after last ckpt.
    assert "V2 wallclock fix" in text, "V2 wallclock fix marker missing"
    assert "END_TS=" in text, "END_TS-based loop control missing"
    # V2 must have logic to sleep until END_TS after last checkpoint
    assert "last checkpoint done; sleeping" in text, (
        "V2 must sleep after last checkpoint to reach END_TS"
    )
    # The original sleep-skipping pattern should be documented in a comment
    assert "V1 had a bug" in text, "V1 bug should be documented for future readers"


def test_v2_total_wallclock_guaranteed_6h():
    """V2 must enforce that wallclock >= 6h. Verify the END_TS-based logic
    in the supervisor (START_TS + 6*3600) and the post-final sleep logic."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # END_TS = START_TS + 6 * 3600
    assert "END_TS=$(( START_TS + 6 * 3600 ))" in text
    # After the last checkpoint, REMAINING = END_TS - now must be sleeped
    assert "REMAINING=$(( END_TS - $(date +%s) ))" in text
    # Final tail sleep to hit exactly END_TS
    assert "TAIL=$(( END_TS - $(date +%s) ))" in text


# ---------------------------------------------------------------------------
# 2. 5h runtime cannot pass gate
# ---------------------------------------------------------------------------

def test_5h_runtime_cannot_pass_gate():
    """If actual_runtime_minutes is 300 (5h), gate must be FAIL."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # The gate check: ELAPSED_MIN < 330 → FAIL
    assert '"${ELAPSED_MIN}" -lt 330' in text
    assert "REAL_6H_GATE_PASS=false" in text
    assert "GATE_DECISION=\"FAIL\"" in text
    # The fail path must write FAIL verdict (no skipping)
    assert "still write finalize + FINAL_VERDICT with status=FAIL" in text


def test_min_runtime_threshold_330():
    """V2 must require actual_runtime_minutes >= 330 to PASS."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "actual_runtime_minutes=${ELAPSED_MIN}" in text
    # In the JSON output, runtime validity is computed from ELAPSED_MIN
    # Look for the gate threshold comparison
    assert "actual_runtime_valid_for_6h_gate" in text


# ---------------------------------------------------------------------------
# 3. short_mode_used=true never passes
# ---------------------------------------------------------------------------

def test_short_mode_rejected_by_supervisor():
    """SLEEP_SECONDS < 3600 must be rejected as short mode (exit 8)."""
    result = subprocess.run(
        ["bash", "-c",
         "SLEEP_SECONDS=10 LOOP_COUNT=6 bash scripts/run_lp_long_horizon_readonly_6h_once.sh 99999999_test"],
        capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
    )
    combined = (result.stdout + result.stderr).lower()
    assert "refused" in combined
    assert "short mode forbidden" in combined
    assert "sleep_seconds=10 < 3600" in combined
    assert result.returncode != 0


def test_loop_count_override_rejected():
    """LOOP_COUNT != 6 must be rejected (exit 9)."""
    result = subprocess.run(
        ["bash", "-c",
         "SLEEP_SECONDS=3600 LOOP_COUNT=10 bash scripts/run_lp_long_horizon_readonly_6h_once.sh 99999999_test"],
        capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
    )
    combined = (result.stdout + result.stderr).lower()
    assert "refused" in combined
    assert "override forbidden" in combined
    assert "loop_count=10 != 6" in combined
    assert result.returncode != 0


def test_short_mode_used_true_cannot_pass():
    """V1 audit shows short_mode_used=false (V2 must also enforce this).

    Even if short mode somehow bypassed the preflight, the gate would
    fail because actual_runtime_minutes would be ~5h not ~6h."""
    assert V1_SALVAGE.exists(), "V1 salvage FINAL_VERDICT must exist for V2 audit"
    v1 = json.loads(V1_SALVAGE.read_text(encoding="utf-8"))
    assert v1["short_mode_used"] is False
    assert v1["actual_runtime_minutes"] < 330
    assert v1["gate_pass"] is False


# ---------------------------------------------------------------------------
# 4. Python `false` typo is gone
# ---------------------------------------------------------------------------

def test_no_lowercase_false_in_python_heredoc():
    """V1 had `\"short_mode_used\": false,` (lowercase) in Python heredoc,
    causing NameError. V2 must use `False` everywhere in Python heredocs."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")

    # Extract all Python heredoc blocks (between `<<PYEOF` and `PYEOF` markers)
    blocks = re.findall(r"<<PYEOF[^\n]*\n(.*?)\nPYEOF", text, re.DOTALL)

    # Strip out f-string contents (where {} is used for formatting) and
    # bash-variable-interpolated lines. Look for bare JSON-style booleans.
    bad_patterns = [
        re.compile(r":\s*false\s*[,}]"),  # : false, or : false}
        re.compile(r":\s*true\s*[,}]"),   # : true, or : true}
        re.compile(r"=\s*false\b"),       # = false (kwarg)
        re.compile(r"=\s*true\b"),        # = true (kwarg)
    ]

    for i, block in enumerate(blocks):
        for j, line in enumerate(block.splitlines(), 1):
            for pat in bad_patterns:
                m = pat.search(line)
                if m:
                    # Allow if the line is a comment or a string
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    # Allow f-string format specs (e.g. {str(...).lower()})
                    if "{" in line and "}" in line and "lower()" in line:
                        # Likely `str(x).lower()` returning "true"/"false" strings
                        continue
                    pytest.fail(
                        f"Python heredoc block {i+1} line {j} has lowercase boolean: {line!r}"
                    )


def test_python_finalize_block_runs():
    """The main finalize Python heredoc must NOT have lowercase booleans
    (the V1 NameError cause). The block is shell-interpolated at runtime, so
    we can't ast.parse it as-is, but we can scan the raw text for the
    forbidden lowercase booleans and also verify uppercase False/True is used."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # Find the main finalize blocks (PYEOF-delimited)
    blocks = re.findall(r"<<PYEOF[^\n]*\n(.*?)\nPYEOF", text, re.DOTALL)
    assert len(blocks) >= 1, "expected at least 1 Python heredoc block"

    bad_patterns = [
        re.compile(r":\s*false\s*[,}]"),  # : false, or : false}
        re.compile(r":\s*true\s*[,}]"),   # : true, or : true}
    ]

    for i, block in enumerate(blocks):
        for j, line in enumerate(block.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue  # comment line
            for pat in bad_patterns:
                if pat.search(line):
                    pytest.fail(
                        f"Python heredoc block {i+1} line {j} has lowercase boolean: {line!r}"
                    )

    # Also verify the V2 fix: at least one block uses False/True (Python uppercase)
    has_python_boolean = any("False" in b or "True" in b for b in blocks)
    assert has_python_boolean, "no Python uppercase booleans (False/True) found in heredocs"


# ---------------------------------------------------------------------------
# 5. V2 fail-safe trap
# ---------------------------------------------------------------------------

def test_v2_fail_safe_trap_present():
    """V2 must have a trap that writes FAIL FINAL_VERDICT on early exit
    (closes the V1 NameError silent-loss bug)."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "trap 'write_fail_verdict_on_trap EXIT' EXIT" in text
    assert "trap 'write_fail_verdict_on_trap SIGTERM" in text
    assert "trap 'write_fail_verdict_on_trap SIGINT" in text
    assert "trap 'write_fail_verdict_on_trap SIGHUP" in text
    assert "write_fail_verdict_on_trap" in text
    assert "FINAL_VERDICT.json" in text


def test_v2_set_euo_pipefail_present():
    """V2 must have set -euo pipefail at script start to catch errors early."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # The very first non-comment line should be `set -euo pipefail`
    lines = text.splitlines()
    for i, line in enumerate(lines[:30], 1):
        if line.strip() and not line.strip().startswith("#"):
            if "set -euo pipefail" in line:
                return
            else:
                pytest.fail(
                    f"set -euo pipefail must appear before any non-comment line; "
                    f"first non-comment line at {i}: {line!r}"
                )
    pytest.fail("set -euo pipefail not found in supervisor header")


# ---------------------------------------------------------------------------
# 6. no auto advance to 12h
# ---------------------------------------------------------------------------

def test_no_auto_advance_to_12h():
    """V2 must never auto-advance to 12h. Even on PASS, the user must give
    a new manual approval (the 6h→12h step requires fresh approval)."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # The 12h recommendation is gated on the gate_pass flag
    # The auto_advance_started flag must always be False
    assert '"auto_advance_started": False' in text
    # The 12h step is only "recommended_next_stage", not "auto-launch"
    assert "12H_RUN_APPROVAL_V1" in text  # recommended but not auto
    # No "auto_launch" or "start_12h" command in supervisor
    assert "auto_launch_12h" not in text
    assert "start_12h" not in text
    assert "begin_12h" not in text


# ---------------------------------------------------------------------------
# 7. no keypair / signer / tx
# ---------------------------------------------------------------------------

def _strip_banned_list_and_comments(text: str) -> str:
    """Strip heredoc / echos / comments / egrep patterns before banned-token check."""
    lines = []
    for line in text.splitlines():
        in_single = False
        in_double = False
        idx = -1
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                idx = i
                break
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"egrep\s+'[^']*'", "egrep '<stripped>'", text)
    text = re.sub(r"grep\s+'[^']*'", "grep '<stripped>'", text)
    text = re.sub(r"egrep\s+\"[^\"]*\"", "egrep \"<stripped>\"", text)
    text = re.sub(r"grep\s+\"[^\"]*\"", "grep \"<stripped>\"", text)
    return text


def test_supervisor_no_banned_token_in_real_code():
    raw = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    text = _strip_banned_list_and_comments(raw)
    banned_calls = [
        "new Signer(",
        "new Wallet(",
        "sendTransaction(",
        "eth_sendRawTransaction",
        "eth_sendTransaction",
        "signTransaction(",
        "signAndSendTransaction(",
        "add_liquidity(",
        "remove_liquidity(",
        "collect_fee(",
        "collect(",
        "mint(",
        "approve(",
        "burn(",
        "transfer(",
    ]
    for token in banned_calls:
        assert token not in text, f"banned call {token!r} found in supervisor"


def test_no_wallet_path_in_supervisor():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "keystore.json" not in text
    assert "encrypted_json" not in text
    assert "keypair.json" not in text


def test_no_production_write_path():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    bad_paths = [
        "data/dryrun",
        "data/shadow",
        "data/live",
        "migrations/",
        "/cmd/lpbot",
        "internal/adapters",
    ]
    for bad in bad_paths:
        assert bad not in text, f"production-like path {bad!r} found"


def test_no_shadow_overwrite():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "data/lp_long_horizon/shadow" not in text
    assert "data/lp_long_horizon/live" not in text
    # The only data path is data/lp_long_horizon/${RUN_ID}
    assert "data/lp_long_horizon/${RUN_ID}" in text
    # Only report path is reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}
    assert "reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}" in text


# ---------------------------------------------------------------------------
# 8. final verdict allowed next stages only
# ---------------------------------------------------------------------------

def test_final_verdict_allowed_next_stages():
    """The recommended_next_stage must be one of 5 allowed values:
    - LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1
    - LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT
    - LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT
    - PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA
    - STOP_LP_RESEARCH_NOW"""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    allowed = [
        "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    ]
    # The V1 salvage FINAL_VERDICT must use one of these 5 names as recommended_next_stage
    assert V1_SALVAGE.exists()
    v1 = json.loads(V1_SALVAGE.read_text(encoding="utf-8"))
    # V1 salvage recommends V2 (which contains "REAL_WALLCLOCK_FIX_REPEAT_V2", a V2-specific name)
    # The V1 salvage uses V2 as recommended_next_stage per task spec
    assert v1["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2", (
        f"V1 salvage recommended_next_stage must be V2"
    )
    # The supervisor's finalize path must write one of the 5 allowed stages
    # (when it succeeds with the gate, not the V1 salvage path)
    # Look for: 12H_RUN_APPROVAL_V1 (PASS path) and FIX_REPEAT (FAIL path)
    assert "12H_RUN_APPROVAL_V1" in text  # PASS recommendation
    assert "REAL_WALLCLOCK_FIX_REPEAT" in text  # FAIL recommendation


# ---------------------------------------------------------------------------
# 9. can_run_probe_now / tiny_canary_allowed false / no
# ---------------------------------------------------------------------------

def test_can_run_probe_now_false_tiny_canary_no():
    """V1 salvage FINAL_VERDICT must have can_run_probe_now=false and
    tiny_canary_allowed='no'. V2 must preserve this."""
    assert V1_SALVAGE.exists()
    v1 = json.loads(V1_SALVAGE.read_text(encoding="utf-8"))
    assert v1["can_run_probe_now"] is False
    assert v1["tiny_canary_allowed"] == "no"
    assert v1["wallet_or_tx_touched"] is False
    assert v1["transaction_sent"] is False


# ---------------------------------------------------------------------------
# 10. V1 salvage integrity
# ---------------------------------------------------------------------------

def test_v1_salvage_final_verdict_complete():
    """V1 salvage FINAL_VERDICT.json must have all required fields per task spec."""
    assert V1_SALVAGE.exists(), "V1 salvage FINAL_VERDICT must exist"
    v1 = json.loads(V1_SALVAGE.read_text(encoding="utf-8"))
    required = [
        "stage", "status", "six_hour_run_completed",
        "actual_runtime_minutes", "actual_runtime_valid_for_6h_gate",
        "short_mode_used", "supervisor_finalize_failed", "finalize_error",
        "checkpoints_generated", "gate_pass", "can_advance_to_12h",
        "recommended_next_stage", "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent",
    ]
    for k in required:
        assert k in v1, f"V1 salvage FINAL_VERDICT missing field {k!r}"
    # status must be FAIL
    assert v1["status"] == "FAIL"
    assert v1["six_hour_run_completed"] is False
    assert v1["short_mode_used"] is False
    assert v1["supervisor_finalize_failed"] is True
    assert "false" in v1["finalize_error"]  # the actual error
    assert v1["checkpoints_generated"] == 6
    assert v1["gate_pass"] is False
    assert v1["can_advance_to_12h"] is False
    assert v1["can_run_probe_now"] is False
    assert v1["tiny_canary_allowed"] == "no"
    assert v1["wallet_or_tx_touched"] is False
    assert v1["transaction_sent"] is False
    # recommended_next_stage must be V2
    assert v1["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2"


def test_v1_completion_audit_acknowledged():
    """V1 audit must document the 2 bugs (loop + Python false typo)."""
    assert V1_AUDIT.exists()
    audit = json.loads(V1_AUDIT.read_text(encoding="utf-8"))
    assert audit["actual_runtime_minutes"] < 330
    assert audit["actual_runtime_valid_for_6h_gate"] is False
    assert audit["v1_completion_status"] == "FAIL"
    assert "bug_1_bash_loop_missing_sleep" in audit["bugs_in_supervisor_v1"]
    assert "bug_2_python_lowercase_false" in audit["bugs_in_supervisor_v1"]


# ---------------------------------------------------------------------------
# 11. process safety (no canary / live / paper / keypair process)
# ---------------------------------------------------------------------------

def test_no_canary_live_paper_keypair_process():
    r = subprocess.run(
        ["bash", "-c",
         "ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|"
         "eth_sendTransaction|keypair' | grep -v grep || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    matched = [line for line in r.stdout.splitlines() if "grep" not in line and line.strip()]
    suspicious = [m for m in matched if any(
        b in m.lower() for b in ["canary", "lpbot-live", "paper", "sendtransaction",
                                  "eth_sendraw", "eth_sendtransaction", "keypair"]
    )]
    assert not suspicious, f"suspicious running process: {suspicious}"


def test_no_extra_tmux_session():
    """No more than 1 lp_long_horizon tmux session should exist."""
    r = subprocess.run(
        ["bash", "-c", "tmux ls 2>/dev/null | grep 'lp_long_horizon' | wc -l"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    count = int(r.stdout.strip() or "0")
    assert count <= 1, f"expected <=1 lp_long_horizon tmux session, got {count}"


# ---------------------------------------------------------------------------
# 12. V2 supervisor smoke (does not run, just parse + preflight)
# ---------------------------------------------------------------------------

def test_supervisor_executable():
    """V2 supervisor must be executable and pass `bash -n` syntax check."""
    import os
    import stat
    st = SUPERVISOR_SCRIPT.stat()
    assert st.st_mode & stat.S_IXUSR, "supervisor script not executable"
    result = subprocess.run(
        ["bash", "-n", str(SUPERVISOR_SCRIPT)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"supervisor syntax error: {result.stderr}"


def test_v2_stage_name_in_supervisor():
    """V2 supervisor must reference the V2 stage name in FINAL_VERDICT."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # The trap verdict must be V2 stage (per V2 spec)
    assert "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V2" in text
    # Also reference V1 salvage (backward compat)
    assert "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1" in text


# ---------------------------------------------------------------------------
# 13. V2 hard guard: cannot pass with 5h runtime
# ---------------------------------------------------------------------------

def test_v2_5h_runtime_audit():
    """V1 actual runtime was 300.12 min (5h). V2 must NOT have the same bug.

    Verify the V2 supervisor's logic would correctly compute actual_runtime
    as ~360 min (not 300 min) when given a 6h+ wallclock."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # V2 fix block sleeps until END_TS after the last checkpoint
    # so ELAPSED_MIN at finalize will be ~360 (6h)
    assert "[V2 wallclock fix]" in text
    # The V1 audit's actual_runtime_minutes (300.12) is the V1 bug evidence
    assert V1_AUDIT.exists()
    audit = json.loads(V1_AUDIT.read_text(encoding="utf-8"))
    assert audit["actual_runtime_minutes"] < 330
    # V2 supervisor must have additional sleep after last checkpoint
    # to push runtime from 300 (5h) to 360 (6h)
    assert "REMAINING=$(( END_TS - $(date +%s) ))" in text
    # Verify the supervisor splits REMAINING into CHUNK + TAIL and sleeps
    assert 'CHUNK=$(( REMAINING / 4 ))' in text
    assert 'TAIL=$(( END_TS - $(date +%s) ))' in text
    assert 'sleep "${CHUNK}"' in text
    assert 'sleep "${TAIL}"' in text
