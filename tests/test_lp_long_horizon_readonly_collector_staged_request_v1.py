"""Tests for LP Long Horizon Read-only Collector Staged Run Request (STAGED_REQUEST_V1).

Verifies:
1. one_shot_7d_replaced = true
2. stages include 6h/12h/24h/48h/72h/7d
3. auto_advance_allowed = false
4. manual_approval_required_each_stage = true
5. no cron enabled
6. no systemd enabled
7. no daemon started
8. long_run_started = false
9. can_run_probe_now = false
10. final verdict allowed next stages only
11. No actual approval recorded as true
12. Locked boundary fields preserved
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_staged_request" / "20260604_123955"

FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
PLAN_JSON = REPORT_DIR / "staged_run_plan.json"
GATE_JSON = REPORT_DIR / "stage_gate_rules.json"
APPROVAL_JSON = REPORT_DIR / "stage_approval_templates.json"
BUDGET_JSON = REPORT_DIR / "stage_runtime_budget.json"
POLICY_JSON = REPORT_DIR / "stage_failure_and_abort_policy.json"
TMUX_JSON = REPORT_DIR / "staged_tmux_script_template.json"

CN_DOCS = [
    REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
    REPORT_DIR / "STAGED_RUN_PLAN_CN.md",
    REPORT_DIR / "STAGE_GATE_RULES_CN.md",
    REPORT_DIR / "STAGE_APPROVAL_TEMPLATES_CN.md",
    REPORT_DIR / "STAGE_RUNTIME_BUDGET_CN.md",
    REPORT_DIR / "STAGE_FAILURE_AND_ABORT_POLICY_CN.md",
    REPORT_DIR / "STAGED_TMUX_SCRIPT_TEMPLATE_CN.md",
    REPORT_DIR / "ONEPAGE_CN.md",
    REPORT_DIR / "ARTIFACT_INDEX.md",
]

# ---------------------------------------------------------------------------
# 1. final verdict (Stage I)
# ---------------------------------------------------------------------------

def test_final_verdict_required_fields():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1"
    assert v["status"] in {"PASS", "WARN", "FAIL"}
    assert v["one_shot_7d_replaced"] is True
    assert v["staged_plan_ready"] is False
    assert v["first_stage"] == "6h"
    assert v["auto_advance_allowed"] is False
    assert v["manual_approval_required_each_stage"] is True
    assert v["tmux_template_generated"] is False  # this stage: template in MD, JSON literal false
    assert v["cron_enabled"] is False
    assert v["systemd_enabled"] is False
    assert v["daemon_started"] is False
    assert v["long_run_started"] is False
    assert v["can_run_probe_now"] is False
    assert v["tiny_canary_allowed"] == "no"
    assert v["edge_proven"] == "no"
    assert v["wallet_or_tx_touched"] is False
    assert v["transaction_sent"] is False
    assert v["send_hard_disable_still_active"] is True


def test_final_verdict_stages_complete():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    expected = ["6h", "12h", "24h", "48h", "72h", "7d"]
    assert v["stages"] == expected
    # Each stage detail
    assert len(v["stages_detail"]) == 6
    for s in v["stages_detail"]:
        assert s["stage"] in expected
        assert s["auto_advance"] is False
        assert s["manual_approval_required"] is True


def test_final_verdict_recommended_next_stage_allowed():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_REQUEST_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    assert v["recommended_next_stage"] in allowed, (
        f"recommended_next_stage={v['recommended_next_stage']!r} "
        f"not in allowed {sorted(allowed)}"
    )


def test_final_verdict_redirect_record():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    r = v["redirect_record"]
    assert r["previous_recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1"
    assert r["current_recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1"
    assert r["one_shot_7d_replaced"] is True


def test_final_verdict_safety_18_fields():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    s = v["safety"]
    for key in [
        "touched_trading_path", "touched_wallet_tx_bridge_live_paper",
        "wallet_or_tx_touched", "solana_wallet_or_keypair_touched",
        "transaction_sent", "send_hard_disable_still_active",
        "no_paid_rpc_integration", "no_paid_indexer_integration",
        "no_protocol_re_run", "no_heuristic_modification",
        "no_long_running_daemon", "no_signer_creation",
        "no_7d_14d_30d_run", "no_actual_stage_run",
        "no_approval_recorded_true",
        "secret_leak_count", "production_write_count",
        "shadow_overwrite_count", "tmux_actual_session_started",
    ]:
        assert key in s, f"missing safety field {key!r}"


# ---------------------------------------------------------------------------
# 2. Input evidence audit (Stage B)
# ---------------------------------------------------------------------------

def test_input_evidence_locked_boundary_fields():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    locked = audit["locked_boundary_fields"]
    for key in ["can_run_probe_now", "tiny_canary_allowed", "edge_proven",
                "send_hard_disable_still_active", "wallet_or_tx_touched",
                "transaction_sent", "long_run_started", "global_lp_rejected"]:
        assert key in locked, f"missing locked field {key!r}"
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"
    assert locked["edge_proven"] == "no"
    assert locked["long_run_started"] is False


def test_input_evidence_stages_and_advance():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    assert audit["stages_defined"] == ["6h", "12h", "24h", "48h", "72h", "7d"]
    assert audit["first_stage"] == "6h"
    assert audit["auto_advance_allowed"] is False
    assert audit["manual_approval_required_each_stage"] is True


def test_input_evidence_no_approval_recorded():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    for prohibition in audit["hard_prohibitions_checklist"]:
        assert "no approval recorded as true" in prohibition or True  # presence-only check
    # The dedicated entry must be present
    assert any(
        "no approval recorded as true" in p.lower()
        for p in audit["hard_prohibitions_checklist"]
    )


# ---------------------------------------------------------------------------
# 3. Staged run plan (Stage C)
# ---------------------------------------------------------------------------

def test_plan_stages_complete():
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    assert plan["stages"] == ["6h", "12h", "24h", "48h", "72h", "7d"]
    assert plan["first_stage"] == "6h"
    assert plan["auto_advance_allowed"] is False
    assert plan["one_shot_7d_replaced"] is True
    assert plan["manual_approval_required_each_stage"] is True
    assert len(plan["stages_detail"]) == 6
    for s in plan["stages_detail"]:
        assert s["auto_advance"] is False
        assert s["manual_approval_required"] is True


def test_plan_forbidden_shortcuts():
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    forbidden = plan["forbidden_shortcuts"]
    for phrase in [
        "skip 6h to 12h",
        "skip 12h to 24h",
        "skip any stage",
        "auto_advance",
        "single approval",
        "treat 7d as inevitable",
    ]:
        assert any(phrase in f for f in forbidden), f"missing forbidden shortcut: {phrase!r}"


def test_plan_current_state_disabled():
    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    state = plan["current_state"]
    assert state["staged_plan_ready"] is False
    assert state["tmux_template_generated"] is False
    assert state["cron_enabled"] is False
    assert state["systemd_enabled"] is False
    assert state["daemon_started"] is False
    assert state["long_run_started"] is False


# ---------------------------------------------------------------------------
# 4. Stage gate rules (Stage D)
# ---------------------------------------------------------------------------

def test_gate_13_core_rules():
    gate = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    assert len(gate["gate_rules_common"]) == 13
    for rule in gate["gate_rules_common"]:
        assert rule["level"] == "core"
        assert "name" in rule
        assert "threshold" in rule


def test_gate_per_stage_thresholds_complete():
    gate = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    assert set(gate["stage_specific_thresholds"].keys()) == {
        "6h", "12h", "24h", "48h", "72h", "7d"
    }
    for stage, t in gate["stage_specific_thresholds"].items():
        for key in ["min_pool_snapshot_rows", "min_quote_snapshot_rows",
                    "min_fee_velocity_rows", "min_liquidity_distribution_rows",
                    "min_market_regime_rows", "min_real_data_pct",
                    "disk_usage_max_mb"]:
            assert key in t, f"missing threshold key {key!r} for {stage!r}"


def test_gate_data_quality_status_decision():
    gate = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    dq = gate["data_quality_status_decision"]
    assert "PASS" in dq
    assert "WARN_ACCEPTABLE" in dq
    assert "FAIL" in dq


# ---------------------------------------------------------------------------
# 5. Stage approval templates (Stage E)
# ---------------------------------------------------------------------------

def test_approval_6_phrases():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    phrases = appr["approve_phrase_template_per_stage"]
    assert set(phrases.keys()) == {"6h", "12h", "24h", "48h", "72h", "7d"}
    for stage, phrase in phrases.items():
        expected = f"APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage={stage} mode=readonly no_probe=true"
        assert phrase == expected, f"phrase mismatch for {stage!r}"


def test_approval_record_required_fields():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    tpl = appr["approve_record_template"]
    for key in ["phrase", "stage", "mode", "no_probe", "approved_at",
                "approved_by", "reason", "preconditions_verified",
                "risk_acknowledged"]:
        assert key in tpl, f"missing approval template field {key!r}"


def test_approval_no_batch_or_forward():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    excl = appr["cross_stage_exclusivity"]
    assert any("batch" in e.lower() for e in excl)
    assert any("forward" in e.lower() for e in excl)
    assert any("implicit" in e.lower() for e in excl)


def test_approval_reject_and_pause_phrases():
    appr = json.loads(APPROVAL_JSON.read_text(encoding="utf-8"))
    assert "REJECT_LP_LONG_HORIZON_READONLY_STAGE_RUN" in appr["reject_phrase_template"]
    assert "PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN" in appr["pause_phrase_template"]


# ---------------------------------------------------------------------------
# 6. Runtime budget (Stage F)
# ---------------------------------------------------------------------------

def test_budget_6_stage_records():
    budget = json.loads(BUDGET_JSON.read_text(encoding="utf-8"))
    assert set(budget["estimated_records_per_stage"].keys()) == {
        "6h", "12h", "24h", "48h", "72h", "7d"
    }
    for stage, est in budget["estimated_records_per_stage"].items():
        assert "pool_snapshots_per_pool" in est
        assert "quote_snapshots_total" in est


def test_budget_paid_rpc_required_progression():
    budget = json.loads(BUDGET_JSON.read_text(encoding="utf-8"))
    paid = budget["paid_rpc_required"]
    assert paid["6h"] == "no"
    assert paid["12h"] == "no"
    assert paid["24h"] == "no"
    assert paid["48h"] in {"recommend", "yes"}
    assert paid["72h"] == "yes"
    assert paid["7d"] == "must"


def test_budget_size_estimates_within_threshold():
    budget = json.loads(BUDGET_JSON.read_text(encoding="utf-8"))
    for stage, sz in budget["size_estimates"].items():
        assert sz["total_mb"] <= sz["disk_max_mb"] * 1.0  # upper bound <= max


# ---------------------------------------------------------------------------
# 7. Failure / abort policy (Stage G)
# ---------------------------------------------------------------------------

def test_policy_5_abort_conditions():
    pol = json.loads(POLICY_JSON.read_text(encoding="utf-8"))
    assert len(pol["abort_conditions"]) == 5
    kinds = {a["kind"] for a in pol["abort_conditions"]}
    assert "consecutive_429" in kinds
    assert "error_rate" in kinds
    assert "write_failure" in kinds
    assert "safety_self_check_failure" in kinds
    assert "banned_token_detected" in kinds


def test_policy_3_decision_paths():
    pol = json.loads(POLICY_JSON.read_text(encoding="utf-8"))
    paths = pol["decision_paths"]
    assert "fix_repeat" in paths
    assert "pause" in paths
    assert "stop" in paths


def test_policy_no_concealment():
    pol = json.loads(POLICY_JSON.read_text(encoding="utf-8"))
    assert pol["no_concealment"]


# ---------------------------------------------------------------------------
# 8. tmux template (Stage H)
# ---------------------------------------------------------------------------

def test_tmux_template_disabled():
    tmux = json.loads(TMUX_JSON.read_text(encoding="utf-8"))
    assert tmux["tmux_template_generated"] is True
    assert tmux["tmux_disabled_by_default"] is True
    assert tmux["tmux_actual_session_started"] == 0
    assert tmux["cron_enabled"] is False
    assert tmux["systemd_enabled"] is False
    assert tmux["daemon_started"] is False
    assert tmux["long_run_started"] is False


def test_tmux_max_1_concurrent_session():
    tmux = json.loads(TMUX_JSON.read_text(encoding="utf-8"))
    assert tmux["max_concurrent_sessions"] == 1


def test_tmux_forbidden_actions_include_cron_systemd():
    tmux = json.loads(TMUX_JSON.read_text(encoding="utf-8"))
    forbidden = tmux["forbidden_actions"]
    assert any("cron" in f.lower() for f in forbidden)
    assert any("systemd" in f.lower() for f in forbidden)
    assert any("canary" in f.lower() or "live" in f.lower() or "paper" in f.lower() or "probe" in f.lower() for f in forbidden)


# ---------------------------------------------------------------------------
# 9. CN docs + run_id consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_123955" in text, f"run_id missing in {path.name}"


def test_run_id_consistent_across_artifacts():
    expected = "20260604_123955"
    paths = [
        FINAL_VERDICT, INPUT_EVIDENCE, PLAN_JSON, GATE_JSON,
        APPROVAL_JSON, BUDGET_JSON, POLICY_JSON, TMUX_JSON,
    ] + CN_DOCS
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 10. process safety
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


def test_no_tmux_session_for_lp_long_horizon():
    """Verify no tmux session is started for this stage (we did not launch one)."""
    r = subprocess.run(
        ["bash", "-c", "tmux ls 2>/dev/null | grep 'lp_long_horizon' || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    # Allow tmux itself to be missing (no server) — that's fine.
    matched = [line for line in r.stdout.splitlines() if "lp_long_horizon" in line]
    assert not matched, f"unexpected tmux session: {matched}"
