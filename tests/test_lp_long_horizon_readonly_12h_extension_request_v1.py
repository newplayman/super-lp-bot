"""Tests for LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1.

These tests verify:
  - Approval phrase is exactly the 12h phrase (sha256 match)
  - Wrong stage rejected by supervisor preflight
  - Real pool universe required (no smoke placeholder)
  - 12h supervisor does not auto-advance to 24h
  - Locked fields: can_run_probe_now=false, tiny_canary_allowed="no", etc.
  - No wallet/keypair/signer in any 12h output
  - No tx send (forbidden process check)
  - Final verdict allowed next stages only (5-set)
  - V2 6h data not modified
  - V2 6h corrected verdict not modified

All tests are read-only; they do NOT touch any 6h or 12h data.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = ROOT / "reports" / "lp_long_horizon_readonly_continuous_12h_extension" / "20260605_082120"
V2_FINAL_VERDICT = ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260605_043726" / "FINAL_VERDICT.json"
V2_DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260605_043726"
V2_CORRECTED = ROOT / "reports" / "lp_long_horizon_6h_finalizer_rebuild" / "20260605_043726" / "CORRECTED_FINAL_VERDICT.json"
SUPERVISOR_SCRIPT = ROOT / "scripts" / "run_lp_long_horizon_readonly_stage_once.sh"
NODE_REPORT_GENERATOR = ROOT / "scripts" / "lp_long_horizon_node_report_generator_v1.py"

EXPECTED_APPROVAL_TEXT = "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true"
EXPECTED_APPROVAL_SHA256 = "040c37f3bc32bc3fe281eb4cf181fae4634e742e78c769d2211d3a5f8802198f"

ALLOWED_NEXT_STAGES_12H = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT",
    "LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
}

# Snapshot of V2 final verdict MD5 BEFORE tests run
_EXPECTED_V2_FINAL_VERDICT_MD5 = "8dee718af852c9cadcd515e852f8642d"


# ---------------------------------------------------------------------------
# Stage A: input evidence audit
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (EXTENSION_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (EXTENSION_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_audit_key_assertions() -> None:
    audit = json.loads((EXTENSION_DIR / "input_evidence_audit.json").read_text())
    assert audit["key_assertions"]["6h_corrected_gate_pass"] is True
    assert audit["key_assertions"]["6h_corrected_runtime_valid"] is True
    assert audit["key_assertions"]["6h_pool_universe_was_placeholder"] is True
    assert audit["key_assertions"]["12h_must_use_real_pool_universe"] is True
    assert audit["key_assertions"]["no_auto_24h"] is True


# ---------------------------------------------------------------------------
# Stage B: 12h approval record
# ---------------------------------------------------------------------------

def test_b_12h_approval_record_files_exist() -> None:
    assert (EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED.json").exists()
    assert (EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED_CN.md").exists()


def test_b_12h_approval_phrase_exact() -> None:
    rec = json.loads((EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED.json").read_text())
    assert rec["user_approval_text"] == EXPECTED_APPROVAL_TEXT


def test_b_12h_approval_sha256_match() -> None:
    rec = json.loads((EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED.json").read_text())
    assert rec["user_approval_text_hash_sha256"] == EXPECTED_APPROVAL_SHA256


def test_b_12h_approved_stage_is_12h() -> None:
    rec = json.loads((EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED.json").read_text())
    assert rec["approved_stage"] == "12h"
    assert rec["mode"] == "readonly"
    assert rec["no_probe"] is True
    assert rec["auto_advance_allowed"] is False
    assert rec["approved_next_stages"] == []  # no forward approval


def test_b_12h_locked_fields() -> None:
    rec = json.loads((EXTENSION_DIR / "MANUAL_APPROVAL_RECORDED.json").read_text())
    # can_run_probe_now and tiny_canary_allowed live in no_touch_invariants block
    assert rec["no_touch_invariants"]["can_run_probe_now"] is False
    assert rec["no_touch_invariants"]["tiny_canary_allowed"] == "no"
    assert rec["no_touch_invariants"]["no_auto_24h"] is True


# ---------------------------------------------------------------------------
# Stage C: real pool universe (no placeholder)
# ---------------------------------------------------------------------------

def test_c_real_pool_universe_files_exist() -> None:
    assert (EXTENSION_DIR / "real_pool_universe_for_12h.json").exists()
    assert (EXTENSION_DIR / "real_pool_universe_for_12h.csv").exists()
    assert (EXTENSION_DIR / "REAL_POOL_UNIVERSE_FOR_12H_CN.md").exists()


def test_c_real_pool_universe_no_placeholder() -> None:
    universe = json.loads((EXTENSION_DIR / "real_pool_universe_for_12h.json").read_text())
    assert universe["real_pool_universe_used"] is True
    assert universe["all_pools_are_real_on_chain"] is True
    assert universe["placeholder_pool_count"] == 0
    assert universe["selected_real_pool_count"] >= 30


def test_c_no_smoke_placeholder_in_csv() -> None:
    csv_text = (EXTENSION_DIR / "real_pool_universe_for_12h.csv").read_text()
    assert "<smoke_pool" not in csv_text


def test_c_per_protocol_min_counts() -> None:
    universe = json.loads((EXTENSION_DIR / "real_pool_universe_for_12h.json").read_text())
    c = universe["per_protocol_counts"]
    # At least 1 orca clmm, 5 stable, 10 raydium_clmm, 10 raydium_cpmm
    assert c["solana_orca_whirlpool_clmm"] >= 1
    assert c["solana_stable_total"] >= 5
    assert c["solana_raydium_clmm"] >= 10
    assert c["solana_raydium_cpmm"] >= 10


def test_c_all_pools_have_real_address() -> None:
    universe = json.loads((EXTENSION_DIR / "real_pool_universe_for_12h.json").read_text())
    for p in universe["pools"]:
        # Solana base58 addresses are 32-44 chars
        assert 32 <= len(p["pool_address"]) <= 44
        assert p["chain"] == "solana"


# ---------------------------------------------------------------------------
# Stage D: 12h run config frozen
# ---------------------------------------------------------------------------

def test_d_12h_run_config_files_exist() -> None:
    assert (EXTENSION_DIR / "twelve_hour_run_config.json").exists()
    assert (EXTENSION_DIR / "TWELVE_HOUR_RUN_CONFIG_CN.md").exists()


def test_d_12h_duration_hours_12() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    assert cfg["duration_hours"] == 12
    assert cfg["loop_count"] == 12
    assert cfg["sleep_seconds_per_iteration"] == 3600


def test_d_12h_no_auto_advance() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    assert cfg["auto_advance_to_24h"] is False
    assert cfg["auto_advance_to_48h"] is False
    assert cfg["auto_advance_to_72h"] is False
    assert cfg["auto_advance_to_7d"] is False
    assert cfg["manual_approval_required_for_24h"] is True


def test_d_12h_no_probe_no_wallet_no_tx() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    assert cfg["no_probe"] is True
    assert cfg["no_canary"] is True
    assert cfg["no_live"] is True
    assert cfg["no_paper"] is True
    assert cfg["no_wallet"] is True
    assert cfg["no_keypair"] is True
    assert cfg["no_signer"] is True
    assert cfg["no_tx"] is True
    assert cfg["no_approve"] is True
    assert cfg["no_mint"] is True
    assert cfg["no_bridge"] is True
    assert cfg["no_add_liquidity"] is True
    assert cfg["no_remove_liquidity"] is True
    assert cfg["no_collect"] is True
    assert cfg["no_swap"] is True
    assert cfg["no_production_write"] is True
    assert cfg["no_shadow_overwrite"] is True
    assert cfg["paid_rpc"] is False
    assert cfg["paid_indexer"] is False


def test_d_12h_abort_conditions_present() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    assert "consecutive_429_streak_gte_5" in cfg["abort_conditions"]
    assert "error_rate_pct_gt_20" in cfg["abort_conditions"]
    assert "write_failure" in cfg["abort_conditions"]
    assert "safety_self_check_fail" in cfg["abort_conditions"]
    assert "forbidden_token_detected" in cfg["abort_conditions"]
    assert "disk_threshold_breach" in cfg["abort_conditions"]
    assert "duplicate_collector_process" in cfg["abort_conditions"]


# ---------------------------------------------------------------------------
# Stage E: 12h supervisor script + tests
# ---------------------------------------------------------------------------

def test_e_12h_supervisor_script_exists() -> None:
    assert SUPERVISOR_SCRIPT.exists()
    assert SUPERVISOR_SCRIPT.is_file()


def test_e_12h_supervisor_syntax() -> None:
    rc = subprocess.run(
        ["bash", "-n", str(SUPERVISOR_SCRIPT)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, f"supervisor syntax error: {rc.stderr}"


def test_e_12h_supervisor_uses_real_pool_universe() -> None:
    text = SUPERVISOR_SCRIPT.read_text()
    # Verify it checks for <smoke_pool placeholder and rejects
    assert "<smoke_pool" in text  # in the rejection check
    assert "real_pool_universe_used" in text
    assert "all_pools_are_real_on_chain" in text
    assert "placeholder_pool_count" in text


def test_e_12h_supervisor_no_auto_advance() -> None:
    text = SUPERVISOR_SCRIPT.read_text()
    assert "auto_advance_to_next" in text
    # auto_advance_to_next: False (Python boolean) OR "False" string
    assert ("auto_advance_to_next\": False" in text) or ("auto_advance_to_next: False" in text) or ("auto_advance_to_next\":False" in text)
    # can_advance_to_next: False
    assert ("can_advance_to_next\": False" in text) or ("can_advance_to_next: False" in text) or ("can_advance_to_next\":False" in text)


def test_e_12h_supervisor_fail_safe_trap() -> None:
    text = SUPERVISOR_SCRIPT.read_text()
    assert "write_fail_verdict_on_trap" in text
    assert ".finalize_succeeded" in text
    assert "CORRECTED_FINAL_VERDICT_FALLBACK.json" in text
    # Trap on multiple signals
    assert "SIGTERM" in text
    assert "SIGINT" in text
    assert "SIGHUP" in text


# ---------------------------------------------------------------------------
# Stage F/G: pre-run safety (deferred — but verify config files exist)
# ---------------------------------------------------------------------------

def test_f_no_existing_lp_long_horizon_tmux() -> None:
    """No V2 6h tmux, no staged_observation tmux, no 12h tmux yet."""
    rc = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
    for forbidden in ("lp_long_horizon_6h_v2", "lp_long_horizon_12h_20260505_082120", "staged_observation", "node_report"):
        assert forbidden not in rc.stdout


def test_f_no_forbidden_process_running() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_f_v2_data_dir_intact() -> None:
    files = [f for f in V2_DATA_DIR.rglob("*") if f.is_file()]
    assert len(files) == 42


def test_f_v2_final_verdict_unchanged_md5() -> None:
    import hashlib
    h = hashlib.md5(V2_FINAL_VERDICT.read_bytes()).hexdigest()
    assert h == _EXPECTED_V2_FINAL_VERDICT_MD5


def test_f_v2_corrected_verdict_exists() -> None:
    assert V2_CORRECTED.exists()
    fv = json.loads(V2_CORRECTED.read_text())
    assert fv["gate_pass"] is True


# ---------------------------------------------------------------------------
# Stage I: FINAL_VERDICT allowed next stages only
# ---------------------------------------------------------------------------

def test_i_allowed_next_stages_match() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    listed = set(cfg["allowed_next_stages_locked"])
    assert listed == ALLOWED_NEXT_STAGES_12H


def test_i_forbidden_next_stages_explicit() -> None:
    cfg = json.loads((EXTENSION_DIR / "twelve_hour_run_config.json").read_text())
    assert "any probe / canary / live / paper / wallet / keypair stage" in cfg["forbidden_next_stages"]


# ---------------------------------------------------------------------------
# Secret scan
# ---------------------------------------------------------------------------

def test_k_no_secret_value_in_extension_outputs() -> None:
    """No real secret values in the extension report files.

    Whitelist: the 12h approval phrase sha256 (which is a hash, not a secret).
    """
    # 12h approval phrase sha256 (per MANUAL_APPROVAL_RECORDED.json) — this is a hash, not a secret
    WHITELIST_HEX_64 = {EXPECTED_APPROVAL_SHA256}

    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
        re.compile(r'\b[0-9a-fA-F]{64,}\b'),
    ]
    for p in EXTENSION_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    matched_value = m.group(0)
                    # Allow if it's a whitelisted hash (not a real secret)
                    if any(wh in matched_value for wh in WHITELIST_HEX_64):
                        continue
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {matched_value[:80]}")
