"""Tests for LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1.

These tests verify:
  - The corrected 6h verdict at reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726/
    is built from V2 checkpoints (not hardcoded zeros)
  - The original V2 FINAL_VERDICT is NOT overwritten
  - source_finalize_failed is recorded
  - Locked fields: can_run_probe_now=false, tiny_canary_allowed="no", etc.
  - No auto 12h
  - Final verdict recommended_next_stage is in the 5-stage allowed set
  - The rebuild script refuses bad args and works end-to-end

All tests are read-only; they do NOT touch V2 data or V2 FINAL_VERDICT.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REBUILD_DIR = ROOT / "reports" / "lp_long_horizon_6h_finalizer_rebuild" / "20260605_043726"
V2_FINAL_VERDICT = ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260605_043726" / "FINAL_VERDICT.json"
V2_DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260605_043726"
REBUILD_SCRIPT = ROOT / "scripts" / "rebuild_lp_long_horizon_6h_verdict_from_checkpoints_v1.py"

# 5-stage allowed next stages (per LP_LONG_HORIZON_6H_FINALIZE_AND_FULL_NODE_REPORT_V1 spec)
ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_NODE_REPORT_FIX_REPEAT",
    "LP_LONG_HORIZON_COLLECTOR_6H_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
}

# Snapshot V2 FINAL_VERDICT content hash BEFORE any test runs to verify it
# is not modified by the rebuild script execution.
_EXPECTED_V2_FINAL_VERDICT_MD5 = "8dee718af852c9cadcd515e852f8642d"


# ---------------------------------------------------------------------------
# Stage A: input evidence audit + rebuild dir + V2 FINAL_VERDICT integrity
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (REBUILD_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REBUILD_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_audit_key_assertions() -> None:
    audit = json.loads((REBUILD_DIR / "input_evidence_audit.json").read_text())
    assert audit["key_assertions"]["runtime_valid"] is True
    assert audit["key_assertions"]["short_mode_used"] is False
    assert audit["key_assertions"]["checkpoint_count"] == 6
    assert audit["key_assertions"]["checkpoint_data_exists"] is True
    assert audit["key_assertions"]["original_final_verdict_status"] == "FAIL"
    assert audit["key_assertions"]["original_finalizer_failed"] is True
    assert audit["key_assertions"]["original_rows_zero_due_to_finalize_bug"] is True


def test_a_v2_final_verdict_unchanged_md5() -> None:
    """V2 FINAL_VERDICT.json must NOT be modified by the rebuild."""
    import hashlib
    h = hashlib.md5(V2_FINAL_VERDICT.read_bytes()).hexdigest()
    assert h == _EXPECTED_V2_FINAL_VERDICT_MD5, f"V2 FINAL_VERDICT was modified: {h}"


def test_a_v2_final_verdict_still_fail() -> None:
    """V2 FINAL_VERDICT must still say status=FAIL (we did not rewrite it)."""
    fv = json.loads(V2_FINAL_VERDICT.read_text())
    assert fv["status"] == "FAIL"
    assert fv["selected_pool_count"] == 0
    assert fv["pool_snapshot_rows"] == 0


def test_a_v2_data_dir_42_files() -> None:
    """V2 data dir must still have 42 files (6 ckpts × 7)."""
    files = [f for f in V2_DATA_DIR.rglob("*") if f.is_file()]
    assert len(files) == 42


# ---------------------------------------------------------------------------
# Stage B: rebuild script CLI + sanity
# ---------------------------------------------------------------------------

def test_b_rebuild_script_exists() -> None:
    assert REBUILD_SCRIPT.exists()
    assert REBUILD_SCRIPT.is_file()


def test_b_rebuild_script_syntax() -> None:
    import py_compile
    try:
        py_compile.compile(str(REBUILD_SCRIPT), doraise=True)
    except py_compile.PyCompileError as e:
        pytest.fail(f"rebuild script compile error: {e}")


def test_b_rebuild_script_runs_end_to_end() -> None:
    """Run rebuild on a temp output dir to verify end-to-end + idempotency."""
    import shutil
    # Use relative path so the rebuild script's path-prefix check accepts it
    test_out_rel = "reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726_e2e_test"
    test_out_abs = ROOT / test_out_rel
    if test_out_abs.exists():
        shutil.rmtree(test_out_abs)
    rc = subprocess.run(
        [
            sys.executable, str(REBUILD_SCRIPT),
            "--run-id", "20260605_043726",
            "--data-dir", "data/lp_long_horizon/20260605_043726",
            "--source-verdict", "reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json",
            "--output-dir", test_out_rel,
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode == 0, f"rebuild failed: {rc.stderr}"
    out = json.loads(rc.stdout)
    assert out["gate_pass"] is True
    assert out["checkpoint_count"] == 6
    # Cleanup
    shutil.rmtree(test_out_abs, ignore_errors=True)


def test_b_rebuild_rejects_bad_data_dir() -> None:
    rc = subprocess.run(
        [
            sys.executable, str(REBUILD_SCRIPT),
            "--run-id", "20260605_043726",
            "--data-dir", "tmp/bad",
            "--output-dir", "reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726_bad",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode != 0
    assert "REFUSED" in rc.stderr


def test_b_rebuild_rejects_bad_output_dir() -> None:
    rc = subprocess.run(
        [
            sys.executable, str(REBUILD_SCRIPT),
            "--run-id", "20260605_043726",
            "--data-dir", "data/lp_long_horizon/20260605_043726",
            "--output-dir", "tmp/bad",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode != 0
    assert "REFUSED" in rc.stderr


# ---------------------------------------------------------------------------
# Stage C: corrected verdict schema
# ---------------------------------------------------------------------------

def test_c_corrected_verdict_exists() -> None:
    assert (REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").exists()


def test_c_corrected_verdict_required_fields() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    required = {
        "stage", "source_run_id", "source_verdict_status", "source_supervisor_finalize_failed",
        "corrected_from_checkpoints", "actual_runtime_minutes", "actual_runtime_valid_for_6h_gate",
        "short_mode_used", "checkpoint_count", "selected_pool_count",
        "pool_snapshot_rows", "quote_snapshot_rows", "fee_velocity_rows",
        "liquidity_distribution_rows", "market_regime_rows",
        "error_rate_pct", "consecutive_429_max", "data_quality_status", "gate_pass",
        "can_advance_to_12h", "auto_advance_started", "longer_stage_started",
        "can_run_probe_now", "tiny_canary_allowed", "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"CORRECTED_FINAL_VERDICT missing fields: {missing}"


def test_c_corrected_from_checkpoints_true() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["corrected_from_checkpoints"] is True


def test_c_source_finalize_failed_recorded() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["source_supervisor_finalize_failed"] is True
    assert fv["source_verdict_status"] == "FAIL"


# ---------------------------------------------------------------------------
# Stage D: rows aggregated from checkpoints (NOT 0)
# ---------------------------------------------------------------------------

def test_d_rows_not_all_zero() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["pool_snapshot_rows"] > 0
    assert fv["quote_snapshot_rows"] > 0
    assert fv["fee_velocity_rows"] > 0
    assert fv["liquidity_distribution_rows"] > 0
    assert fv["market_regime_rows"] > 0


def test_d_rows_match_v2_ckpt_aggregate() -> None:
    """Rebuilt rows must match what the V2 supervisor would have aggregated."""
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["pool_snapshot_rows"] == 5
    assert fv["quote_snapshot_rows"] == 180
    assert fv["fee_velocity_rows"] == 150
    assert fv["liquidity_distribution_rows"] == 30
    assert fv["market_regime_rows"] == 42
    assert fv["selected_pool_count"] == 5
    assert fv["actual_fee_accrual_placeholder_rows"] == 6


def test_d_runtime_valid_and_rows_imply_gate_pass() -> None:
    """runtime_valid=true + rows>0 + no wallet/tx → gate_pass=true."""
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["actual_runtime_minutes"] >= 330
    assert fv["actual_runtime_valid_for_6h_gate"] is True
    assert fv["pool_snapshot_rows"] > 0
    assert fv["quote_snapshot_rows"] > 0
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["gate_pass"] is True


# ---------------------------------------------------------------------------
# Stage E: locked fields
# ---------------------------------------------------------------------------

def test_e_can_run_probe_now_false() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False


def test_e_tiny_canary_allowed_no() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["tiny_canary_allowed"] == "no"


def test_e_edge_proven_no() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["edge_proven"] == "no"


def test_e_wallet_or_tx_touched_false() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


def test_e_no_auto_advance() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["auto_advance_started"] is False
    assert fv["longer_stage_started"] is False
    assert fv["can_advance_to_12h"] is False  # LOCKED, even if gate=PASS


# ---------------------------------------------------------------------------
# Stage F: final verdict allowed next stages only
# ---------------------------------------------------------------------------

def test_f_recommended_next_stage_allowed() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    rec = fv["recommended_next_stage"]
    assert rec in ALLOWED_NEXT_STAGES


def test_f_recommended_next_stage_is_12h_extension() -> None:
    """Per Stage D rules: gate_pass=true → recommended=12H_EXTENSION_REQUEST_V1."""
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1"


def test_f_allowed_stages_listed() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    listed = set(fv["allowed_recommended_next_stages"])
    assert listed == ALLOWED_NEXT_STAGES


# ---------------------------------------------------------------------------
# Stage G: no wallet/keypair/signer/tx in any output
# ---------------------------------------------------------------------------

def test_g_no_secret_value_in_rebuild_outputs() -> None:
    """No real secret values in the rebuild output files."""
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
        re.compile(r'\b[0-9a-fA-F]{64,}\b'),
    ]
    for p in REBUILD_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {m.group(0)[:80]}")


def test_g_no_forbidden_keys_in_corrected_verdict() -> None:
    """CORRECTED_FINAL_VERDICT must not contain any forbidden secret keys."""
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    forbidden = {"tx_hash", "wallet_address", "private_key", "keypair", "mnemonic", "seed", "signed_transaction"}
    def walk(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in forbidden:
                    pytest.fail(f"forbidden key {k!r} at {path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
    walk(fv)


# ---------------------------------------------------------------------------
# Stage H: tx send / forbidden process check
# ---------------------------------------------------------------------------

def test_h_no_transaction_send_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_h_v2_supervisor_not_running() -> None:
    """V2 supervisor PID 3872268 should be gone (V2 has finalized)."""
    rc = subprocess.run(["ps", "-p", "3872268", "-o", "pid="], capture_output=True, text=True)
    assert rc.stdout.strip() == "", f"V2 supervisor still running: {rc.stdout}"


def test_h_no_new_tmux_for_rebuild() -> None:
    rc = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
    assert "staged_observation" not in rc.stdout
    assert "finalizer_rebuild" not in rc.stdout


# ---------------------------------------------------------------------------
# Stage I: gate_checks structure
# ---------------------------------------------------------------------------

def test_i_gate_checks_13_items() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert len(fv["gate_checks"]) == 13
    assert fv["gate_check_pass_count"] == 13
    assert fv["gate_check_fail_count"] == 0


def test_i_data_quality_status_pass() -> None:
    fv = json.loads((REBUILD_DIR / "CORRECTED_FINAL_VERDICT.json").read_text())
    assert fv["data_quality_status"] == "PASS"
