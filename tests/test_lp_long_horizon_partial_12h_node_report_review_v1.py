"""Tests for LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1.

Verifies the 12h node report review deliverables (10 + FINAL_VERDICT):
  - 12h pass does NOT imply edge_proven
  - fee_proxy_only=true if actual fee missing
  - candidate_decision_reliable=false if all data_insufficient
  - global_lp_rejected=false (12h r0 = data insufficient, not reject)
  - no probe allowed
  - final verdict allowed next stages only

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_partial_12h_node_report_review" / "20260606_131323"
FINALIZE_DIR = ROOT / "reports" / "lp_long_horizon_readonly_12h_run" / "20260606_131323"
TWELVE_H_DIR = ROOT / "reports" / "lp_long_horizon_readonly_12h_node_report" / "20260606_131323"
DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260606_131323"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1",
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Deliverables exist
# ---------------------------------------------------------------------------

def test_all_deliverables_exist() -> None:
    files = [
        "INPUT_EVIDENCE_AUDIT_CN.md",
        "INPUT_EVIDENCE_AUDIT.json",
        "WHAT_12H_PROVED_CN.md",
        "WHAT_12H_PROVED.json",
        "WHAT_12H_DID_NOT_PROVE_CN.md",
        "WHAT_12H_DID_NOT_PROVE.json",
        "COVERAGE_REVIEW_CN.md",
        "COVERAGE_REVIEW.json",
        "FEE_ESTIMATION_REVIEW_CN.md",
        "FEE_ESTIMATION_REVIEW.json",
        "CANDIDATE_REVIEW_AUDIT_CN.md",
        "CANDIDATE_REVIEW_AUDIT.json",
        "R0_TO_R1_DATA_UPGRADE_PLAN_CN.md",
        "R0_TO_R1_DATA_UPGRADE_PLAN.json",
        "NEXT_STAGE_DECISION_CN.md",
        "NEXT_STAGE_DECISION.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
    ]
    for f in files:
        assert (REPORT_DIR / f).exists(), f"missing deliverable: {f}"


# ---------------------------------------------------------------------------
# FINAL_VERDICT required fields + allowed next stages
# ---------------------------------------------------------------------------

def test_final_verdict_required_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    d = json.loads(p.read_text())
    required = {
        "stage", "status",
        "twelve_hour_pipeline_passed",
        "lp_edge_proven",
        "global_lp_rejected",
        "actual_fee_data_available",
        "fee_proxy_only",
        "candidate_decision_reliable",
        "preflight_candidate_count",
        "watchlist_count",
        "data_insufficient_count",
        "coverage_scope",
        "do_not_treat_as_full_universe",
        "r1_upgrade_required",
        "can_run_probe_now",
        "tiny_canary_allowed",
        "wallet_or_tx_touched",
        "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(d.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_recommended_in_allowed_set() -> None:
    d = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert d["recommended_next_stage"] in ALLOWED_NEXT_STAGES, (
        f"recommended_next_stage {d['recommended_next_stage']!r} not in {ALLOWED_NEXT_STAGES}"
    )


# ---------------------------------------------------------------------------
# 12h pass does NOT imply edge_proven
# ---------------------------------------------------------------------------

def test_12h_pass_does_not_imply_edge_proven() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    fv_12h = json.loads((FINALIZE_DIR / "FINAL_VERDICT.json").read_text())
    # 12h pipeline passed
    assert fv["twelve_hour_pipeline_passed"] is True
    assert fv_12h["gate_pass"] is True
    assert fv_12h["data_quality_status"] == "PASS"
    # BUT edge_proven is FALSE
    assert fv["lp_edge_proven"] is False
    assert fv_12h["edge_proven"] == "no"
    assert fv["edge_proven"] == "no"


def test_12h_pass_does_not_imply_probe_allowed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"


# ---------------------------------------------------------------------------
# fee_proxy_only=true if actual fee missing
# ---------------------------------------------------------------------------

def test_fee_proxy_only_when_actual_fee_missing() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    fee = json.loads((REPORT_DIR / "FEE_ESTIMATION_REVIEW.json").read_text())
    # Actual fee is missing (r0 placeholder)
    assert fv["actual_fee_data_available"] is False
    # So fee_proxy_only MUST be true
    assert fv["fee_proxy_only"] is True
    assert fee["is_actual_fee"] is False
    assert fee["is_proxy_fee"] is True


def test_fee_estimation_review_no_token_id() -> None:
    fee = json.loads((REPORT_DIR / "FEE_ESTIMATION_REVIEW.json").read_text())
    assert fee["has_token_id"] is False
    assert fee["has_fee_growth_inside"] is False
    assert fee["has_tokens_owed"] is False
    assert fee["has_collected_fee"] is False
    assert fee["has_entry_exit_snapshot"] is False


# ---------------------------------------------------------------------------
# candidate_decision_reliable=false if all data_insufficient
# ---------------------------------------------------------------------------

def test_candidate_decision_unreliable_when_all_data_insufficient() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    cr = json.loads((REPORT_DIR / "CANDIDATE_REVIEW_AUDIT.json").read_text())
    cov = json.loads((REPORT_DIR / "COVERAGE_REVIEW.json").read_text())
    # All 53 pools are data_insufficient
    assert cr["data_insufficient_count"] == 53
    assert cr["preflight_candidate_count"] == 0
    assert cr["watchlist_count"] == 0
    assert cr["reject_count"] == 0
    # Verify counts sum to observed_pool_count
    assert cr["preflight_candidate_count"] + cr["watchlist_count"] + cr["data_insufficient_count"] + cr["reject_count"] == cov["pool_count"]["observed_pool_count"]
    # candidate_decision_reliable MUST be false
    assert fv["candidate_decision_reliable"] is False
    assert cr["candidate_decision_reliable"] is False


def test_data_insufficient_not_equal_to_reject() -> None:
    cr = json.loads((REPORT_DIR / "CANDIDATE_REVIEW_AUDIT.json").read_text())
    # data_insufficient ≠ reject (spec clarification)
    assert cr["data_insufficient_count"] == 53
    assert cr["reject_count"] == 0
    # The spec must explicitly say DATA_INSUFFICIENT ≠ REJECT_BY_EV (in either CN or EN spec_clarification / per_pool_classification)
    spec_text = json.dumps(cr, ensure_ascii=False)
    assert "DATA_INSUFFICIENT" in spec_text
    assert "REJECT_BY_EV" in spec_text
    assert "≠" in spec_text or " not " in spec_text.lower() or "不等于" in spec_text or "不 = " in spec_text or "不=reject" in spec_text.lower() or "不 = reject" in spec_text.lower() or "暂搁置" in spec_text


# ---------------------------------------------------------------------------
# global_lp_rejected=false (12h r0 = data insufficient, NOT reject)
# ---------------------------------------------------------------------------

def test_global_lp_rejected_is_false() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    cr = json.loads((REPORT_DIR / "CANDIDATE_REVIEW_AUDIT.json").read_text())
    assert fv["global_lp_rejected"] is False
    assert cr["global_lp_rejected"] is False


def test_global_lp_rejected_explanation_clarifies() -> None:
    cr = json.loads((REPORT_DIR / "CANDIDATE_REVIEW_AUDIT.json").read_text())
    expl = cr["global_lp_rejected_explanation"]
    assert expl["value"] is False
    # The explanation MUST say false means data insufficient, NOT reject
    fm = " ".join(expl["false_means"])
    assert "data insufficient" in fm.lower() or "blocked" in fm.lower() or "r0" in fm.lower()


# ---------------------------------------------------------------------------
# No probe allowed
# ---------------------------------------------------------------------------

def test_no_probe_allowed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    nsd = json.loads((REPORT_DIR / "NEXT_STAGE_DECISION.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    # NEXT_STAGE_DECISION must list probe/canary/live as NOT_RECOMMENDED
    nrs = " ".join(nsd["absolute_prohibitions"])
    assert "不 probe" in nrs or "不 canary" in nrs
    # Match variations: 不 live, / live, /live /, live
    assert ("不 live" in nrs) or ("live" in nrs.lower() and "不" in nrs) or ("probe / canary / live" in nrs)
    assert "不 paper" in nrs or "paper" in nrs.lower()


def test_no_wallet_tx_touched() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


# ---------------------------------------------------------------------------
# Coverage + R1 upgrade required
# ---------------------------------------------------------------------------

def test_coverage_partial_solana_bsc() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    cov = json.loads((REPORT_DIR / "COVERAGE_REVIEW.json").read_text())
    assert fv["coverage_scope"] == "partial_solana_bsc_real_universe"
    assert fv["do_not_treat_as_full_universe"] is True
    assert "solana" in cov["observed_chains"]
    assert "bsc" in cov["observed_chains"]
    assert "base" in cov["missing_chains"]


def test_r1_upgrade_required() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    r1 = json.loads((REPORT_DIR / "R0_TO_R1_DATA_UPGRADE_PLAN.json").read_text())
    nsd = json.loads((REPORT_DIR / "NEXT_STAGE_DECISION.json").read_text())
    assert fv["r1_upgrade_required"] is True
    # R1 stage name is the recommended next stage
    assert nsd["recommended_next_stage"] == "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1"
    assert fv["recommended_next_stage"] == "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1"
    # R1 plan must NOT include probe/canary/live/mint
    ndo = " ".join(r1["r1_does_not_do"])
    assert "不 probe" in ndo
    assert "不 canary" in ndo
    assert "不 live" in ndo
    assert "不 mint" in ndo


# ---------------------------------------------------------------------------
# Data integrity
# ---------------------------------------------------------------------------

def test_twelve_hour_data_dir_intact() -> None:
    """12h data dir (12 ckpts) should be unchanged by this review stage."""
    ckpts = sorted(DATA_DIR.glob("checkpoint_*"))
    assert len(ckpts) == 12


def test_twelve_hour_finalize_intact() -> None:
    """12h finalize FINAL_VERDICT should be unchanged (status=PASS, gate_pass=true)."""
    fv_12h = json.loads((FINALIZE_DIR / "FINAL_VERDICT.json").read_text())
    assert fv_12h["status"] == "PASS"
    assert fv_12h["gate_pass"] is True


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
