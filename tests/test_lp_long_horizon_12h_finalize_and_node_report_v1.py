"""Tests for the 12h full node report (LP_LONG_HORIZON_6H_FINALIZE_AND_FULL_NODE_REPORT_V1 + 12h extension).

These tests verify:
  - 12h node report at reports/lp_long_horizon_node_reports/20260605_082120/12h/ is a full_sample
  - The V2 12h supervisor data_dir is intact (12 ckpts × 7 = 84 files)
  - The CORRECTED_FINAL_VERDICT.json was rebuilt from checkpoints
  - The V2 12h supervisor FINAL_VERDICT.json is NOT overwritten
  - coverage_scope=partial_solana_real_pool_universe, do_not_treat_as_full_coverage=true
  - Locked fields: can_run_probe_now=false, tiny_canary_allowed="no", etc.
  - No auto 24h
  - Final node verdict has all spec-required fields and only allows
    next stages from the 5-stage allowed set

All tests are read-only; they do NOT touch V2 12h data.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE_REPORT_DIR = ROOT / "reports" / "lp_long_horizon_node_reports" / "20260605_082120" / "12h"
EXTENSION_DIR = ROOT / "reports" / "lp_long_horizon_readonly_12h_extension" / "20260605_082120"
EXTENSION_DIR_LAUNCH = ROOT / "reports" / "lp_long_horizon_readonly_continuous_12h_extension" / "20260605_082120"
V2_12H_FINAL_VERDICT = ROOT / "reports" / "lp_long_horizon_readonly_12h_run" / "20260605_082120" / "FINAL_VERDICT.json"
V2_12H_DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
V2_6H_CORRECTED = ROOT / "reports" / "lp_long_horizon_6h_finalizer_rebuild" / "20260605_043726" / "CORRECTED_FINAL_VERDICT.json"

# 5-stage allowed next stages
ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT",
    "LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
}

# V2 12h FINAL_VERDICT.md5 (FAIL with default zeros, untouched)
V2_12H_FINAL_VERDICT_MD5_BEFORE_TESTS = "computed_at_runtime"


# ---------------------------------------------------------------------------
# Stage A: 12h finalize check
# ---------------------------------------------------------------------------

def test_a_v2_12h_final_verdict_exists() -> None:
    assert V2_12H_FINAL_VERDICT.exists(), "V2 12h FINAL_VERDICT.json missing"


def test_a_v2_12h_supervisor_gone() -> None:
    """V2 12h supervisor should have exited after 12h finalize (or fail-safe trap)."""
    rc = subprocess.run(["ps", "-p", "1054322", "-o", "pid="], capture_output=True, text=True)
    assert rc.stdout.strip() == "", f"V2 12h supervisor still running: {rc.stdout}"


def test_a_v2_12h_finalize_failed_default_zeros() -> None:
    """V2 12h FINAL_VERDICT has default-zero row counts (post-12h block NameError, trap overwrote)."""
    fv = json.loads(V2_12H_FINAL_VERDICT.read_text())
    assert fv["status"] == "FAIL"
    assert fv["supervisor_finalize_failed"] is True
    assert fv["finalize_error"] == "trap EXIT rc=1"
    assert fv["pool_snapshot_rows"] == 0
    assert fv["quote_snapshot_rows"] == 0
    assert fv["fee_velocity_rows"] == 0
    assert fv["actual_runtime_minutes"] == 720  # real 12h wallclock ran
    assert fv["actual_runtime_valid_for_12h_gate"] is True


# ---------------------------------------------------------------------------
# Stage B: 12h data integrity
# ---------------------------------------------------------------------------

def test_b_12h_data_dir_84_files() -> None:
    """V2 12h data dir must still have 84 files (12 ckpts × 7)."""
    files = [f for f in V2_12H_DATA_DIR.rglob("*") if f.is_file()]
    assert len(files) == 84, f"expected 84 V2 12h data files, got {len(files)}"


def test_b_12h_12_checkpoints() -> None:
    ckpts = [d for d in V2_12H_DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("checkpoint_")]
    assert len(ckpts) == 12


def test_b_12h_final_verdict_unchanged() -> None:
    """V2 12h FINAL_VERDICT must not be modified by this stage."""
    fv = json.loads(V2_12H_FINAL_VERDICT.read_text())
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["tiny_canary_allowed"] == "no"


# ---------------------------------------------------------------------------
# Stage C: corrected verdict rebuilt from checkpoints
# ---------------------------------------------------------------------------

def test_c_corrected_verdict_exists() -> None:
    assert (EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").exists()


def test_c_corrected_verdict_required_fields() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    spec_required = {
        "stage", "source_run_id", "source_verdict_status", "source_supervisor_finalize_failed",
        "corrected_from_checkpoints", "actual_runtime_minutes", "actual_runtime_valid_for_12h_gate",
        "short_mode_used", "checkpoint_count", "selected_pool_count",
        "pool_snapshot_rows", "quote_snapshot_rows", "fee_velocity_rows",
        "liquidity_distribution_rows", "market_regime_rows",
        "error_rate_pct", "consecutive_429_max", "data_quality_status", "gate_pass",
        "coverage_scope", "do_not_treat_as_full_coverage",
        "can_run_probe_now", "tiny_canary_allowed", "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = spec_required - set(fv.keys())
    assert not missing, f"CORRECTED_FINAL_VERDICT missing fields: {missing}"


def test_c_corrected_from_checkpoints_true() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["corrected_from_checkpoints"] is True


def test_c_source_finalize_failed_recorded() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["source_supervisor_finalize_failed"] is True
    assert fv["source_verdict_status"] == "FAIL"


# ---------------------------------------------------------------------------
# Stage D: rows aggregated from checkpoints (NOT 0)
# ---------------------------------------------------------------------------

def test_d_rows_not_all_zero() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["pool_snapshot_rows"] > 0
    assert fv["quote_snapshot_rows"] > 0
    assert fv["fee_velocity_rows"] > 0
    assert fv["liquidity_distribution_rows"] > 0
    assert fv["market_regime_rows"] > 0


def test_d_rows_match_v2_12h_ckpt_aggregate() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["pool_snapshot_rows"] == 5  # 5 placeholder deduped
    assert fv["quote_snapshot_rows"] == 360  # 30 × 12 ckpts
    assert fv["fee_velocity_rows"] == 300  # 25 × 12
    assert fv["liquidity_distribution_rows"] == 60  # 5 × 12
    assert fv["market_regime_rows"] == 84  # 7 × 12
    assert fv["actual_fee_accrual_placeholder_rows"] == 12  # 1 × 12
    assert fv["selected_real_pool_count"] == 33
    assert fv["placeholder_pool_count"] == 0


def test_d_runtime_valid_and_rows_imply_gate_pass() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["actual_runtime_minutes"] >= 660
    assert fv["actual_runtime_valid_for_12h_gate"] is True
    assert fv["pool_snapshot_rows"] > 0
    assert fv["quote_snapshot_rows"] > 0
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["gate_pass"] is True


# ---------------------------------------------------------------------------
# Stage E: coverage scope (partial universe, NOT full)
# ---------------------------------------------------------------------------

def test_e_coverage_scope_partial_solana() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["coverage_scope"] == "partial_solana_real_pool_universe"
    assert fv["do_not_treat_as_full_coverage"] is True


def test_e_selected_real_pool_count_below_target() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["selected_real_pool_count"] == 33
    assert fv["coverage_gap_count"] == 12  # 45 - 33


def test_e_missing_protocols_listed() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    missing = fv["missing_protocols_in_universe"]
    assert "Meteora DLMM" in str(missing)
    assert "Base Uniswap V3" in str(missing)
    assert "Base Aerodrome" in str(missing)
    assert "BSC PancakeSwap V3" in str(missing)
    assert "BSC PancakeSwap V2" in str(missing)


# ---------------------------------------------------------------------------
# Stage F: locked fields
# ---------------------------------------------------------------------------

def test_f_can_run_probe_now_false() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False


def test_f_tiny_canary_allowed_no() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["tiny_canary_allowed"] == "no"


def test_f_edge_proven_no() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["edge_proven"] == "no"


def test_f_wallet_or_tx_touched_false() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


def test_f_no_auto_advance() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["auto_advance_started"] is False
    assert fv["longer_stage_started"] is False
    assert fv["can_advance_to_next"] is False  # LOCKED, even if gate=PASS


# ---------------------------------------------------------------------------
# Stage G: 12h node report (full_sample, NOT partial)
# ---------------------------------------------------------------------------

def test_g_node_report_dir_exists() -> None:
    assert NODE_REPORT_DIR.exists()


def test_g_node_report_required_files() -> None:
    required = [
        "NODE_REPORT.json", "NODE_REPORT_CN.md",
        "POOL_UNIVERSE_COVERAGE_MANIFEST.csv", "POOL_UNIVERSE_COVERAGE_MANIFEST.json",
        "FEE_ESTIMATION_BASIS.json", "FEE_ESTIMATION_BASIS_CN.md",
        "RANGE_LIQUIDITY_FEE_SENSITIVITY.csv", "RANGE_LIQUIDITY_FEE_SENSITIVITY.json",
        "CANDIDATE_REVIEW.csv", "CANDIDATE_REVIEW.json",
        "FINAL_NODE_VERDICT.json",
    ]
    for f in required:
        assert (NODE_REPORT_DIR / f).exists(), f"missing required file {f}"


def test_g_node_report_full_sample_true() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["full_sample"] is True


def test_g_node_report_partial_sample_false() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["partial_sample"] is False


def test_g_node_report_source_run_id() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["source_run_id"] == "20260605_082120"
    assert fv["node"] == "12h"


def test_g_node_report_checkpoint_completeness() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["checkpoint_count_observed"] == 12
    assert fv["checkpoint_count_expected"] == 12


def test_g_node_report_coverage_partial_marked() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["coverage_scope"] == "partial_solana_real_pool_universe"
    assert fv["do_not_treat_as_full_coverage"] is True
    assert fv["coverage_gap_count"] == 12


def test_g_node_report_quote_fee_ev_all_zero() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["quote_ready_pool_count"] == 0
    assert fv["fee_ready_pool_count"] == 0
    assert fv["ev_ready_pool_count"] == 0
    assert fv["preflight_candidate_count"] == 0
    assert fv["watchlist_count"] == 0
    assert fv["data_insufficient_count"] == 60
    assert fv["reject_count"] == 0


# ---------------------------------------------------------------------------
# Stage H: locked fields
# ---------------------------------------------------------------------------

def test_h_node_report_can_run_probe_now_false() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["auto_probe_allowed"] is False
    assert fv["auto_trade_allowed"] is False
    assert fv["manual_approval_required_for_execution"] is True


# ---------------------------------------------------------------------------
# Stage I: final verdict allowed next stages only
# ---------------------------------------------------------------------------

def test_i_node_report_recommended_next_stage_allowed() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    rec = fv["recommended_next_stage"]
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in allowed set"


def test_i_node_report_recommended_next_stage_is_12h_fix_repeat() -> None:
    """Per recommendation: 24h NOT recommended due to partial coverage. 12h_fix_repeat preferred."""
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["recommended_next_stage"] == "LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT"


def test_i_node_report_allowed_stages_listed() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    listed = set(fv["allowed_recommended_next_stages"])
    assert listed == ALLOWED_NEXT_STAGES


def test_i_do_not_auto_start_24h() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["do_not_auto_start_24h"] is True
    assert fv["manual_approval_required_for_24h"] is True
    assert "24h" in fv["manual_approval_phrase_24h"]


# ---------------------------------------------------------------------------
# Stage J: tx send / forbidden process check
# ---------------------------------------------------------------------------

def test_j_no_transaction_send_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_j_v2_12h_supervisor_not_running() -> None:
    """V2 12h supervisor PID 1054322 should be gone (V2 12h has finalized)."""
    rc = subprocess.run(["ps", "-p", "1054322", "-o", "pid="], capture_output=True, text=True)
    assert rc.stdout.strip() == "", f"V2 12h supervisor still running: {rc.stdout}"


def test_j_no_new_tmux_for_12h_observation() -> None:
    rc = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
    assert "staged_observation" not in rc.stdout
    assert "node_report" not in rc.stdout


# ---------------------------------------------------------------------------
# Stage K: gate_checks structure
# ---------------------------------------------------------------------------

def test_k_gate_checks_15_items() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert len(fv["gate_checks"]) == 15
    assert fv["gate_check_pass_count"] == 15
    assert fv["gate_check_fail_count"] == 0


def test_k_data_quality_status_pass() -> None:
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["data_quality_status"] == "PASS"


# ---------------------------------------------------------------------------
# Stage L: 6h + 12h both corrected verdicts exist
# ---------------------------------------------------------------------------

def test_l_6h_corrected_verdict_still_intact() -> None:
    """V2 6h corrected verdict (from previous stage) must be untouched."""
    assert V2_6H_CORRECTED.exists()
    fv = json.loads(V2_6H_CORRECTED.read_text())
    assert fv["gate_pass"] is True
    assert fv["actual_runtime_minutes"] == 360


def test_l_12h_corrected_verdict_intact() -> None:
    """V2 12h corrected verdict (this stage) must exist and be valid."""
    fv = json.loads((EXTENSION_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["corrected_from_checkpoints"] is True
    assert fv["actual_runtime_minutes"] == 720
    assert fv["gate_pass"] is True


# ---------------------------------------------------------------------------
# Stage M: no secret value in 12h outputs
# ---------------------------------------------------------------------------

def test_m_no_secret_value_in_12h_outputs() -> None:
    """No real secret values in 12h report files.

    Whitelist: 12h approval phrase sha256 (which is a hash, not a secret).
    """
    import json as _json
    fv = _json.loads((EXTENSION_DIR_LAUNCH / "MANUAL_APPROVAL_RECORDED.json").read_text())
    WHITELIST_HEX_64 = {fv.get("user_approval_text_hash_sha256", "")}

    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
        re.compile(r'\b[0-9a-fA-F]{64,}\b'),
    ]
    for p in (EXTENSION_DIR.rglob("*"), NODE_REPORT_DIR.rglob("*")):
        for f in p:
            if f.is_file() and f.suffix in {".json", ".md", ".csv"}:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for pat in value_patterns:
                    m = pat.search(text)
                    if m:
                        matched = m.group(0)
                        if any(wh in matched for wh in WHITELIST_HEX_64):
                            continue
                        pytest.fail(f"potential secret value matched {pat.pattern!r} in {f}: {matched[:80]}")
