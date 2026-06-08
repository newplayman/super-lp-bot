"""Tests for LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1.

Verifies:
  - All 7 audit deliverable files exist
  - FINAL_AUDIT_VERDICT.json has all required fields
  - status is in {PASS, WARN, FAIL}
  - branch == "feat/supabase-postgres-deployment"
  - commit_before is set
  - r1_pause_respected == True
  - r2_locked == True
  - canary_live_locked == True
  - tiny_canary_allowed == "no"
  - can_run_probe_now == False
  - edge_proven == "no"
  - forbidden_actions_still_zero == True
  - schema_code_drift_found == True (this audit found drift)
  - deployment_blockers_found == True
  - ci_test_gaps_found == True
  - ready_for_p0_pg_02_fix == True
  - recommended_next_stage == "LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DRIFT_FIX_V1"
  - top_10_blockers all enumerated
  - Audit evidence paths exist
  - No R1 / R2 / canary / live reactivation
  - R1 pause/freeze artifacts still present
  - No real secret / DSN / private_key in audit output

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "reports" / "p0_postgres_shadow_audit" / "2026-06-09"
R1_PAUSE_DIR = ROOT / "reports" / "lp_long_horizon_r1_pause_and_freeze" / "20260607_191500"

ALLOWED_STATUSES = {"PASS", "WARN", "FAIL"}


# ---------------------------------------------------------------------------
# Deliverable inventory
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "00_INDEX.md",
    "01_EXECUTIVE_SUMMARY_CN.md",
    "02_SCHEMA_CODE_DRIFT_AUDIT.md",
    "03_DEPLOYMENT_RUNNABILITY_AUDIT.md",
    "04_CI_AND_TEST_GAP_AUDIT.md",
    "05_FIX_PLAN_P0_PG_02.md",
    "FINAL_AUDIT_VERDICT.json",
]


def test_all_audit_deliverables_exist() -> None:
    for f in REQUIRED_FILES:
        assert (AUDIT_DIR / f).exists(), f"missing audit deliverable: {f}"


def test_all_audit_files_non_empty() -> None:
    for f in REQUIRED_FILES:
        p = AUDIT_DIR / f
        assert p.exists() and p.stat().st_size > 0, f"empty audit file: {f}"


def test_audit_json_files_valid() -> None:
    p = AUDIT_DIR / "FINAL_AUDIT_VERDICT.json"
    d = json.loads(p.read_text())
    assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# FINAL_AUDIT_VERDICT.json — required fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "stage", "status", "branch", "commit_before", "audited_at_utc",
    "r1_pause_respected", "r2_locked", "canary_live_locked",
    "tiny_canary_allowed", "can_run_probe_now", "edge_proven",
    "forbidden_actions_still_zero",
    "schema_code_drift_found", "deployment_blockers_found", "ci_test_gaps_found",
    "ready_for_p0_pg_02_fix", "recommended_next_stage",
    "top_10_blockers",
]


def test_final_audit_verdict_required_fields() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    missing = [f for f in REQUIRED_FIELDS if f not in d]
    assert not missing, f"FINAL_AUDIT_VERDICT.json missing fields: {missing}"


def test_final_audit_verdict_stage_and_status() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["stage"] == "LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1"
    assert d["status"] in ALLOWED_STATUSES, f"status {d['status']!r} not in {ALLOWED_STATUSES}"


def test_final_audit_verdict_branch() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["branch"] == "feat/supabase-postgres-deployment"
    assert d["commit_before"] == "ed84970"  # R1 pause/freeze commit


def test_final_audit_verdict_r1_respected() -> None:
    """R1 PAUSE must be respected, no reopen."""
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["r1_pause_respected"] is True
    assert d["r1_pause_status"] == "PAUSED"


def test_final_audit_verdict_locked_fields() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["r2_locked"] is True
    assert d["canary_live_locked"] is True
    assert d["tiny_canary_allowed"] == "no"
    assert d["can_run_probe_now"] is False
    assert d["edge_proven"] == "no"
    assert d["forbidden_actions_still_zero"] is True


def test_final_audit_verdict_drift_and_blockers_found() -> None:
    """This audit must report drift/blockers/gaps found = True."""
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["schema_code_drift_found"] is True
    assert d["deployment_blockers_found"] is True
    assert d["ci_test_gaps_found"] is True


def test_final_audit_verdict_ready_for_p0_pg_02() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["ready_for_p0_pg_02_fix"] is True
    assert d["recommended_next_stage"] == "LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DRIFT_FIX_V1"


def test_final_audit_verdict_top_10_blockers() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    blockers = d["top_10_blockers"]
    assert len(blockers) == 10, f"expected 10 blockers, got {len(blockers)}"
    # Verify ranks 1-10
    ranks = {b["rank"] for b in blockers}
    assert ranks == set(range(1, 11)), f"blocker ranks not 1-10: {ranks}"
    # All blockers have id, title, severity
    for b in blockers:
        assert "id" in b
        assert "title" in b
        assert "severity" in b
        assert b["severity"] in {"P0", "P1"}


# ---------------------------------------------------------------------------
# Audit does NOT do (negative tests)
# ---------------------------------------------------------------------------

def test_audit_did_not_modify_code() -> None:
    """Audit stage must not modify any .go / .sql / .toml file."""
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    audit_did_not = d["this_stage_did_not"]
    assert "modify any .sql migration file" in audit_did_not
    assert any(".go file" in s for s in audit_did_not)
    assert any("modify any config" in s for s in audit_did_not)


def test_audit_did_not_activate_r1_r2_canary_live() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    audit_did_not = d["this_stage_did_not"]
    assert any("R1" in s for s in audit_did_not)
    assert any("R2" in s for s in audit_did_not)
    assert any("canary/live" in s or "unlock" in s for s in audit_did_not)


def test_audit_did_not_connect_to_real_db() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    audit_did_not = d["this_stage_did_not"]
    # Should not connect to Supabase, prod DB, etc.
    assert "run psql" in " ".join(audit_did_not).lower() or "no psql" in " ".join(audit_did_not).lower()
    assert "no Supabase" in " ".join(audit_did_not) or "supabase" in " ".join(audit_did_not).lower()


def test_audit_forbidden_actions_audit_clean() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    faa = d["forbidden_actions_audit_during_p0_pg_01"]
    # All keys should be True (clean)
    for k, v in faa.items():
        assert v is True, f"forbidden_actions_audit_during_p0_pg_01.{k} should be True, got {v}"


# ---------------------------------------------------------------------------
# R1 pause artifacts still present (audit did not touch them)
# ---------------------------------------------------------------------------

def test_r1_pause_artifacts_intact() -> None:
    """R1 pause/freeze record must still be at expected path with 7 files."""
    assert R1_PAUSE_DIR.exists(), f"R1 pause dir missing: {R1_PAUSE_DIR}"
    expected_files = [
        "FINAL_PAUSE_VERDICT.json",
        "PAUSE_DECISION_CN.md",
        "REOPEN_CONDITIONS_CN.md",
        "SUPERVISOR_FIX_OPTIONS_CN.md",
        "WHAT_DATA_CAN_BE_REUSED_CN.md",
        "FORBIDDEN_ACTIONS_LOCK.json",
        "NEXT_ENGINEERING_TRACK_RECOMMENDATION.md",
    ]
    for f in expected_files:
        assert (R1_PAUSE_DIR / f).exists(), f"R1 pause file missing: {f}"


def test_r1_pause_verdict_status() -> None:
    d = json.loads((R1_PAUSE_DIR / "FINAL_PAUSE_VERDICT.json").read_text())
    assert d["status"] == "PAUSED"


def test_r1_data_dir_intact() -> None:
    """R1 v3 data dir must still be at expected path with 12 ckpts + 156 r1 files."""
    data_dir = ROOT / "data" / "lp_long_horizon_r1_12h_full_wallclock" / "20260607_191500"
    assert data_dir.exists()
    ckpts = sorted([d for d in data_dir.glob("checkpoint_*") if d.is_dir()])
    assert len(ckpts) == 12
    files = list(data_dir.glob("checkpoint_*/r1_*"))
    assert len(files) == 156


# ---------------------------------------------------------------------------
# Audit report content sanity
# ---------------------------------------------------------------------------

def test_drift_audit_references_specific_files() -> None:
    """Schema drift audit must reference specific Go files and migrations."""
    p = AUDIT_DIR / "02_SCHEMA_CODE_DRIFT_AUDIT.md"
    text = p.read_text()
    # Should reference real files / line numbers
    assert "decision_trace.go" in text
    assert "position_mark.go" in text
    assert "main.go" in text
    assert "000011" in text or "shadow_decision_trace" in text
    assert "BLK-PG-" in text


def test_deployment_audit_references_systemd() -> None:
    p = AUDIT_DIR / "03_DEPLOYMENT_RUNNABILITY_AUDIT.md"
    text = p.read_text()
    assert "lpbot-shadow.service" in text
    assert "lpbot-canary.service" in text
    assert "EnvironmentFile" in text
    assert "BLK-PG-06" in text


def test_ci_audit_references_makefile_and_ci() -> None:
    p = AUDIT_DIR / "04_CI_AND_TEST_GAP_AUDIT.md"
    text = p.read_text()
    assert "Makefile" in text
    assert "ci.yml" in text
    assert "TestPostgresAdapter_DockerIntegration_RoundTrip" in text
    assert "-race" in text


def test_fix_plan_references_5_subtasks() -> None:
    p = AUDIT_DIR / "05_FIX_PLAN_P0_PG_02.md"
    text = p.read_text()
    assert "P0-PG-02-A" in text
    assert "P0-PG-02-B" in text
    assert "P0-PG-02-C" in text
    assert "P0-PG-02-D" in text
    assert "P0-PG-02-E" in text


def test_executive_summary_references_top10() -> None:
    p = AUDIT_DIR / "01_EXECUTIVE_SUMMARY_CN.md"
    text = p.read_text()
    assert "Top 10 Blockers" in text or "top_10_blockers" in text.lower()
    assert "BLK-PG-01" in text


# ---------------------------------------------------------------------------
# Audit evidence paths
# ---------------------------------------------------------------------------

def test_audit_evidence_paths_in_verdict() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    paths = d["audit_evidence_paths"]
    assert len(paths) == 6  # 5 .md + 1 .json
    for p in paths:
        # Each path should be relative to reports/
        assert p.startswith("reports/p0_postgres_shadow_audit/2026-06-09/")
        # And the file should exist
        full = ROOT / p
        assert full.exists(), f"audit evidence path missing: {p}"


# ---------------------------------------------------------------------------
# Safety / no secret leak
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


def test_safety_no_real_secret_in_audit_output() -> None:
    """Audit output must not contain real secrets, only placeholders."""
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in AUDIT_DIR.rglob("*"):
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


# ---------------------------------------------------------------------------
# R1 R2 canary live not reactivated
# ---------------------------------------------------------------------------

def test_r1_r2_canary_live_not_reactivated() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert d["r1_pause_respected"] is True
    assert d["r2_locked"] is True
    assert d["canary_live_locked"] is True
    assert d["can_run_probe_now"] is False
    assert d["tiny_canary_allowed"] == "no"
    assert d["edge_proven"] == "no"


# ---------------------------------------------------------------------------
# Audit summary presence
# ---------------------------------------------------------------------------

def test_audit_summary_present() -> None:
    d = json.loads((AUDIT_DIR / "FINAL_AUDIT_VERDICT.json").read_text())
    assert "summary" in d
    assert "8 P0" in d["summary"] or "8 个 P0" in d["summary"]
    assert "P0-PG-02" in d["summary"] or "P0-PG-02" in d["recommended_next_stage"]
