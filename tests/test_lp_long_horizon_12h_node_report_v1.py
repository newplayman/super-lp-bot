"""Tests for LP_LONG_HORIZON_READONLY_12H_NODE_REPORT_V1.

These tests verify the 12h node report deliverables written after 12h finalize PASS:
  - 12H_NODE_REPORT_CN.md
  - coverage_manifest.json
  - fee_estimation_basis.json
  - candidate_review.json
  - next_node_decision.json
  - ARTIFACT_INDEX.md

12h gate is verified via the 12h finalize FINAL_VERDICT.json in
reports/lp_long_horizon_readonly_12h_run/20260606_131323/FINAL_VERDICT.json.

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_readonly_12h_node_report" / "20260606_131323"
FINALIZE_DIR = ROOT / "reports" / "lp_long_horizon_readonly_12h_run" / "20260606_131323"
DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260606_131323"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage H 12h finalize gate
# ---------------------------------------------------------------------------

def test_finalize_verdict_exists() -> None:
    p = FINALIZE_DIR / "FINAL_VERDICT.json"
    assert p.exists(), f"12h finalize FINAL_VERDICT not found: {p}"
    assert (FINALIZE_DIR / ".finalize_succeeded").exists(), "12h finalize marker missing"


def test_finalize_verdict_gate_pass() -> None:
    d = json.loads((FINALIZE_DIR / "FINAL_VERDICT.json").read_text())
    assert d["status"] == "PASS", f"12h gate status: {d['status']}"
    assert d["twelve_hour_run_completed"] is True
    assert d["actual_runtime_valid_for_12h_gate"] is True
    assert d["actual_runtime_minutes"] >= 660
    assert d["gate_pass"] is True
    assert d["data_quality_status"] == "PASS"
    assert d["error_rate_pct"] == 0.0
    assert d["consecutive_429_max"] == 0


def test_finalize_verdict_locked_fields() -> None:
    d = json.loads((FINALIZE_DIR / "FINAL_VERDICT.json").read_text())
    # 12h finalize FINAL_VERDICT uses auto_advance_started (not auto_advance_to_next)
    assert d["can_run_probe_now"] is False
    assert d["tiny_canary_allowed"] == "no"
    assert d["edge_proven"] == "no"
    assert d["wallet_or_tx_touched"] is False
    assert d["transaction_sent"] is False
    assert d["auto_advance_started"] is False
    assert d["longer_stage_started"] is False
    assert d["send_hard_disable_still_active"] is True


# ---------------------------------------------------------------------------
# Node report deliverables exist
# ---------------------------------------------------------------------------

def test_node_report_files_exist() -> None:
    assert (REPORT_DIR / "12H_NODE_REPORT_CN.md").exists()
    assert (REPORT_DIR / "coverage_manifest.json").exists()
    assert (REPORT_DIR / "fee_estimation_basis.json").exists()
    assert (REPORT_DIR / "candidate_review.json").exists()
    assert (REPORT_DIR / "next_node_decision.json").exists()
    assert (REPORT_DIR / "ARTIFACT_INDEX.md").exists()


def test_node_report_cn_has_required_sections() -> None:
    text = (REPORT_DIR / "12H_NODE_REPORT_CN.md").read_text()
    for sec in [
        "## 0. 一句话",
        "## 1. 时间线",
        "## 2. 池 universe 分布",
        "## 3. 12h 数据收集",
        "## 4. 数据质量",
        "## 5. Market regime 分布",
        "## 6. Locked fields",
        "## 7. recommended_next_stage",
        "## 8. 12h finalize 输出",
        "## 9. 12h node report 评估结论",
        "## 10. 与前几 stage 的关系",
    ]:
        assert sec in text, f"missing section: {sec}"


# ---------------------------------------------------------------------------
# Coverage manifest
# ---------------------------------------------------------------------------

def test_coverage_manifest_partial() -> None:
    d = json.loads((REPORT_DIR / "coverage_manifest.json").read_text())
    assert d["coverage_scope"] == "partial_solana_bsc_real_universe"
    assert d["do_not_treat_as_full_universe"] is True
    assert d["full_coverage_ready"] is False
    assert d["three_level_coverage"]["chain_level"]["observed_chains"] == ["solana", "bsc"]
    assert "base" in d["three_level_coverage"]["chain_level"]["missing_chains"]
    assert d["three_level_coverage"]["pool_level"]["observed_pool_count"] == 53
    assert d["three_level_coverage"]["pool_level"]["placeholder_pool_count"] == 0
    assert d["three_level_coverage"]["pool_level"]["smoke_placeholder_pool_count"] == 53


def test_coverage_manifest_chain_distribution() -> None:
    d = json.loads((REPORT_DIR / "coverage_manifest.json").read_text())
    pd = d["three_level_coverage"]["pool_level"]["chain_distribution"]
    assert pd == {"solana": 49, "bsc": 4}


def test_coverage_manifest_protocol_distribution() -> None:
    d = json.loads((REPORT_DIR / "coverage_manifest.json").read_text())
    pd = d["three_level_coverage"]["pool_level"]["protocol_distribution"]
    assert pd["solana/orca_whirlpool"] == 13
    assert pd["solana/raydium_clmm"] == 10
    assert pd["solana/raydium_cpmm"] == 10
    assert pd["solana/meteora_dlmm"] == 16
    assert pd["bsc/pancakeswap_v3"] == 4


# ---------------------------------------------------------------------------
# Fee estimation basis
# ---------------------------------------------------------------------------

def test_fee_estimation_basis_r0_phase() -> None:
    d = json.loads((REPORT_DIR / "fee_estimation_basis.json").read_text())
    assert d["coverage_scope"] == "partial_solana_bsc_real_universe"
    assert d["r0_phase_status"].startswith("proxy mode only")
    # r0 phase: no actual fee, all 0
    for proto, info in d["per_pool_fee_tier_summary"].items():
        assert info["r0_estimated_24h_fee_usd_per_1000usd_position"] == 0.0, f"{proto} r0 fee not 0"


def test_fee_estimation_basis_r1_blockers() -> None:
    d = json.loads((REPORT_DIR / "fee_estimation_basis.json").read_text())
    blockers = d["r1_phase_blockers"]
    assert len(blockers) > 0
    # Must disclose Base RPC issue
    assert any("Base" in b for b in blockers)


# ---------------------------------------------------------------------------
# Candidate review
# ---------------------------------------------------------------------------

def test_candidate_review_no_preflight() -> None:
    d = json.loads((REPORT_DIR / "candidate_review.json").read_text())
    assert d["candidate_status"]["preflight_candidate_count"] == 0
    assert d["candidate_status"]["ev_ready_pool_count"] == 0
    assert d["candidate_status"]["actual_fee_accrual_pool_count"] == 0
    # tier_classifier_output is at the top level (tier_classification_status), not in candidate_status
    assert d["tier_classification_status"]["tier_classifier_output"].startswith("DEFERRED_TO_R1")


def test_candidate_review_tier_deferred() -> None:
    d = json.loads((REPORT_DIR / "candidate_review.json").read_text())
    tc = d["tier_classification_status"]
    assert tc["tier_classifier_output"].startswith("DEFERRED_TO_R1")
    assert tc["tier_a_assigned"] is False
    assert tc["tier_b_assigned"] is False
    assert tc["tier_c_assigned"] is False


# ---------------------------------------------------------------------------
# Next node decision
# ---------------------------------------------------------------------------

def test_next_node_decision_manual_required() -> None:
    d = json.loads((REPORT_DIR / "next_node_decision.json").read_text())
    assert d["next_node_decision"] == "MANUAL_USER_DECISION_REQUIRED"
    assert d["current_12h_finalize_status"] == "PASS"


def test_next_node_decision_four_allowed_stages() -> None:
    d = json.loads((REPORT_DIR / "next_node_decision.json").read_text())
    stages = {s["stage"] for s in d["allowed_next_stages_with_rationale"]}
    assert stages == ALLOWED_NEXT_STAGES


def test_next_node_decision_24h_requires_new_approval() -> None:
    d = json.loads((REPORT_DIR / "next_node_decision.json").read_text())
    for s in d["allowed_next_stages_with_rationale"]:
        if s["stage"] == "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1":
            assert s["requires_user_approval"] is True
            assert s["requires_new_scope_freeze"] is True
            assert s["auto_advance_to_24h"] is False
            assert s["scope_suggestion"] == "partial_solana_bsc_real_universe_24h_extension (NOT full coverage)"


def test_next_node_decision_prohibits_probe_canary_live() -> None:
    d = json.loads((REPORT_DIR / "next_node_decision.json").read_text())
    # not_recommended_next_stages are strings with rationale; check prefix
    nr = " ".join(d["not_recommended_next_stages"])
    assert "LP_LONG_HORIZON_TINY_CANARY_PROBE_V1" in nr
    assert "LP_LONG_HORIZON_LIVE_PROBE_V1" in nr
    assert "LP_LONG_HORIZON_PAPER_TRADE_V1" in nr
    assert "LP_LONG_HORIZON_24H_AUTO_V1" in nr


def test_next_node_decision_locked_fields() -> None:
    d = json.loads((REPORT_DIR / "next_node_decision.json").read_text())
    lf = d["locked_fields"]
    assert lf["can_run_probe_now"] is False
    assert lf["tiny_canary_allowed"] == "no"
    assert lf["edge_proven"] == "no"
    assert lf["wallet_or_tx_touched"] is False
    assert lf["transaction_sent"] is False
    assert lf["auto_advance_to_next"] is False
    assert lf["longer_stage_started"] is False


# ---------------------------------------------------------------------------
# Data integrity
# ---------------------------------------------------------------------------

def test_data_dir_has_12_checkpoints() -> None:
    ckpts = sorted(DATA_DIR.glob("checkpoint_*"))
    assert len(ckpts) == 12, f"expected 12 checkpoints, got {len(ckpts)}"


def test_data_dir_ckpt_12_has_smoke_summary() -> None:
    last = sorted(DATA_DIR.glob("checkpoint_12_*"))[0]
    assert (last / "smoke_summary.json").exists()
    s = json.loads((last / "smoke_summary.json").read_text())
    assert s["selected_real_pool_count"] == 53
    assert s["placeholder_pool_count"] == 0
    assert s["all_pools_are_real_on_chain"] is True
    assert s["wallet_or_tx_touched"] is False
    assert s["transaction_sent"] is False


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def test_safety_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction",
                 "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
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
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
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
