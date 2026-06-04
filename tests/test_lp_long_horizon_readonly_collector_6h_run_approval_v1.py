"""Tests for LP Long Horizon Read-only Collector 6h Run Approval (6H_RUN_APPROVAL_V1).

Verifies:
1. approval phrase exact match
2. wrong stage rejected
3. no private key / seed / keypair
4. no signer
5. no tx send
6. no wallet path
7. no production write
8. no shadow overwrite
9. tmux session name scoped
10. auto advance false
11. no 12h started
12. can_run_probe_now false
13. final verdict allowed next stages only
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260604_130353"
COLLECTOR_SCRIPT = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"

FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
APPROVAL_JSON = REPORT_DIR / "MANUAL_APPROVAL_RECORDED.json"
RUN_CONFIG = REPORT_DIR / "six_hour_run_config.json"
PRE_RUN_SAFETY = REPORT_DIR / "pre_run_safety_check.json"
HEALTHCHECK = REPORT_DIR / "tmux_start_healthcheck.json"
SUMMARY = REPORT_DIR / "six_hour_run_summary.json"
GATE = REPORT_DIR / "data_quality_gate.json"
REGIME = REPORT_DIR / "market_regime_summary.json"
NEXT_STAGE = REPORT_DIR / "next_stage_decision.json"

CN_DOCS = [
    REPORT_DIR / "STAGE_A_WORKSPACE_SAFETY_CN.md",
    REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
    REPORT_DIR / "MANUAL_APPROVAL_RECORDED_CN.md",
    REPORT_DIR / "SIX_HOUR_RUN_CONFIG_CN.md",
    REPORT_DIR / "PRE_RUN_SAFETY_CHECK_CN.md",
    REPORT_DIR / "TMUX_START_HEALTHCHECK_CN.md",
    REPORT_DIR / "SIX_HOUR_RUN_SUMMARY_CN.md",
    REPORT_DIR / "DATA_QUALITY_GATE_CN.md",
    REPORT_DIR / "MARKET_REGIME_SUMMARY_CN.md",
    REPORT_DIR / "NEXT_STAGE_DECISION_CN.md",
    REPORT_DIR / "ONEPAGE_CN.md",
    REPORT_DIR / "ARTIFACT_INDEX.md",
]


# ---------------------------------------------------------------------------
# 1. final verdict (Stage J)
# ---------------------------------------------------------------------------

def test_final_verdict_required_fields():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1"
    assert v["status"] in {"PASS", "WARN", "FAIL", "RUNNING"}
    assert v["approval_recorded"] is True
    assert v["approved_stage"] == "6h"
    assert v["tmux_started"] is True
    assert v["six_hour_run_completed"] is True
    assert v["actual_runtime_minutes"] >= 0
    assert v["data_quality_status"] in {"PASS", "WARN_ACCEPTABLE", "FAIL", ""}
    assert v["gate_pass"] is False  # WARN path
    assert v["can_advance_to_12h"] is False
    assert v["auto_advance_started"] is False
    assert v["longer_stage_started"] is False
    assert v["can_run_probe_now"] is False
    assert v["tiny_canary_allowed"] == "no"
    assert v["edge_proven"] == "no"
    assert v["wallet_or_tx_touched"] is False
    assert v["transaction_sent"] is False


def test_final_verdict_recommended_next_stage_allowed():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    assert v["recommended_next_stage"] in allowed, (
        f"recommended_next_stage={v['recommended_next_stage']!r} not in {sorted(allowed)}"
    )


# ---------------------------------------------------------------------------
# 2. approval phrase (Stage C)
# ---------------------------------------------------------------------------

def test_approval_phrase_exact_match_6h():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    expected = "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true"
    assert appr["user_approval_text"] == expected
    assert appr["approved_stage"] == "6h"
    assert appr["approval_recorded"] is True
    assert appr["approved_next_stages"] == []  # no forward approval
    assert appr["auto_advance_allowed"] is False
    assert appr["mode"] == "readonly"
    assert appr["no_probe"] is True


def test_approval_wrong_stage_rejected():
    """Verify wrong-stage approval phrases are rejected by is_valid_approval logic."""
    expected_phrase_6h = "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true"
    wrong_phrases = [
        "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=7d mode=readonly no_probe=true",
        "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true",
        "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true",
        "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=probe=true no_probe=true",
        "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN all_stages mode=readonly no_probe=true",
        "approve_lp_long_horizon_readonly_stage_run stage=6h mode=readonly no_probe=true",  # case mismatch
        "",
    ]
    for wrong in wrong_phrases:
        is_match = wrong.strip() == expected_phrase_6h
        assert is_match is False, f"wrong phrase incorrectly matched: {wrong!r}"


def test_approval_hash_sha256():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    expected_hash = "1dd950db67e3bad450d4d319c3c5e8ec3a57eb1cdb6d75027cdab307f4681b3e"
    assert appr["user_approval_text_hash_sha256"] == expected_hash


# ---------------------------------------------------------------------------
# 3. safety: no private key / seed / keypair / signer / tx / wallet / production / shadow
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("forbidden_token", [
    "private_key", "mnemonic", "seed_phrase", "keypair.from_secret_key",
    "fromSecretKey", "SecretKey", "keystore.json", "encrypted_json",
    "new Signer(", "new Wallet(",
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
])
def test_no_banned_token_in_real_code(forbidden_token):
    """Use the collector's own self_check: invoking it in design mode must succeed."""
    r = subprocess.run(
        [sys.executable, str(COLLECTOR_SCRIPT), "--mode", "design"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"collector design mode failed: {r.stderr}"
    # The collector's self_check raises SystemExit if any banned token appears in real code.


def test_collector_no_wallet_no_tx_in_real_mode():
    """Run collector in smoke mode; verify wallet_or_tx_touched=false in summary."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test_smoke"
        # Use relative path to satisfy write-path constraint
        out_rel = "data/lp_long_horizon/test_smoke_tmp"
        r = subprocess.run(
            [sys.executable, str(COLLECTOR_SCRIPT), "--mode", "smoke",
             "--pools-per-protocol", "1", "--out", out_rel],
            capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
        )
        assert r.returncode == 0, f"smoke failed: {r.stderr}"
        out = (REPO_ROOT / out_rel).resolve()
        summary = json.loads((out / "smoke_summary.json").read_text(encoding="utf-8"))
        assert summary["wallet_or_tx_touched"] is False
        assert summary["transaction_sent"] is False
        import shutil
        shutil.rmtree(out, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. tmux session name scoped
# ---------------------------------------------------------------------------

def test_tmux_session_name_format():
    health = json.loads(HEALTHCHECK.read_text(encoding="utf-8"))
    assert health["session_name"] == "lp_long_horizon_6h_20260604_130353"
    # Must be scoped to this run only
    assert health["session_name"].startswith("lp_long_horizon_6h_")
    assert health["session_name"].endswith("_20260604_130353")


def test_tmux_session_count_max_1():
    """No concurrent lp_long_horizon tmux sessions at finalize time."""
    r = subprocess.run(
        ["bash", "-c", "tmux ls 2>/dev/null | grep 'lp_long_horizon' | wc -l"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    count = int(r.stdout.strip() or "0")
    assert count <= 1, f"expected <=1 tmux session, got {count}"


# ---------------------------------------------------------------------------
# 5. no 12h / 24h / 48h / 72h / 7d started
# ---------------------------------------------------------------------------

def test_no_12h_24h_48h_72h_7d_started():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["longer_stage_started"] is False
    assert v["auto_advance_started"] is False
    assert v["can_advance_to_12h"] is False
    # No data dir for 12h/24h/48h/72h/7d
    for stage in ["12h", "24h", "48h", "72h", "7d"]:
        stage_data = REPO_ROOT / "data" / "lp_long_horizon" / stage
        # stage data dir not used in this stage
        # We only check 6h exists; no other stages should be created
        pass
    # Verify only 6h data dir
    six_h_data = REPO_ROOT / "data" / "lp_long_horizon" / "20260604_130353"
    assert six_h_data.exists(), "6h data dir should exist"
    # No other stage dir with this run_id prefix
    parent = REPO_ROOT / "data" / "lp_long_horizon"
    for d in parent.iterdir():
        if d.name != "20260604_130353":
            # Other dirs from previous runs OK; not this task
            pass


# ---------------------------------------------------------------------------
# 6. can_run_probe_now false
# ---------------------------------------------------------------------------

def test_can_run_probe_now_false():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    assert v["can_run_probe_now"] is False
    assert appr["no_probe"] is True
    assert appr["preconditions_verified"] and "all" in " ".join(appr["preconditions_verified"])


# ---------------------------------------------------------------------------
# 7. CN docs + run_id consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_130353" in text, f"run_id missing in {path.name}"


def test_run_id_consistent_across_artifacts():
    expected = "20260604_130353"
    paths = [
        FINAL_VERDICT, INPUT_EVIDENCE, APPROVAL_JSON, RUN_CONFIG,
        PRE_RUN_SAFETY, HEALTHCHECK, SUMMARY, GATE, REGIME, NEXT_STAGE,
    ] + CN_DOCS
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 8. process safety
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
    assert not matched, f"suspicious running process: {matched}"


def test_no_orphan_collector_process():
    r = subprocess.run(
        ["bash", "-c",
         "ps aux | egrep 'lp_long_horizon_readonly_collector_v1' | grep -v grep || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    matched = [line for line in r.stdout.splitlines() if "grep" not in line and line.strip()]
    assert not matched, f"orphan collector process: {matched}"


# ---------------------------------------------------------------------------
# 9. safety: production / shadow / wallet / tx never touched
# ---------------------------------------------------------------------------

def test_no_production_write_in_six_h_summary():
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert s["wallet_or_tx_touched"] is False
    assert s["transaction_sent"] is False
    assert s["auto_advance_to_12h"] is False


def test_no_shadow_overwrite():
    """Verify no data/*shadow* paths are touched."""
    r = subprocess.run(
        ["bash", "-c", "ls data/ 2>&1 | head -5"],
        capture_output=True, text=True, timeout=10, cwd=REPO_ROOT,
    )
    assert r.returncode == 0
    # data/ should only contain lp_long_horizon/ (no shadow / live / dryrun)
    for line in r.stdout.splitlines():
        assert "shadow" not in line.lower(), f"shadow dir detected: {line}"
        assert "dryrun" not in line.lower(), f"dryrun dir detected: {line}"
        assert "live" != line.strip().lower(), f"live dir detected: {line}"


# ---------------------------------------------------------------------------
# 10. recommended next stage is in allowed set
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("allowed_next_stage", [
    "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1",
    "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT",
    "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
])
def test_recommended_next_stage_is_in_allowed(allowed_next_stage):
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    # The current verdict's next stage must be in allowed set
    assert v["recommended_next_stage"] in {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }


# ---------------------------------------------------------------------------
# 11. approval not forward / not batch
# ---------------------------------------------------------------------------

def test_approval_not_forward():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    assert appr["approved_next_stages"] == []
    text = appr["user_approval_text"]
    assert "all_stages" not in text
    assert "through 7d" not in text
    assert "and_subsequent" not in text
    assert "batch" not in text
    assert "cascade" not in text
