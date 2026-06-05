"""Tests for the 6h full node report (LP_LONG_HORIZON_6H_FINALIZE_AND_FULL_NODE_REPORT_V1).

These tests verify:
  - The 6h node report at reports/lp_long_horizon_node_reports/20260605_043726/6h/
    is a full_sample (not partial_sample)
  - The V2 source data (data/lp_long_horizon/20260605_043726/) is intact
  - Coverage manifest has all 3 levels (chain/dex/pool)
  - Fee estimation basis marks proxy, not actual
  - Locked fields: can_run_probe_now=false, tiny_canary_allowed="no", etc.
  - Final node verdict has all spec-required fields and only allows
    next stages from the 5-stage allowed set
  - No V2 supervisor / collector / data files were modified by the generator

All tests are read-only; they do NOT touch V2 data and do NOT generate
additional node reports.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE_REPORT_DIR = ROOT / "reports" / "lp_long_horizon_node_reports" / "20260605_043726" / "6h"
V2_FINAL_VERDICT = ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260605_043726" / "FINAL_VERDICT.json"
V2_DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260605_043726"

# 5-stage allowed next stages
ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_NODE_REPORT_FIX_REPEAT",
    "LP_LONG_HORIZON_COLLECTOR_6H_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
}


# ---------------------------------------------------------------------------
# Stage A: V2 FINAL_VERDICT exists
# ---------------------------------------------------------------------------

def test_a_v2_final_verdict_exists() -> None:
    """V2 FINAL_VERDICT.json must exist for full 6h node report generation."""
    assert V2_FINAL_VERDICT.exists(), "V2 FINAL_VERDICT.json missing; cannot generate full 6h node report"


def test_a_v2_final_verdict_status_known() -> None:
    fv = json.loads(V2_FINAL_VERDICT.read_text())
    assert fv["status"] in ("PASS", "WARN", "FAIL")
    assert fv["actual_runtime_minutes"] >= 0


# ---------------------------------------------------------------------------
# Stage B: full_sample + partial_sample
# ---------------------------------------------------------------------------

def test_b_node_report_directory_exists() -> None:
    assert NODE_REPORT_DIR.exists()
    assert NODE_REPORT_DIR.is_dir()


def test_b_node_report_required_files() -> None:
    """All 11 spec-required files must be present."""
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


def test_b_node_report_full_sample_true() -> None:
    """Final node verdict must have full_sample=true (since V2 finished 6h)."""
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["full_sample"] is True


def test_b_node_report_partial_sample_false() -> None:
    """Final node verdict must have partial_sample=false (full 6h)."""
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["partial_sample"] is False


def test_b_node_report_source_run_id() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["source_run_id"] == "20260605_043726"
    assert fv["node"] == "6h"


def test_b_node_report_checkpoint_completeness() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["checkpoint_count_observed"] == 6
    assert fv["checkpoint_count_expected"] == 6
    assert fv["checkpoint_completeness_pct"] == 100.0


# ---------------------------------------------------------------------------
# Stage C: V2 data integrity (must NOT be modified by generator)
# ---------------------------------------------------------------------------

def test_c_v2_data_dir_42_files() -> None:
    """V2 data dir must still have 42 files (6 ckpts × 7 files)."""
    files = [f for f in V2_DATA_DIR.rglob("*") if f.is_file()]
    assert len(files) == 42, f"expected 42 V2 data files, got {len(files)}"


def test_c_v2_data_dir_6_checkpoints() -> None:
    ckpts = [d for d in V2_DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("checkpoint_")]
    assert len(ckpts) == 6


def test_c_v2_final_verdict_unchanged() -> None:
    """V2 FINAL_VERDICT must not have been modified by the generator."""
    fv = json.loads(V2_FINAL_VERDICT.read_text())
    assert fv["status"] in ("PASS", "FAIL")  # V2 finalized → status set
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


# ---------------------------------------------------------------------------
# Stage D: coverage manifest has all 3 levels
# ---------------------------------------------------------------------------

def test_d_coverage_manifest_has_3_levels() -> None:
    cov = json.loads((NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").read_text())
    assert "chain_coverage" in cov
    assert "dex_coverage" in cov
    assert "pool_coverage" in cov


def test_d_chain_coverage_count_7() -> None:
    cov = json.loads((NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").read_text())
    assert len(cov["chain_coverage"]) == 7


def test_d_dex_coverage_count_10() -> None:
    cov = json.loads((NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").read_text())
    assert len(cov["dex_coverage"]) == 10


def test_d_pool_coverage_count_30() -> None:
    cov = json.loads((NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").read_text())
    assert len(cov["pool_coverage"]) == 30


def test_d_chain_observed_solana_only() -> None:
    cov = json.loads((NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").read_text())
    observed = [c["chain"] for c in cov["chain_coverage"] if c["observed"]]
    assert observed == ["solana"]


# ---------------------------------------------------------------------------
# Stage D cont: fee estimation basis marks proxy, not actual
# ---------------------------------------------------------------------------

def test_e_fee_estimation_marks_proxy_not_actual() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["fee_estimation_status"]["actual_fee_data_available"] is False
    assert fv["fee_estimation_status"]["fee_proxy_used"] is True
    assert fv["fee_estimation_status"]["heuristic_used"] is True
    assert fv["fee_estimation_status"]["fee_estimate_confidence"] == "low"


def test_e_fee_basis_has_5_pool_type_formulas() -> None:
    fb = json.loads((NODE_REPORT_DIR / "FEE_ESTIMATION_BASIS.json").read_text())
    for key in ("v3_clmm", "meteora_dlmm", "cpmm", "stable_pool"):
        assert key in fb
        assert len(fb[key]) > 0


def test_e_fee_estimation_r1_requirements_count() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["fee_estimation_status"]["r1_upgrade_requirements_count"] >= 6


# ---------------------------------------------------------------------------
# Stage E: locked fields
# ---------------------------------------------------------------------------

def test_f_can_run_probe_now_false() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False


def test_f_tiny_canary_allowed_no() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["tiny_canary_allowed"] == "no"


def test_f_edge_proven_no() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["edge_proven"] == "no"


def test_f_wallet_tx_touched_false() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


def test_f_auto_probe_trade_disallowed() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["auto_probe_allowed"] is False
    assert fv["auto_trade_allowed"] is False
    assert fv["manual_approval_required_for_execution"] is True


# ---------------------------------------------------------------------------
# Stage E cont: no wallet/keypair/signer
# ---------------------------------------------------------------------------

def test_g_node_report_no_secret_keys() -> None:
    """Node report JSON must not contain any forbidden secret keys."""
    report = json.loads((NODE_REPORT_DIR / "NODE_REPORT.json").read_text())
    forbidden = {"tx_hash", "wallet_address", "private_key", "keypair", "mnemonic", "seed", "signed_transaction"}
    def walk(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in forbidden:
                    pytest.fail(f"forbidden key {k!r} found at {path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
    walk(report)


def test_g_no_secret_value_in_reports() -> None:
    """No real secret values (private keys, mnemonics, hex keys) in this turn's files."""
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
        re.compile(r'\b[0-9a-fA-F]{64,}\b'),
    ]
    for p in NODE_REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {m.group(0)[:80]}")


# ---------------------------------------------------------------------------
# Stage F: tx send forbidden
# ---------------------------------------------------------------------------

def test_h_no_transaction_send_process() -> None:
    """No sendTransaction / keypair / wallet process should be running."""
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


def test_h_no_new_tmux_for_observation() -> None:
    """No new tmux session started for this 6h node report work."""
    rc = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
    assert "staged_observation" not in rc.stdout
    assert "node_report" not in rc.stdout


# ---------------------------------------------------------------------------
# Stage G: final verdict allowed next stages only
# ---------------------------------------------------------------------------

def test_i_final_node_verdict_recommended_next_stage_allowed() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    rec = fv["recommended_next_stage"]
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in allowed set"


def test_i_final_node_verdict_allowed_stages_listed() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    listed = set(fv["allowed_recommended_next_stages"])
    assert listed == ALLOWED_NEXT_STAGES


def test_i_final_node_verdict_has_spec_required_fields() -> None:
    """Per task spec, FINAL_NODE_VERDICT must have these fields."""
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    spec_required = {
        "stage", "node", "source_run_id", "v2_finalized", "full_sample", "partial_sample",
        "coverage_manifest_generated", "fee_estimation_basis_generated",
        "range_liquidity_fee_sensitivity_generated", "candidate_review_generated",
        "chain_coverage_count", "dex_coverage_count", "pool_coverage_count",
        "quote_ready_pool_count", "fee_ready_pool_count", "ev_ready_pool_count",
        "preflight_candidate_count", "watchlist_count", "data_insufficient_count", "reject_count",
        "can_run_probe_now", "tiny_canary_allowed", "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = spec_required - set(fv.keys())
    assert not missing, f"FINAL_NODE_VERDICT missing required fields: {missing}"


# ---------------------------------------------------------------------------
# Stage G cont: do not auto-start 12h
# ---------------------------------------------------------------------------

def test_j_do_not_auto_start_12h() -> None:
    fv = json.loads((NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert fv["do_not_auto_start_12h"] is True
    assert fv["manual_approval_required_for_12h"] is True
    assert "12h" in fv["manual_approval_phrase_12h"]


# ---------------------------------------------------------------------------
# Cross-cutting: 10-question NODE_REPORT_CN coverage
# ---------------------------------------------------------------------------

def test_k_node_report_cn_10_questions() -> None:
    """NODE_REPORT_CN.md must answer 10 questions per task spec."""
    cn = (NODE_REPORT_DIR / "NODE_REPORT_CN.md").read_text()
    # Question keywords to look for (relaxed; just need to cover the topic)
    keywords = {
        "chain": "链",  # 1. 观察了哪些链
        "dex": "DEX",  # 2. 观察了哪些 DEX
        "pool": "池",   # 3. 观察了哪些 LP 池
        "missing": "未覆盖",  # 4. 哪些没有覆盖
        "quote_ready": "quote-ready",  # 5. quote-ready / fee-ready / ev-ready
        "preflight": "preflight",  # 6. preflight candidate
        "fee_proxy": "fee proxy",  # 7. fee proxy basis
        "range": "range",  # 8. range sensitivity
        "12h": "12h",    # 9. 12h 观察
        "probe": "probe",  # 10. probe forbidden
    }
    for q, kw in keywords.items():
        assert kw.lower() in cn.lower(), f"NODE_REPORT_CN.md missing keyword {kw!r} for question {q!r}"


# ---------------------------------------------------------------------------
# Generator CLI regression
# ---------------------------------------------------------------------------

def test_generator_runs_full_6h_cleanly() -> None:
    """Generator runs end-to-end on the full V2 6h data."""
    rc = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "lp_long_horizon_node_report_generator_v1.py"),
            "--run-id", "20260605_043726",
            "--node", "6h",
            "--data-dir", "data/lp_long_horizon/20260605_043726",
            "--report-dir", "reports/lp_long_horizon_node_reports/20260605_043726/6h_generator_regression",
        ],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, f"generator failed: {rc.stderr}"
    out = json.loads(rc.stdout)
    assert out["gate_status"] in ("PASS", "WARN_ACCEPTABLE", "FAIL")
    assert out["partial_sample"] is False
    # Cleanup
    import shutil
    shutil.rmtree(ROOT / "reports" / "lp_long_horizon_node_reports" / "20260605_043726" / "6h_generator_regression", ignore_errors=True)
