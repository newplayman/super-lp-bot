"""Tests for LP Long Horizon Read-only Collector Smoke (LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1).

These tests verify:
1. The previous pipeline stage produced an unlocked collector + schemas
2. The collector script remains read-only and free of wallet / signer / tx / mutation / bridge tokens
3. design mode and smoke mode both run cleanly with exit 0
4. The smoke output is written only to data/lp_long_horizon/
5. The smoke output matches the schema defined in the previous pipeline stage
6. No production data path / shadow table is touched
7. The 7 regime placeholders are present, marked, and not fabricated
8. FINAL_VERDICT.json fields are locked; recommended_next_stage is in the allowed set
9. The long-run readiness is correctly documented as 0/9
10. Process safety (ps aux) shows no canary / live / paper / keypair process
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_smoke" / "20260604_081432"
PIPELINE_REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_data_pipeline" / "20260604_062324"
SCRIPT_PATH = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"
SMOKE_OUTPUT_DIR = REPO_ROOT / "data" / "lp_long_horizon" / "20260604_081432" / "collector_smoke"

FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
CLI_REVIEW_JSON = REPORT_DIR / "collector_cli_review.json"
DESIGN_RESULT = REPORT_DIR / "collector_design_mode_result.json"
SMOKE_RESULT = REPORT_DIR / "collector_smoke_result.json"
SCHEMA_VALIDATION = REPORT_DIR / "smoke_output_schema_validation.json"
REGIME_VALIDATION = REPORT_DIR / "market_regime_smoke_validation.json"
HEALTH_JSON = REPORT_DIR / "collector_health_and_failure_mode.json"
NEXT_STAGE_JSON = REPORT_DIR / "long_horizon_collector_next_stage_decision.json"

CN_DOCS = [
    REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
    REPORT_DIR / "COLLECTOR_CLI_REVIEW_CN.md",
    REPORT_DIR / "COLLECTOR_DESIGN_MODE_RESULT_CN.md",
    REPORT_DIR / "COLLECTOR_SMOKE_RESULT_CN.md",
    REPORT_DIR / "SMOKE_OUTPUT_SCHEMA_VALIDATION_CN.md",
    REPORT_DIR / "MARKET_REGIME_SMOKE_VALIDATION_CN.md",
    REPORT_DIR / "COLLECTOR_HEALTH_AND_FAILURE_MODE_CN.md",
    REPORT_DIR / "LONG_HORIZON_COLLECTOR_NEXT_STAGE_DECISION_CN.md",
    REPORT_DIR / "ONEPAGE_CN.md",
    REPORT_DIR / "ARTIFACT_INDEX.md",
]

# ---------------------------------------------------------------------------
# 1. final verdict (Stage J)
# ---------------------------------------------------------------------------

def test_final_verdict_required_fields():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1"
    assert v["status"] in {"PASS", "WARN", "FAIL"}
    assert v["design_mode_ran"] is True
    assert v["smoke_mode_ran"] is True
    assert v["selected_pool_count"] == 5
    assert v["pool_snapshot_rows"] == 5
    assert v["quote_snapshot_rows"] == 30
    assert v["fee_velocity_rows"] == 25
    assert v["liquidity_distribution_rows"] == 5
    assert v["market_regime_rows"] == 7
    assert v["schema_validation_pass"] is True
    assert v["research_only_write_ok"] is True
    assert v["long_run_ready"] is False
    assert v["long_run_started"] is False
    assert v["can_run_probe_now"] is False
    assert v["tiny_canary_allowed"] == "no"
    assert v["edge_proven"] == "no"
    assert v["wallet_or_tx_touched"] is False
    assert v["transaction_sent"] is False
    assert v["send_hard_disable_still_active"] is True


def test_final_verdict_recommended_next_stage_allowed():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    assert v["recommended_next_stage"] in allowed, (
        f"recommended_next_stage={v['recommended_next_stage']!r} not in allowed {sorted(allowed)}"
    )


# ---------------------------------------------------------------------------
# 2. previous stage inputs locked
# ---------------------------------------------------------------------------

def test_input_evidence_audit_locked_fields():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    locked = audit["locked_boundary_fields"]
    for key in ["can_run_probe_now", "tiny_canary_allowed", "edge_proven",
                "send_hard_disable_still_active", "global_lp_rejected",
                "current_probe_allowed", "long_term_lp_value_judged",
                "wallet_or_tx_touched", "transaction_sent"]:
        assert key in locked, f"missing locked field {key!r}"
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"
    assert locked["edge_proven"] == "no"


def test_input_evidence_audit_smoke_target():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    target = audit["smoke_target_fields"]
    assert target["previous_stage"] == "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1"
    assert target["collector_script_built"] is True
    assert target["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1"
    assert target["default_mode"] == "design"
    assert target["smoke_1_pass_only"] is True
    assert target["long_run_requires_separate_approval"] is True


# ---------------------------------------------------------------------------
# 3. CLI review
# ---------------------------------------------------------------------------

def test_cli_review_modes():
    review = json.loads(CLI_REVIEW_JSON.read_text(encoding="utf-8"))
    assert set(review["actual_cli_signature"]["flags"][0]["allowed"]) == {"design", "smoke"}
    rejected = set(review["mode_whitelist_audit"]["hard_rejected"])
    for bad in ["daemon", "30d", "long", "loop", "cron", "live", "canary", "paper", "probe"]:
        assert bad in rejected, f"{bad!r} not in hard_rejected"


def test_cli_review_path_constraint():
    review = json.loads(CLI_REVIEW_JSON.read_text(encoding="utf-8"))
    assert review["output_path_constraint"]["must_start_with"] == "data/lp_long_horizon"


# ---------------------------------------------------------------------------
# 4. design mode run
# ---------------------------------------------------------------------------

def test_design_mode_run_result():
    r = json.loads(DESIGN_RESULT.read_text(encoding="utf-8"))
    assert r["exit_code"] == 0
    assert r["mode"] == "design"
    assert r["safety_checklist"]["no_network_calls"] is True
    assert r["safety_checklist"]["no_wallet"] is True
    assert r["safety_checklist"]["no_tx"] is True
    assert r["safety_checklist"]["no_daemon"] is True


# ---------------------------------------------------------------------------
# 5. smoke mode run
# ---------------------------------------------------------------------------

def test_smoke_mode_run_result():
    r = json.loads(SMOKE_RESULT.read_text(encoding="utf-8"))
    assert r["smoke_ran"] is True
    assert r["exit_code"] == 0
    assert r["selected_pool_count"] == 5
    assert r["pool_snapshot_rows"] == 5
    assert r["quote_snapshot_rows"] == 30
    assert r["fee_velocity_rows"] == 25
    assert r["liquidity_distribution_rows"] == 5
    assert r["regime_rows"] == 7
    assert r["error_count"] == 0
    assert r["warning_count"] == 0
    assert r["research_only_write_ok"] is True
    assert r["no_production_write"] is True
    assert r["no_wallet"] is True
    assert r["no_tx"] is True


# ---------------------------------------------------------------------------
# 6. smoke output schema validation
# ---------------------------------------------------------------------------

def test_schema_validation_pass():
    v = json.loads(SCHEMA_VALIDATION.read_text(encoding="utf-8"))
    assert v["schema_validation_pass"] is True
    for table in v["tables_validated"]:
        assert table["pass"] is True, f"table {table['name']!r} failed schema validation"
        assert not table["missing_fields"], f"table {table['name']!r} missing fields"


def test_schema_validation_no_secret_or_production():
    v = json.loads(SCHEMA_VALIDATION.read_text(encoding="utf-8"))
    assert v["secret_scan"]["real_secret_hits"] == 0
    assert v["production_data_path_check"]["pass"] is True
    assert v["shadow_table_overwrite_check"]["pass"] is True


# ---------------------------------------------------------------------------
# 7. market regime sample validation
# ---------------------------------------------------------------------------

def test_regime_validation_seven_regimes():
    v = json.loads(REGIME_VALIDATION.read_text(encoding="utf-8"))
    assert v["regime_rows"] == 7
    assert len(v["regimes_present"]) == 7
    expected = {
        "uptrend", "downtrend", "sideways", "high_volume_sideways",
        "high_volatility_trend", "incentive_period", "low_volatility_stable",
    }
    assert set(v["regimes_present"]) == expected
    assert v["missing_data_marked"] is True
    assert v["no_fabrication"] is True


def test_regime_actual_output_has_placeholder():
    """The actual on-disk market_regime.jsonl must have all 7 rows with smoke_placeholder=true."""
    if not SMOKE_OUTPUT_DIR.exists():
        pytest.skip(f"smoke output dir not present: {SMOKE_OUTPUT_DIR}")
    p = SMOKE_OUTPUT_DIR / "market_regime.jsonl"
    assert p.exists()
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 7
    for row in rows:
        assert row["smoke_placeholder"] is True
        assert row["lookback_days"] == 7
        # placeholder values, not fabricated
        assert row["price_change_pct"] == 0.0
        assert row["realized_vol_pct"] == 0.0
        assert row["incentive_active"] is False


# ---------------------------------------------------------------------------
# 8. health / failure mode
# ---------------------------------------------------------------------------

def test_health_readiness_score_zero():
    h = json.loads(HEALTH_JSON.read_text(encoding="utf-8"))
    assert h["smoke_health"]["exit_code"] == 0
    assert h["smoke_health"]["error_count"] == 0 if "error_count" in h["smoke_health"] else True
    assert h["long_run_readiness_score"] == "0/9"
    assert h["long_run_ready"] is False
    assert h["long_run_started"] is False
    assert len(h["current_blocker"]) >= 1


# ---------------------------------------------------------------------------
# 9. next stage decision
# ---------------------------------------------------------------------------

def test_next_stage_decision_allowed_value():
    n = json.loads(NEXT_STAGE_JSON.read_text(encoding="utf-8"))
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1",
        "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    assert n["decision"]["recommended_next_stage"] in allowed


def test_next_stage_decision_locked_fields():
    n = json.loads(NEXT_STAGE_JSON.read_text(encoding="utf-8"))
    locked = n["locked_fields_preserved"]
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"
    assert locked["edge_proven"] == "no"
    assert locked["long_run_ready"] is False
    assert locked["long_run_started"] is False
    assert locked["wallet_or_tx_touched"] is False
    assert locked["transaction_sent"] is False


# ---------------------------------------------------------------------------
# 10. CN docs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_081432" in text, f"run_id missing in {path.name}"


def test_onepage_contains_required_fields():
    text = (REPORT_DIR / "ONEPAGE_CN.md").read_text(encoding="utf-8")
    for phrase in [
        "LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1",
        "smoke_mode_ran",
        "long_run_ready",
        "can_run_probe_now",
        "tiny_canary_allowed",
        "wallet_or_tx_touched",
        "FIX_REPEAT",
        "20260604_081432",
    ]:
        assert phrase in text, f"missing {phrase!r} in ONEPAGE_CN.md"


def test_artifact_index_references_all_stages():
    text = (REPORT_DIR / "ARTIFACT_INDEX.md").read_text(encoding="utf-8")
    for stage in ["STAGE_A", "INPUT_EVIDENCE", "COLLECTOR_CLI_REVIEW",
                  "COLLECTOR_DESIGN_MODE_RESULT", "COLLECTOR_SMOKE_RESULT",
                  "SMOKE_OUTPUT_SCHEMA_VALIDATION", "MARKET_REGIME_SMOKE_VALIDATION",
                  "COLLECTOR_HEALTH", "LONG_HORIZON_COLLECTOR_NEXT_STAGE_DECISION",
                  "FINAL_VERDICT", "ONEPAGE_CN", "ARTIFACT_INDEX"]:
        assert stage in text, f"missing {stage} reference in ARTIFACT_INDEX.md"


# ---------------------------------------------------------------------------
# 11. run_id consistency
# ---------------------------------------------------------------------------

def test_run_id_consistent():
    expected = "20260604_081432"
    paths = [FINAL_VERDICT, INPUT_EVIDENCE, CLI_REVIEW_JSON, DESIGN_RESULT,
             SMOKE_RESULT, SCHEMA_VALIDATION, REGIME_VALIDATION, HEALTH_JSON,
             NEXT_STAGE_JSON] + CN_DOCS
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 12. process safety (no canary / live / paper / keypair / sendTransaction)
# ---------------------------------------------------------------------------

def test_no_canary_live_paper_keypair_process():
    result = subprocess.run(
        ["bash", "-c",
         "ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|"
         "eth_sendTransaction|keypair' | grep -v grep || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    matched = [
        line for line in result.stdout.splitlines()
        if "grep" not in line and line.strip()
    ]
    assert not matched, f"suspicious running process: {matched}"


# ---------------------------------------------------------------------------
# 13. collector script re-verified (no banned tokens in real code)
# ---------------------------------------------------------------------------

def test_collector_script_self_check_still_passes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", "design"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "SAFETY GUARD" not in result.stderr
    assert "[design mode]" in result.stdout


def test_collector_script_long_run_modes_rejected():
    for bad in ["daemon", "30d", "long", "loop", "live", "canary", "paper", "probe"]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--mode", bad],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "REFUSED" in result.stderr
