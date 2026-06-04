"""Tests for LP Long Horizon Read-only Collector 6h Real Wallclock Fix Repeat.

Verifies (per task spec stage J):
1. short mode rejected as valid 6h
2. actual_runtime_minutes >=330 required
3. no auto advance to 12h
4. no private key / seed / keypair
5. no signer
6. no tx send
7. no wallet path
8. no production write
9. no shadow overwrite
10. tmux session scoped
11. can_run_probe_now false
12. final verdict allowed next stages only
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_fix" / "20260604_134918"
SIX_H_REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260604_134918"
COLLECTOR_SCRIPT = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"
SUPERVISOR_SCRIPT = REPO_ROOT / "scripts" / "run_lp_long_horizon_readonly_6h_once.sh"

PREV_AUDIT = REPORT_DIR / "previous_6h_invalid_audit.json"
APPROVAL_JSON = REPORT_DIR / "MANUAL_APPROVAL_RECORDED.json"
CONFIG_JSON = REPORT_DIR / "six_hour_real_wallclock_config.json"
PRE_RUN_SAFETY = REPORT_DIR / "pre_run_safety_check.json"
HEALTHCHECK = REPORT_DIR / "tmux_start_healthcheck.json"
INTERIM_STATUS = REPORT_DIR / "STAGE_H_INTERIM_STATUS_CN.md"

CN_DOCS = [
    REPORT_DIR / "PREVIOUS_6H_INVALID_AUDIT_CN.md",
    REPORT_DIR / "STAGE_B_WORKSPACE_SAFETY_CN.md",
    REPORT_DIR / "MANUAL_APPROVAL_RECORDED_CN.md",
    REPORT_DIR / "SIX_HOUR_REAL_WALLCLOCK_CONFIG_CN.md",
    REPORT_DIR / "SUPERVISOR_SCRIPT_IMPL_CN.md",
    REPORT_DIR / "PRE_RUN_SAFETY_CHECK_CN.md",
    REPORT_DIR / "TMUX_START_HEALTHCHECK_CN.md",
    REPORT_DIR / "STAGE_H_INTERIM_STATUS_CN.md",
]


def _strip_banned_list_and_comments(text: str) -> str:
    """Strip heredoc / echos / comments / egrep patterns from supervisor text before banned-token check.

    The supervisor contains banned tokens as literal strings inside ps-aux preflight checks
    (e.g. `egrep 'canary|live|sendTransaction|eth_sendRawTransaction|...'`). These are
    SEARCH PATTERNS, not call sites. We strip them so the banned-token assertion only fires
    on actual code-level invocations.
    """
    # 1. Strip line comments
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

    # 2. Strip egrep / grep search patterns — these are preflight check strings,
    # NOT call sites. They are wrapped in single quotes after egrep/grep.
    text = re.sub(r"egrep\s+'[^']*'", "egrep '<stripped>'", text)
    text = re.sub(r"grep\s+'[^']*'", "grep '<stripped>'", text)
    text = re.sub(r"egrep\s+\"[^\"]*\"", "egrep \"<stripped>\"", text)
    text = re.sub(r"grep\s+\"[^\"]*\"", "grep \"<stripped>\"", text)

    return text


# ---------------------------------------------------------------------------
# 1. short mode rejected as valid 6h
# ---------------------------------------------------------------------------

def test_short_mode_rejected_by_supervisor():
    """Verify the supervisor script hard-rejects short mode (SLEEP_SECONDS < 3600)."""
    result = subprocess.run(
        ["bash", "-c",
         "SLEEP_SECONDS=10 LOOP_COUNT=6 bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260604_134918"],
        capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
    )
    combined = (result.stdout + result.stderr).lower()
    assert "refused" in combined, f"short mode not rejected: {result.stdout!r} {result.stderr!r}"
    assert "short mode forbidden" in combined
    assert "sleep_seconds=10 < 3600" in combined
    assert result.returncode != 0, f"short mode not rejected (rc={result.returncode})"


def test_loop_count_override_rejected_by_supervisor():
    result = subprocess.run(
        ["bash", "-c",
         "SLEEP_SECONDS=3600 LOOP_COUNT=10 bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260604_134918"],
        capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
    )
    combined = (result.stdout + result.stderr).lower()
    assert "refused" in combined
    assert "override forbidden" in combined
    assert "loop_count=10 != 6" in combined
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# 2. actual_runtime_minutes >=330 required
# ---------------------------------------------------------------------------

def test_min_runtime_threshold_330():
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    assert config["min_valid_runtime_minutes"] == 330
    assert config["duration_hours"] == 6
    short = config["CRITICAL_short_mode_constraints"]
    assert short["short_mode_allowed"] is False
    assert short["loop_sleep_override_allowed"] is False
    assert short["min_sleep_seconds_per_iteration"] == 3600
    assert short["min_actual_runtime_minutes"] == 330


def test_gate_pass_conditions_include_runtime_330():
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    assert config["gate_pass_conditions"]["actual_runtime_minutes"] == ">= 330"


def test_supervisor_aborts_on_short_runtime():
    """The supervisor should gate-validate `actual_runtime < 330` as FAIL."""
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    # The runtime gate is `if [ "${ELAPSED_MIN}" -lt 330 ]; then echo FAIL...`
    assert '"${ELAPSED_MIN}" -lt 330' in text
    assert "REAL_6H_GATE_PASS=false" in text
    assert "GATE_DECISION=\"FAIL\"" in text


# ---------------------------------------------------------------------------
# 3. no auto advance to 12h
# ---------------------------------------------------------------------------

def test_no_auto_advance_to_12h():
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    assert config["auto_advance_to_12h"] is False
    # Even on PASS, recommended_next_stage is 12H_RUN_APPROVAL_V1 (not auto-advance)


def test_approval_not_forward():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    assert appr["approved_next_stages"] == []
    text = appr["user_approval_text"]
    assert "all_stages" not in text
    assert "through 7d" not in text
    assert "and_subsequent" not in text
    assert "batch" not in text


# ---------------------------------------------------------------------------
# 4. no private key / seed / keypair (collector self_check)
# ---------------------------------------------------------------------------

def test_collector_no_banned_token_in_real_code():
    result = subprocess.run(
        [sys.executable, str(COLLECTOR_SCRIPT), "--mode", "design"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "SAFETY GUARD" not in result.stderr


def test_supervisor_no_banned_token_in_real_code():
    """The supervisor (bash) must not call any banned API. Strip comments + echos first."""
    raw = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    text = _strip_banned_list_and_comments(raw)
    # The supervisor must NEVER actually call any of these. We strip the banned-list
    # enum (which is just a list of names, not calls).
    banned_calls = [
        "private_key=",  # python kwarg
        '"new Signer("',
        '"new Wallet("',
        '"sendTransaction("',
        '"eth_sendRawTransaction"',
        '"eth_sendTransaction"',
        '"signTransaction("',
        '"signAndSendTransaction("',
        '"add_liquidity("',
        '"remove_liquidity("',
        '"collect_fee("',
        '"collect("',
        '"mint("',
        '"approve("',
        '"burn("',
        '"transfer("',
    ]
    for token in banned_calls:
        assert token not in text, f"banned call {token!r} found in supervisor script"


# ---------------------------------------------------------------------------
# 5. no signer / no tx send
# ---------------------------------------------------------------------------

def test_no_signer_no_tx_in_supervisor():
    raw = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    text = _strip_banned_list_and_comments(raw)
    # The supervisor must not actually create Signer / Wallet
    assert "new Signer" not in text
    assert "new Wallet" not in text
    # tx send methods (as actual calls, not references)
    assert "sendTransaction(" not in text
    assert "eth_sendRawTransaction" not in text
    assert "eth_sendTransaction" not in text
    assert "signTransaction(" not in text


# ---------------------------------------------------------------------------
# 6. no wallet path
# ---------------------------------------------------------------------------

def test_no_wallet_path_in_supervisor():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "keystore.json" not in text
    assert "encrypted_json" not in text


# ---------------------------------------------------------------------------
# 7. no production write
# ---------------------------------------------------------------------------

def test_no_production_write_path():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    bad_paths = ["data/dryrun", "data/shadow", "data/live", "migrations/", "/cmd/lpbot", "internal/adapters"]
    for bad in bad_paths:
        assert bad not in text, f"production-like path {bad!r} found in supervisor"


# ---------------------------------------------------------------------------
# 8. no shadow overwrite
# ---------------------------------------------------------------------------

def test_no_shadow_overwrite():
    text = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    assert "data/lp_long_horizon/shadow" not in text
    assert "data/lp_long_horizon/live" not in text
    # The only data path is data/lp_long_horizon/${RUN_ID}
    assert "data/lp_long_horizon/${RUN_ID}" in text
    # Only report path is reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}
    assert "reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}" in text


# ---------------------------------------------------------------------------
# 9. tmux session scoped
# ---------------------------------------------------------------------------

def test_tmux_session_name_scoped_to_run_id():
    health = json.loads(HEALTHCHECK.read_text(encoding="utf-8"))
    assert health["session_name"] == "lp_long_horizon_6h_20260604_134918"
    assert health["session_name"].startswith("lp_long_horizon_6h_")
    assert health["session_name"].endswith("_20260604_134918")


def test_tmux_session_count_max_1():
    r = subprocess.run(
        ["bash", "-c", "tmux ls 2>/dev/null | grep 'lp_long_horizon_6h' | wc -l"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    count = int(r.stdout.strip() or "0")
    assert count <= 1, f"expected <=1 tmux session, got {count}"


# ---------------------------------------------------------------------------
# 10. can_run_probe_now false
# ---------------------------------------------------------------------------

def test_can_run_probe_now_false():
    """can_run_probe_now + tiny_canary_allowed must stay false / no.

    These live in the post-launch healthcheck snapshot (the runtime gate that the
    supervisor will keep asserting every checkpoint), and as named assertions in the
    approval record. The pre-launch config asserts no_probe=True + auto_advance=False
    which transitively gates them.
    """
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    health = json.loads(HEALTHCHECK.read_text(encoding="utf-8"))

    # Top-level config: no_probe is the pre-launch gate
    assert config["no_probe"] is True
    assert config["auto_advance_to_12h"] is False

    # Approval
    assert appr["no_probe"] is True
    assert appr["approved_next_stages"] == []
    # The preconditions_verified list explicitly names the assertions that must hold
    pre = appr.get("preconditions_verified", [])
    assert "can_run_probe_now_still_false" in pre
    assert "tiny_canary_allowed_still_no" in pre
    # forward_approval_check: only 6h approved; 12h/24h/48h/72h/7d explicitly NOT approved
    fac = appr.get("forward_approval_check", {})
    assert fac.get("approved_stages") == ["6h"]
    assert "12h" in fac.get("NOT_approved_stages", [])

    # safety_21_fields: relevant safety primitives
    s21 = config["safety_21_fields"]
    assert s21["touched_trading_path"] is False
    assert s21["wallet_or_tx_touched"] is False
    assert s21["transaction_sent"] is False
    assert s21["send_hard_disable_still_active"] is True
    assert s21["no_auto_advance"] is True
    assert s21["no_12h_24h_48h_72h_7d_run"] is True
    assert s21["no_actual_daemon"] is True

    # HEALTHCHECK (post-launch runtime gate values) — these MUST stay false / no
    hc_safety = health["safety_check"]
    assert hc_safety["can_run_probe_now"] is False
    assert hc_safety["tiny_canary_allowed"] == "no"
    assert hc_safety["short_mode_rejected"] is True
    assert hc_safety["no_canary_live_paper"] is True
    assert hc_safety["no_wallet_keypair_signer"] is True
    assert hc_safety["no_sendTransaction"] is True
    assert hc_safety["no_production_write"] is True
    assert hc_safety["no_shadow_overwrite"] is True
    assert hc_safety["no_daemon"] is True
    assert hc_safety["no_extra_tmux_session"] is True


# ---------------------------------------------------------------------------
# 11. previous 6h audit
# ---------------------------------------------------------------------------

def test_previous_6h_audit_short_mode():
    prev = json.loads(PREV_AUDIT.read_text(encoding="utf-8"))
    assert prev["previous_actual_runtime_minutes"] < 330
    assert prev["previous_short_mode_used"] is True
    assert prev["previous_gate_valid_for_12h"] is False
    assert prev["previous_should_not_advance_to_12h"] is True


# ---------------------------------------------------------------------------
# 12. CN docs + run_id consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_134918" in text, f"run_id missing in {path.name}"


def test_run_id_consistent_across_artifacts():
    expected = "20260404_134918"  # typo bait
    # Actually: must be 20260604_134918
    expected = "20260604_134918"
    paths = [PREV_AUDIT, APPROVAL_JSON, CONFIG_JSON, PRE_RUN_SAFETY, HEALTHCHECK]
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 13. process safety
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
    suspicious = [m for m in matched if any(b in m.lower() for b in ["canary", "lpbot-live", "paper", "sendtransaction", "eth_sendraw", "eth_sendtransaction", "keypair"])]
    assert not suspicious, f"suspicious running process: {suspicious}"


def test_supervisor_process_alive_or_completed():
    """Supervisor is either still running (6h in progress) or completed (FINAL_VERDICT exists)."""
    r = subprocess.run(
        ["bash", "-c",
         "ps -ef | grep -v grep | grep 'run_lp_long_horizon_readonly_6h_once.sh' | head -3 || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    matched = [line for line in r.stdout.splitlines() if line.strip()]
    final_verdict_exists = (SIX_H_REPORT_DIR / "FINAL_VERDICT.json").exists()
    if matched:
        # Supervisor still running
        for line in matched:
            assert "run_lp_long_horizon_readonly_6h_once.sh" in line
    else:
        # Supervisor must have completed and written FINAL_VERDICT
        assert final_verdict_exists, (
            "supervisor not running and FINAL_VERDICT.json missing; "
            "either supervisor died mid-run or finalize was skipped"
        )


# ---------------------------------------------------------------------------
# 14. final verdict allowed next stages only
# ---------------------------------------------------------------------------

def test_config_recommended_next_stage_set():
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    decision = config["gate_decision_to_recommended_next_stage"]
    # 3 gate outcomes map to 3 next stages
    assert decision["PASS"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1"
    assert decision["WARN_ACCEPTABLE"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT"
    assert decision["FAIL"] == "LP_LONG_HORIZON_READONLY_COLLECTOR FIX_REPEAT"
    # All 3 in task spec allowed set
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT",
        "LP_LONG_HORIZON_READONLY_COLLECTOR FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    for v in decision.values():
        assert v in allowed, f"{v!r} not in allowed {allowed}"


# ---------------------------------------------------------------------------
# 15. approval phrase hash matches
# ---------------------------------------------------------------------------

def test_approval_phrase_hash_sha256():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    expected_hash = "1dd950db67e3bad450d4d319c3c5e8ec3a57eb1cdb6d75027cdab307f4681b3e"
    assert appr["user_approval_text_hash_sha256"] == expected_hash


def test_approval_phrase_exact():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    expected = "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true"
    assert appr["user_approval_text"] == expected
    assert appr["approved_stage"] == "6h"
    assert appr["approval_recorded"] is True
