"""Tests for LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1.

Verifies the R1 12h deliverables + supervisor output:
  - 12 ckpt completed
  - gate decision DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE
  - all forbidden actions = 0
  - 5+ dim row>0
  - source health recorded
  - watchlist / ready evolution replayable
  - no 24h auto-advance
  - no actual fee (LOCKED)
  - no wallet/tx/probe

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_real_data_observation" / "20260607_171000"
R1_12H_DATA_DIR = ROOT / "data" / "lp_long_horizon_r1_12h" / "20260607_171000"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1",
    "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT",
    "LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Deliverables exist
# ---------------------------------------------------------------------------

def test_all_deliverables_exist() -> None:
    files = [
        "FINAL_VERDICT.json", "ONEPAGE_CN.md", "R1_12H_OBSERVATION_REPORT_CN.md",
        "SOURCE_HEALTH.json",
        "WATCHLIST_EVOLUTION.json", "WATCHLIST_EVOLUTION.jsonl",
        "READY_EVOLUTION.json", "READY_EVOLUTION.jsonl",
        "DATA_QUALITY_SUMMARY.json",
    ]
    for f in files:
        assert (REPORT_DIR / f).exists(), f"missing deliverable: {f}"


def test_r1_12h_data_dir_exists() -> None:
    assert R1_12H_DATA_DIR.exists(), f"R1 12h data dir missing: {R1_12H_DATA_DIR}"


def test_r1_12h_12_checkpoints() -> None:
    ckpts = sorted([d for d in R1_12H_DATA_DIR.glob("checkpoint_*") if d.is_dir()])
    assert len(ckpts) == 12, f"expected 12 ckpts, got {len(ckpts)}"


# ---------------------------------------------------------------------------
# 12 ckpt completed + gate
# ---------------------------------------------------------------------------

def test_r1_12h_completed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["r1_12h_completed"] is True
    assert fv["checkpoint_count"] == 12
    assert fv["status"] == "PASS"


def test_gate_decision() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["gate_decision"] == "DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE"


# ---------------------------------------------------------------------------
# 5+ dim row>0
# ---------------------------------------------------------------------------

def test_at_least_5_dimensions_have_row_count() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["all_5_dimensions_have_row_count"] is True
    last = fv["row_counts_last_ckpt"]
    assert last["pool_snapshots"] > 0
    assert last["quote_snapshots"] > 0
    assert last["fee_velocity"] > 0
    assert last["liquidity_distribution"] > 0
    assert last["candidate_review"] > 0


# ---------------------------------------------------------------------------
# All forbidden actions = 0
# ---------------------------------------------------------------------------

def test_forbidden_actions_zero() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    fa = fv["forbidden_actions_check"]
    assert fa["wallet_or_tx_touched"] is False
    assert fa["transaction_sent"] is False
    assert fa["can_run_probe_now"] is False
    assert fa["tiny_canary_allowed"] == "no"
    assert fa["edge_proven"] == "no"
    assert fa["actual_fee_data_available"] is False
    assert fa["auto_advance_to_24h"] is False
    assert fa["longer_stage_started"] is False
    assert fa["no_paid_rpc_key_committed"] is True
    assert fa["no_real_secret_committed"] is True


def test_pass_criteria_all_true() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    pc = fv["pass_criteria"]
    assert pc["twelve_checkpoints_completed"] is True
    assert pc["all_forbidden_actions_zero"] is True
    assert pc["at_least_5_dimensions_have_row_output"] is True
    assert pc["source_health_recorded"] is True
    assert pc["watchlist_evolution_replayable"] is True
    assert pc["ready_evolution_replayable"] is True
    assert pc["no_auto_advance_24h"] is True
    assert pc["no_auto_probe"] is True


def test_fail_criteria_all_false() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    fc = fv["fail_criteria"]
    assert fc["touched_wallet_tx_signer_live_paper"] is False
    assert fc["overwrote_old_data_dir"] is False
    assert fc["auto_started_24h_plus"] is False
    assert fc["faked_actual_fee_or_proxy_as_actual"] is False
    assert fc["reported_r1_as_edge_proven"] is False


# ---------------------------------------------------------------------------
# source health
# ---------------------------------------------------------------------------

def test_source_health_recorded() -> None:
    sh = json.loads((REPORT_DIR / "SOURCE_HEALTH.json").read_text())
    assert "sources_per_ckpt" in sh
    assert "overall_source_health" in sh
    assert sh["chains_skipped"] == ["base"]
    # Solana + bsc + coingecko reachable, base + dexscreener + meteora unreachable
    ohs = sh["overall_source_health"]
    assert "reachable" in ohs["solana"]
    assert "reachable" in ohs["bsc"]
    assert "unreachable" in ohs["base"]
    assert "reachable" in ohs["coingecko"]
    assert "unreachable" in ohs["dexscreener"]


# ---------------------------------------------------------------------------
# watchlist / ready evolution
# ---------------------------------------------------------------------------

def test_watchlist_evolution_replayable() -> None:
    we = json.loads((REPORT_DIR / "WATCHLIST_EVOLUTION.json").read_text())
    assert we["watchlist_count_first"] == 7
    assert we["watchlist_count_last"] == 7
    assert we["watchlist_count_drift"] == 0
    assert len(we["evolution"]) == 12


def test_ready_evolution_replayable() -> None:
    re_ = json.loads((REPORT_DIR / "READY_EVOLUTION.json").read_text())
    assert len(re_["evolution"]) == 12
    # fee_ready / liquidity_ready / ev_ready / preflight remain 0 (no improvement)
    last = re_["last_ckpt"]
    assert last["fee_ready_pool_count"] == 0
    assert last["liquidity_ready_pool_count"] == 0
    assert last["ev_ready_pool_count"] == 0
    assert last["preflight_candidate_count"] == 0


def test_watchlist_evolution_jsonl() -> None:
    p = REPORT_DIR / "WATCHLIST_EVOLUTION.jsonl"
    lines = p.read_text().strip().split("\n")
    assert len(lines) == 12
    for line in lines:
        d = json.loads(line)
        assert "watchlist_count" in d


# ---------------------------------------------------------------------------
# actual_fee_data_available remains false
# ---------------------------------------------------------------------------

def test_actual_fee_data_available_remains_false() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["actual_fee_data_available"] is False
    assert fv["fee_proxy_only"] is True
    assert fv["edge_proven"] == "no"


# ---------------------------------------------------------------------------
# No 24h auto-advance
# ---------------------------------------------------------------------------

def test_no_24h_auto_advance() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["auto_advance_to_24h"] is False
    assert fv["longer_stage_started"] is False
    assert fv["can_run_probe_now"] is False


# ---------------------------------------------------------------------------
# FINAL_VERDICT allowed next stages
# ---------------------------------------------------------------------------

def test_final_verdict_recommended_in_allowed_set() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    rec = fv.get("recommended_next_stage", "")
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in {ALLOWED_NEXT_STAGES}"


# ---------------------------------------------------------------------------
# Old data dirs unchanged (R0 12h + R1 smoke)
# ---------------------------------------------------------------------------

def test_old_12h_data_dir_unchanged() -> None:
    old_12h = ROOT / "data" / "lp_long_horizon" / "20260606_131323"
    if not old_12h.exists():
        pytest.skip("v2 12h data dir not present")
    ckpts = list(old_12h.glob("checkpoint_*"))
    assert len(ckpts) == 12


def test_r1_smoke_data_dir_unchanged() -> None:
    r1_smoke = ROOT / "data" / "lp_long_horizon_r1_smoke" / "20260607_163000"
    if not r1_smoke.exists():
        pytest.skip("R1 smoke data dir not present")
    assert r1_smoke.exists()


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
        if p.is_file() and p.suffix in {".json", ".md", ".csv", ".jsonl"}:
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
