"""Tests for LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1.

Verifies:
  - All 7 PAUSE deliverable files exist
  - FINAL_PAUSE_VERDICT.json has all required fields
  - status == "PAUSED"
  - source_run_id == "20260607_191500"
  - source_status == "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"
  - review_commit == "b46f52e"
  - duration_wallclock_seconds == 39917
  - duration_threshold_seconds == 43200
  - duration_wallclock_seconds_ok == False
  - checkpoint_count == 12
  - data_value == "real_observation_only"
  - edge_proven == "no"
  - actual_fee_data_available == False
  - fee_proxy_only == True
  - can_run_probe_now == False
  - tiny_canary_allowed == "no"
  - r2_locked == True
  - supervisor_fix_required_before_repeat == True
  - no_auto_advance == True
  - forbidden_actions_still_zero == True
  - recommended_next_engineering_track == "P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1"
  - 22 forbidden actions locked
  - PAUSE does not modify code / data / freeze / merge / pkill
  - PAUSE does not unlock R2 / canary / live / tiny_canary
  - PAUSE does not claim edge_proven=yes
  - PAUSE does not auto-advance to 24h

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAUSE_DIR = ROOT / "reports" / "lp_long_horizon_r1_pause_and_freeze" / "20260607_191500"
SOURCE_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_full_wallclock_observation" / "20260607_191500"
REVIEW_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_node_report_review" / "20260607_191500"

TYPO_BLACKLIST = [
    "CWALLCLICK_PROOF",
    "checkpointPinterval_drift_srconds",
    "finalize_aftertexpscaed_end",
    "cheartbeat_index",
    "stt_us",
]


# ---------------------------------------------------------------------------
# Deliverable inventory
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "FINAL_PAUSE_VERDICT.json",
    "PAUSE_DECISION_CN.md",
    "REOPEN_CONDITIONS_CN.md",
    "SUPERVISOR_FIX_OPTIONS_CN.md",
    "WHAT_DATA_CAN_BE_REUSED_CN.md",
    "FORBIDDEN_ACTIONS_LOCK.json",
    "NEXT_ENGINEERING_TRACK_RECOMMENDATION.md",
]


def test_all_pause_deliverables_exist() -> None:
    for f in REQUIRED_FILES:
        assert (PAUSE_DIR / f).exists(), f"missing PAUSE deliverable: {f}"


def test_all_pause_files_non_empty() -> None:
    for f in REQUIRED_FILES:
        p = PAUSE_DIR / f
        assert p.exists() and p.stat().st_size > 0, f"empty PAUSE file: {f}"


def test_pause_json_files_valid() -> None:
    for f in ["FINAL_PAUSE_VERDICT.json", "FORBIDDEN_ACTIONS_LOCK.json"]:
        p = PAUSE_DIR / f
        d = json.loads(p.read_text())
        assert isinstance(d, dict), f"{f} must be a JSON object"


# ---------------------------------------------------------------------------
# FINAL_PAUSE_VERDICT.json — required fields
# ---------------------------------------------------------------------------

REQUIRED_PAUSE_FIELDS = [
    "status", "source_run_id", "source_status", "review_commit",
    "duration_wallclock_seconds", "duration_threshold_seconds",
    "duration_wallclock_seconds_ok", "checkpoint_count", "data_value",
    "edge_proven", "actual_fee_data_available", "fee_proxy_only",
    "can_run_probe_now", "tiny_canary_allowed", "r2_locked",
    "supervisor_fix_required_before_repeat", "no_auto_advance",
    "forbidden_actions_still_zero", "recommended_next_engineering_track",
]


def test_final_pause_verdict_required_fields() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    missing = [f for f in REQUIRED_PAUSE_FIELDS if f not in d]
    assert not missing, f"FINAL_PAUSE_VERDICT.json missing fields: {missing}"


def test_final_pause_verdict_status() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["status"] == "PAUSED"


def test_final_pause_verdict_run_id_and_source() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["source_run_id"] == "20260607_191500"
    assert d["source_status"] == "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"
    assert d["review_commit"] == "b46f52e"
    assert d["review_status"] == "WARN"


def test_final_pause_verdict_duration() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["duration_wallclock_seconds"] == 39917
    assert d["duration_threshold_seconds"] == 43200
    assert d["duration_wallclock_seconds_ok"] is False


def test_final_pause_verdict_checkpoint() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["checkpoint_count"] == 12
    assert d["checkpoint_count_expected"] == 12
    assert d["checkpoint_count_ok"] is True


def test_final_pause_verdict_data_value() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["data_value"] == "real_observation_only"


def test_final_pause_verdict_locked_fields() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["edge_proven"] == "no"
    assert d["actual_fee_data_available"] is False
    assert d["fee_proxy_only"] is True
    assert d["can_run_probe_now"] is False
    assert d["tiny_canary_allowed"] == "no"
    assert d["r2_locked"] is True
    assert d["supervisor_fix_required_before_repeat"] is True
    assert d["no_auto_advance"] is True
    assert d["forbidden_actions_still_zero"] is True


def test_final_pause_verdict_recommended_track() -> None:
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["recommended_next_engineering_track"] == "P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1"


def test_final_pause_verdict_no_typo() -> None:
    p = PAUSE_DIR / "FINAL_PAUSE_VERDICT.json"
    raw = json.loads(p.read_text())
    keys = []
    def walk(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.append(f"{prefix}.{k}" if prefix else k)
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{prefix}[{i}]")
    walk(raw)
    for typo in TYPO_BLACKLIST:
        matched = [k for k in keys if typo in k]
        assert not matched, f"typo {typo!r} in FINAL_PAUSE_VERDICT.json: {matched}"


def test_final_pause_verdict_consistent_with_source() -> None:
    """Cross-check: PAUSE verdict must be consistent with source FINAL_VERDICT and review."""
    pause = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    source_fv = json.loads((SOURCE_DIR / "FINAL_VERDICT.json").read_text())
    review_fv = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    # Duration consistent across all 3
    assert pause["duration_wallclock_seconds"] == source_fv["duration_wallclock_seconds"]
    assert pause["duration_wallclock_seconds"] == review_fv["duration_wallclock_seconds"]
    # Source status consistent
    assert pause["source_status"] == source_fv["status"]
    # Checkpoint count consistent
    assert pause["checkpoint_count"] == source_fv["checkpoint_count"]
    # Review commit is the reviewed commit
    assert pause["review_commit"] == "b46f52e"
    # Edge proven still "no" across all 3
    assert pause["edge_proven"] == source_fv["edge_proven"]
    assert pause["edge_proven"] == review_fv["edge_proven"]


# ---------------------------------------------------------------------------
# FORBIDDEN_ACTIONS_LOCK.json — 22 locked actions
# ---------------------------------------------------------------------------

def test_forbidden_actions_lock_count() -> None:
    d = json.loads((PAUSE_DIR / "FORBIDDEN_ACTIONS_LOCK.json").read_text())
    actions = d["locked_actions"]
    assert len(actions) == 22, f"expected 22 locked actions, got {len(actions)}"


def test_forbidden_actions_lock_categories() -> None:
    d = json.loads((PAUSE_DIR / "FORBIDDEN_ACTIONS_LOCK.json").read_text())
    actions = d["locked_actions"]
    # Verify all action IDs are present
    ids = {a["id"] for a in actions}
    for i in range(1, 23):
        assert f"FAL-{i:02d}" in ids, f"missing FAL-{i:02d}"


def test_forbidden_actions_lock_summary() -> None:
    d = json.loads((PAUSE_DIR / "FORBIDDEN_ACTIONS_LOCK.json").read_text())
    s = d["summary"]
    assert s["forbidden_actions_locked"] == 22
    assert s["ok"] is True
    # All summary booleans true (excluding count fields)
    for k, v in s.items():
        if k in ("ok", "forbidden_actions_locked", "allowed_during_pause"):
            continue
        assert v is True, f"summary.{k} should be True, got {v}"


# ---------------------------------------------------------------------------
# PAUSE does NOT do (negative tests)
# ---------------------------------------------------------------------------

def test_pause_does_not_modify_r2_lock() -> None:
    """PAUSE must NOT change r2_locked (still true)."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["r2_locked"] is True


def test_pause_does_not_claim_edge() -> None:
    """PAUSE must NOT claim edge_proven=yes."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["edge_proven"] == "no"


def test_pause_does_not_unlock_canary() -> None:
    """PAUSE must NOT change tiny_canary_allowed or can_run_probe_now."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["can_run_probe_now"] is False
    assert d["tiny_canary_allowed"] == "no"


def test_pause_does_not_auto_advance() -> None:
    """PAUSE must NOT enable auto_advance_to_24h."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["no_auto_advance"] is True
    assert d["auto_advance_to_24h"] is False if "auto_advance_to_24h" in d else True


def test_pause_does_not_claim_pass() -> None:
    """PAUSE must NOT claim R1 status as PASS."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["source_status"] != "PASS"
    assert d["status"] != "PASS"


# ---------------------------------------------------------------------------
# PAUSE does (positive tests)
# ---------------------------------------------------------------------------

def test_pause_records_what_it_does() -> None:
    """PAUSE record documents what was done in this_record_does."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert len(d["this_record_does"]) >= 5
    assert any("PAUSED" in s or "pause" in s.lower() for s in d["this_record_does"])


def test_pause_records_what_it_doesnt() -> None:
    """PAUSE record documents what was NOT done in this_record_does_not."""
    d = json.loads((PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert len(d["this_record_does_not"]) >= 10
    # Check that key forbidden actions are listed as not-done
    not_done_str = " ".join(d["this_record_does_not"]).lower()
    assert "edge_proven" in not_done_str
    assert "r2" in not_done_str
    assert "code" in not_done_str
    assert "data dir" in not_done_str


# ---------------------------------------------------------------------------
# REOPEN_CONDITIONS_CN.md
# ---------------------------------------------------------------------------

def test_reopen_conditions_doc_exists() -> None:
    p = PAUSE_DIR / "REOPEN_CONDITIONS_CN.md"
    assert p.exists()
    text = p.read_text()
    # Must mention key hard conditions
    assert "12h" in text
    assert "supervisor" in text
    assert "R2" in text
    assert "edge" in text.lower()


# ---------------------------------------------------------------------------
# SUPERVISOR_FIX_OPTIONS_CN.md
# ---------------------------------------------------------------------------

def test_supervisor_fix_doc_has_3_options() -> None:
    p = PAUSE_DIR / "SUPERVISOR_FIX_OPTIONS_CN.md"
    assert p.exists()
    text = p.read_text()
    assert "Fix A" in text
    assert "Fix B" in text
    assert "Fix C" in text


# ---------------------------------------------------------------------------
# NEXT_ENGINEERING_TRACK_RECOMMENDATION.md
# ---------------------------------------------------------------------------

def test_engineering_track_recommendation_doc() -> None:
    p = PAUSE_DIR / "NEXT_ENGINEERING_TRACK_RECOMMENDATION.md"
    assert p.exists()
    text = p.read_text()
    assert "P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1" in text
    assert "Postgres" in text
    assert "shadow" in text
    # Must NOT claim edge or auto-advance
    assert "edge_proven=yes" not in text
    assert "auto-advance" not in text or "禁止" in text or "NOT" in text or "不" in text


# ---------------------------------------------------------------------------
# WHAT_DATA_CAN_BE_REUSED_CN.md
# ---------------------------------------------------------------------------

def test_data_reuse_doc_has_categories() -> None:
    p = PAUSE_DIR / "WHAT_DATA_CAN_BE_REUSED_CN.md"
    assert p.exists()
    text = p.read_text()
    # Must categorize data reuse
    assert "可" in text
    assert "不可" in text
    assert "重新采集" in text or "must recapture" in text or "R2" in text


# ---------------------------------------------------------------------------
# Source data dir integrity (PAUSE did not delete or modify)
# ---------------------------------------------------------------------------

def test_v3_data_dir_12_ckpts_preserved() -> None:
    data_dir = ROOT / "data" / "lp_long_horizon_r1_12h_full_wallclock" / "20260607_191500"
    ckpts = sorted([d for d in data_dir.glob("checkpoint_*") if d.is_dir()])
    assert len(ckpts) == 12


def test_v3_data_dir_156_r1_files_preserved() -> None:
    data_dir = ROOT / "data" / "lp_long_horizon_r1_12h_full_wallclock" / "20260607_191500"
    files = list(data_dir.glob("checkpoint_*/r1_*"))
    assert len(files) == 156


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


def test_safety_no_secret_in_pause_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in PAUSE_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".txt", ".jsonl"}:
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
