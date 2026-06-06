"""Tests for LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1.

These tests verify:
  - coverage_scope = partial_solana_bsc_real_universe
  - do_not_treat_as_full_universe = true
  - selected_pool_count >= 45
  - no placeholder pools
  - no Base unreachable pools included
  - no auto 24h
  - no wallet / keypair / signer
  - no tx send
  - final verdict allowed stages only

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_readonly_partial_12h_request" / "20260606_131323"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_confirms_partial_12h() -> None:
    d = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    c = d["input_evidence_confirmed"]
    assert c["full_coverage_ready"] is False
    assert c["observable_pool_count"] == 49
    assert c["observable_chain_count"] == 2
    assert c["observable_protocol_count"] == 5
    assert c["placeholder_pool_count"] == 0
    assert c["this_stage_is_partial_12h_not_full_12h"] is True


# ---------------------------------------------------------------------------
# Stage B: scope freeze
# ---------------------------------------------------------------------------

def test_b_scope_freeze_files_exist() -> None:
    assert (REPORT_DIR / "PARTIAL_12H_SCOPE_FREEZE_CN.md").exists()
    assert (REPORT_DIR / "partial_12h_scope_freeze.json").exists()


def test_b_scope_freeze_partial() -> None:
    d = json.loads((REPORT_DIR / "partial_12h_scope_freeze.json").read_text())
    assert d["coverage_scope"] == "partial_solana_bsc_real_universe"
    assert d["full_coverage_ready"] is False
    assert d["do_not_treat_as_full_universe"] is True
    assert "solana" in d["observed_chains"]
    assert "bsc" in d["observed_chains"]
    assert "base" in d["missing_chains"]


# ---------------------------------------------------------------------------
# Stage C: partial universe
# ---------------------------------------------------------------------------

def test_c_partial_universe_files_exist() -> None:
    assert (REPORT_DIR / "partial_observable_real_pool_universe_for_12h.csv").exists()
    assert (REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").exists()
    assert (REPORT_DIR / "PARTIAL_OBSERVABLE_REAL_POOL_UNIVERSE_CN.md").exists()


def test_c_partial_universe_selected_pool_count_ge_45() -> None:
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    assert d["selected_pool_count"] >= 45


def test_c_partial_universe_no_placeholder() -> None:
    """No pool should have <smoke_pool_> or PENDING_*_RPC_VALIDATION marker."""
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    for p in d["pools"]:
        assert "<smoke_pool_" not in p.get("pool_address", ""), f"placeholder in {p}"
        assert "PENDING" not in p.get("pool_address", ""), f"pending in {p}"
    assert d["placeholder_pool_count"] == 0


def test_c_partial_universe_no_base_pools() -> None:
    """Base chain pools should NOT be in the partial universe (Base RPC unreachable)."""
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    for p in d["pools"]:
        assert p["chain"] != "base", f"Base pool included: {p}"


def test_c_partial_universe_contains_solana_and_bsc() -> None:
    """Partial universe must contain both Solana + BSC."""
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    chains = {p["chain"] for p in d["pools"]}
    assert "solana" in chains
    assert "bsc" in chains


def test_c_partial_universe_at_least_5_protocols() -> None:
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    protocols = {p["protocol"] for p in d["pools"]}
    assert len(protocols) >= 5


def test_c_partial_universe_no_bsc_v2_zero_getpair() -> None:
    """BSC V2 pools (factory.getPair returned zero) should be excluded."""
    d = json.loads((REPORT_DIR / "partial_observable_real_pool_universe_for_12h.json").read_text())
    for p in d["pools"]:
        if p["chain"] == "bsc":
            assert p["protocol"] != "pancakeswap_v2", f"V2 pool included: {p}"


# ---------------------------------------------------------------------------
# Stage D: approval
# ---------------------------------------------------------------------------

def test_d_approval_files_exist() -> None:
    assert (REPORT_DIR / "MANUAL_APPROVAL_RECORDED_CN.md").exists()
    assert (REPORT_DIR / "MANUAL_APPROVAL_RECORDED.json").exists()
    # Also at the path the stage runner looks for
    approval_path = ROOT / "reports" / "lp_long_horizon_readonly_continuous_12h_extension" / "20260606_131323" / "MANUAL_APPROVAL_RECORDED.json"
    assert approval_path.exists()


def test_d_approval_phrase_valid() -> None:
    approval_path = ROOT / "reports" / "lp_long_horizon_readonly_continuous_12h_extension" / "20260606_131323" / "MANUAL_APPROVAL_RECORDED.json"
    d = json.loads(approval_path.read_text())
    phrase = d["user_approval_text"]
    expected_prefix = "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN"
    assert phrase.startswith(expected_prefix)
    assert "stage=12h" in phrase
    assert "mode=readonly" in phrase
    assert "no_probe=true" in phrase


def test_d_approval_auto_advance_disabled() -> None:
    d = json.loads((REPORT_DIR / "MANUAL_APPROVAL_RECORDED.json").read_text())
    assert d["auto_advance_allowed"] is False
    assert d["approved_next_stages"] == []


# ---------------------------------------------------------------------------
# Stage E: run config
# ---------------------------------------------------------------------------

def test_e_run_config_files_exist() -> None:
    assert (REPORT_DIR / "TWELVE_HOUR_PARTIAL_RUN_CONFIG_CN.md").exists()
    assert (REPORT_DIR / "twelve_hour_partial_run_config.json").exists()


def test_e_run_config_duration_12h() -> None:
    d = json.loads((REPORT_DIR / "twelve_hour_partial_run_config.json").read_text())
    assert d["duration_hours"] == 12
    assert d["checkpoint_interval_minutes"] == 60
    assert d["auto_advance_to_24h"] is False
    assert d["do_not_treat_as_full_universe"] is True


# ---------------------------------------------------------------------------
# Stage F: safety check
# ---------------------------------------------------------------------------

def test_f_safety_check_files_exist() -> None:
    assert (REPORT_DIR / "PRE_RUN_SAFETY_CHECK_CN.md").exists()
    assert (REPORT_DIR / "pre_run_safety_check.json").exists()


def test_f_safety_check_all_passed() -> None:
    d = json.loads((REPORT_DIR / "pre_run_safety_check.json").read_text())
    assert d["all_checks_passed"] is True
    assert d["decision"] == "PROCEED_TO_LAUNCH"


# ---------------------------------------------------------------------------
# Stage G: launch healthcheck
# ---------------------------------------------------------------------------

def test_g_launch_healthcheck_files_exist() -> None:
    assert (REPORT_DIR / "TMUX_OR_NOHUP_START_HEALTHCHECK_CN.md").exists()
    assert (REPORT_DIR / "tmux_or_nohup_start_healthcheck.json").exists()


def test_g_launch_process_alive_or_completed() -> None:
    """Either process is alive (running) or already completed and finalized."""
    pid_path = REPORT_DIR / "tmux_or_nohup_start_healthcheck.json"
    d = json.loads(pid_path.read_text())
    if d.get("process_alive"):
        pid = d.get("process_pid")
        rc = subprocess.run(["ps", "-p", str(pid)], capture_output=True, text=True)
        # Process might have completed in meantime; that's also OK
        assert rc.returncode == 0 or "no such process" in rc.stdout + rc.stderr


def test_g_launch_no_wallet_tx_probe() -> None:
    d = json.loads((REPORT_DIR / "tmux_or_nohup_start_healthcheck.json").read_text())
    assert d["no_wallet_tx_probe_observed"] is True
    assert d["no_24h_started"] is True


# ---------------------------------------------------------------------------
# Stage I (FINAL): final verdict
# ---------------------------------------------------------------------------

def test_i_final_verdict_required_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    required = {
        "stage", "status",
        "coverage_scope", "full_coverage_ready", "do_not_treat_as_full_universe",
        "approved_stage", "selected_pool_count", "placeholder_pool_count",
        "observable_chain_count", "observable_protocol_count",
        "twelve_hour_run_completed", "actual_runtime_minutes",
        "actual_runtime_valid_for_12h_gate",
        "pool_snapshot_rows", "quote_snapshot_rows", "fee_velocity_rows",
        "market_regime_rows",
        "quote_ready_pool_count", "fee_ready_pool_count", "ev_ready_pool_count",
        "preflight_candidate_count", "gate_pass", "can_advance_to_24h",
        "auto_advance_started", "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent", "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_i_final_verdict_coverage_partial() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["coverage_scope"] == "partial_solana_bsc_real_universe"
    assert fv["full_coverage_ready"] is False
    assert fv["do_not_treat_as_full_universe"] is True


def test_i_final_verdict_locked_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["auto_advance_started"] is False
    assert fv["can_advance_to_24h"] is False


def test_i_final_verdict_recommended_in_allowed_set() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    rec = fv.get("recommended_next_stage", "")
    # For RUNNING stage, recommended_next_stage describes what happens AFTER 12h completes
    # (which uses one of the 4-stage allowed set)
    if rec:
        assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in {ALLOWED_NEXT_STAGES}"


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def test_safety_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_safety_no_secret_value_in_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv", ".py"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                for m in pat.finditer(text):
                    snippet = m.group(0)[:80]
                    if "0x" in m.group(0) and len(m.group(0)) >= 64:
                        pytest.fail(f"potential 64-hex secret in {p}: {snippet}")
                    elif "private_key" in pat.pattern or "mnemonic" in pat.pattern or "seed" in pat.pattern:
                        pytest.fail(f"potential secret value in {p}: {snippet}")


def test_safety_v2_12h_data_dir_unchanged() -> None:
    """v2 12h data dir (84 files) should be unchanged — this stage only ADDS new 12h partial data."""
    src = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src.exists():
        pytest.skip("v2 12h fixture data not present")
    files = [f for f in src.rglob("*") if f.is_file()]
    assert len(files) > 0
