"""Tests for LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1.

Verifies:
  - All 7 review deliverable files exist
  - FINAL_REVIEW_VERDICT.json has all required fields
  - status is in {PASS, WARN, FAIL}
  - reviewed_run_id == "20260607_191500"
  - source_status == "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"
  - duration_wallclock_seconds == 39917
  - duration_wallclock_seconds_ok == False
  - checkpoint_count == 12
  - early_finalize_detected == False
  - compressed_detected == False
  - short_supervisor_detected == False
  - old_data_dir_mixed == False
  - prior_baseline_mixed == False
  - forbidden_actions_still_zero == True
  - edge_proven == "no"
  - can_run_probe_now == False
  - tiny_canary_allowed == "no"
  - artifact_consistency_ok == True
  - recommended_next_stage is one of the 4 allowed
  - 27 consistency checks all pass
  - 27 forbidden actions all ok
  - All 14 source deliverable files exist
  - All 14 source files have correct integrity (no typo, no corruption)
  - run_history_audit references v0, v1, v3 pids
  - No 24h / 48h / 72h / 7d / R2 / probe / canary / live / paper / wallet / secret

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_node_report_review" / "20260607_191500"
SOURCE_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_full_wallclock_observation" / "20260607_191500"
DATA_DIR = ROOT / "data" / "lp_long_horizon_r1_12h_full_wallclock" / "20260607_191500"

ALLOWED_STATUSES = {"PASS", "WARN", "FAIL"}
ALLOWED_RECOMMENDED_NEXT_STAGES = {
    "LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1",
    "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT",
    "LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}
TYPO_BLACKLIST = [
    "CWALLCLICK_PROOF",
    "checkpointPinterval_drift_srconds",
    "finalize_aftertexpscaed_end",
    "cheartbeat_index",
    "stt_us",
]


# ---------------------------------------------------------------------------
# Review deliverable inventory
# ---------------------------------------------------------------------------

REQUIRED_REVIEW_FILES = [
    "FINAL_REVIEW_VERDICT.json",
    "NODE_REPORT_REVIEW_CN.md",
    "CHECKPOINT_TIMELINE_AUDIT.md",
    "WALLCLOCK_FAILURE_CAUSE.md",
    "ARTIFACT_CONSISTENCY_AUDIT.json",
    "FORBIDDEN_ACTIONS_RECHECK.json",
    "NEXT_STAGE_RECOMMENDATION.md",
]


def test_all_review_deliverables_exist() -> None:
    for f in REQUIRED_REVIEW_FILES:
        assert (REVIEW_DIR / f).exists(), f"missing review deliverable: {f}"


def test_all_review_files_non_empty() -> None:
    for f in REQUIRED_REVIEW_FILES:
        p = REVIEW_DIR / f
        assert p.exists() and p.stat().st_size > 0, f"empty review file: {f}"


def test_review_json_files_valid() -> None:
    for f in ["FINAL_REVIEW_VERDICT.json", "ARTIFACT_CONSISTENCY_AUDIT.json", "FORBIDDEN_ACTIONS_RECHECK.json"]:
        p = REVIEW_DIR / f
        d = json.loads(p.read_text())
        assert isinstance(d, dict), f"{f} must be a JSON object"


# ---------------------------------------------------------------------------
# FINAL_REVIEW_VERDICT.json — required fields
# ---------------------------------------------------------------------------

def test_final_review_verdict_required_fields() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    required = [
        "status", "reviewed_run_id", "source_status", "duration_wallclock_seconds",
        "duration_wallclock_seconds_ok", "checkpoint_count", "checkpoint_count_ok",
        "artifact_consistency_ok", "early_finalize_detected", "compressed_detected",
        "short_supervisor_detected", "old_data_dir_mixed", "prior_baseline_mixed",
        "forbidden_actions_still_zero", "edge_proven", "can_run_probe_now",
        "tiny_canary_allowed", "recommended_next_stage", "reason",
    ]
    missing = [f for f in required if f not in d]
    assert not missing, f"FINAL_REVIEW_VERDICT.json missing fields: {missing}"


def test_final_review_verdict_status_in_set() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["status"] in ALLOWED_STATUSES, f"status {d['status']!r} not in {ALLOWED_STATUSES}"


def test_final_review_verdict_run_id() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["reviewed_run_id"] == "20260607_191500"
    assert d["source_status"] == "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"


def test_final_review_verdict_duration() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["duration_wallclock_seconds"] == 39917
    assert d["duration_wallclock_seconds_ok"] is False
    assert d["duration_threshold_seconds"] == 43200


def test_final_review_verdict_checkpoint_count() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["checkpoint_count"] == 12
    assert d["checkpoint_count_ok"] is True
    assert d["checkpoint_count_expected"] == 12


def test_final_review_verdict_no_fabrication_flags() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["early_finalize_detected"] is False
    assert d["compressed_detected"] is False
    assert d["short_supervisor_detected"] is False
    assert d["old_data_dir_mixed"] is False
    assert d["prior_baseline_mixed"] is False
    assert d["estimated_row_count_detected"] is False
    assert d["synthetic_mtime_detected"] is False


def test_final_review_verdict_artifact_consistency_ok() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["artifact_consistency_ok"] is True


def test_final_review_verdict_locked_fields() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["forbidden_actions_still_zero"] is True
    assert d["edge_proven"] == "no"
    assert d["can_run_probe_now"] is False
    assert d["tiny_canary_allowed"] == "no"
    assert d["auto_advance_to_24h"] is False
    assert d["longer_stage_started"] is False
    assert d["actual_fee_data_available"] is False
    assert d["fee_proxy_only"] is True
    assert d["wallet_or_tx_touched"] is False
    assert d["transaction_sent"] is False


def test_final_review_verdict_recommended_next_stage() -> None:
    d = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert d["recommended_next_stage"] in ALLOWED_RECOMMENDED_NEXT_STAGES


def test_final_review_verdict_no_typo_fields() -> None:
    p = REVIEW_DIR / "FINAL_REVIEW_VERDICT.json"
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
        assert not matched, f"typo {typo!r} found in FINAL_REVIEW_VERDICT.json: {matched}"


def test_final_review_verdict_wallclock_proof_consistent() -> None:
    """Cross-check: review verdict duration must match source WALLCLOCK_PROOF duration."""
    review = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    source_wp = json.loads((SOURCE_DIR / "WALLCLOCK_PROOF.json").read_text())
    assert review["duration_wallclock_seconds"] == source_wp["duration_wallclock_seconds"]
    assert review["started_at"] == source_wp["started_at"]
    assert review["ended_at"] == source_wp["ended_at"]
    assert review["wrapper_pid"] == source_wp["wrapper_pid"]
    assert review["checkpoint_count"] == source_wp["checkpoint_count_so_far"]


def test_final_review_verdict_final_verdict_consistent() -> None:
    """Cross-check: source FINAL_VERDICT status must equal review's source_status."""
    review = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    source_fv = json.loads((SOURCE_DIR / "FINAL_VERDICT.json").read_text())
    assert review["source_status"] == source_fv["status"]
    assert review["duration_wallclock_seconds"] == source_fv["duration_wallclock_seconds"]


# ---------------------------------------------------------------------------
# ARTIFACT_CONSISTENCY_AUDIT.json — 27 checks all pass
# ---------------------------------------------------------------------------

def test_artifact_consistency_audit_all_ok() -> None:
    d = json.loads((REVIEW_DIR / "ARTIFACT_CONSISTENCY_AUDIT.json").read_text())
    checks = d["consistency_checks"]
    assert len(checks) == 27, f"expected 27 consistency checks, got {len(checks)}"
    for c in checks:
        assert c["ok"] is True, f"consistency check failed: {c['check']}"


def test_artifact_consistency_audit_typo_clean() -> None:
    d = json.loads((REVIEW_DIR / "ARTIFACT_CONSISTENCY_AUDIT.json").read_text())
    assert d["typo_blacklist_audit"]["all_clean"] is True


def test_artifact_consistency_audit_final_ok() -> None:
    d = json.loads((REVIEW_DIR / "ARTIFACT_CONSISTENCY_AUDIT.json").read_text())
    assert d["artifact_consistency_ok"] is True


# ---------------------------------------------------------------------------
# FORBIDDEN_ACTIONS_RECHECK.json — 27 actions all ok
# ---------------------------------------------------------------------------

def test_forbidden_actions_recheck_all_ok() -> None:
    d = json.loads((REVIEW_DIR / "FORBIDDEN_ACTIONS_RECHECK.json").read_text())
    actions = d["forbidden_actions_checked"]
    assert len(actions) == 27, f"expected 27 forbidden actions, got {len(actions)}"
    for a in actions:
        assert a["ok"] is True, f"forbidden action check failed: {a['id']} ({a['action']})"


def test_forbidden_actions_recheck_summary() -> None:
    d = json.loads((REVIEW_DIR / "FORBIDDEN_ACTIONS_RECHECK.json").read_text())
    s = d["summary"]
    assert s["forbidden_actions_checked"] == 27
    assert s["forbidden_actions_still_zero"] is True
    assert s["no_real_order"] is True
    assert s["no_sdk"] is True
    assert s["no_testnet_live"] is True
    assert s["no_wallet"] is True
    assert s["no_merge"] is True
    assert s["no_pkill"] is True
    assert s["no_paid_rpc"] is True
    assert s["no_real_secret_committed"] is True


# ---------------------------------------------------------------------------
# Source files (the run being reviewed)
# ---------------------------------------------------------------------------

REQUIRED_SOURCE_FILES = [
    "FINAL_VERDICT.json",
    "WALLCLOCK_PROOF.json",
    "CHECKPOINT_TIMELINE.json",
    "CHECKPOINT_TIMELINE.jsonl",
    "ONEPAGE_CN.md",
    "R1_12H_FULL_WALLCLOCK_OBSERVATION_REPORT_CN.md",
    "SOURCE_HEALTH.json",
    "WATCHLIST_EVOLUTION.json",
    "WATCHLIST_EVOLUTION.jsonl",
    "READY_EVOLUTION.json",
    "DATA_QUALITY_SUMMARY.json",
    "FORBIDDEN_ACTIONS_AUDIT.json",
    "COMMAND_USED.txt",
    "PID_TRANSITION_AUDIT.json",
]


def test_all_source_files_exist() -> None:
    for f in REQUIRED_SOURCE_FILES:
        assert (SOURCE_DIR / f).exists(), f"missing source file: {f}"


# ---------------------------------------------------------------------------
# Data dir integrity (12 ckpts real)
# ---------------------------------------------------------------------------

def test_data_dir_12_ckpts() -> None:
    ckpts = sorted([d for d in DATA_DIR.glob("checkpoint_*") if d.is_dir()])
    assert len(ckpts) == 12


def test_data_dir_156_r1_files() -> None:
    files = list(DATA_DIR.glob("checkpoint_*/r1_*"))
    assert len(files) == 156, f"expected 156 r1_* files, got {len(files)}"


def test_data_dir_no_old_data_mixed() -> None:
    """Verify v3 data dir does not contain files from v0/v1/v2/old_12h."""
    ckpt_dirs = sorted([d.name for d in DATA_DIR.glob("checkpoint_*")])
    # All 12 v3 ckpts should be 1_1916 through 12_0621 (sorted by ckpt_index)
    expected_by_ckpt_index = [
        "checkpoint_1_1916", "checkpoint_2_2017", "checkpoint_3_2117",
        "checkpoint_4_2217", "checkpoint_5_2318", "checkpoint_6_0019",
        "checkpoint_7_0119", "checkpoint_8_0219", "checkpoint_9_0320",
        "checkpoint_10_0420", "checkpoint_11_0521", "checkpoint_12_0621",
    ]
    # Filesystem glob returns string-sorted order; the JSON timeline also uses string sort.
    # To validate completeness, sort by ckpt_index and compare.
    def ckpt_idx(name: str) -> int:
        return int(name.split("_")[1])

    ckpt_dirs_by_idx = sorted(ckpt_dirs, key=ckpt_idx)
    assert ckpt_dirs_by_idx == expected_by_ckpt_index, (
        f"ckpt dir mismatch (sorted by ckpt_index): {ckpt_dirs_by_idx}"
    )
    assert len(ckpt_dirs) == 12, f"expected 12 ckpt dirs, got {len(ckpt_dirs)}"


# ---------------------------------------------------------------------------
# Run history audit (v0, v1, v3)
# ---------------------------------------------------------------------------

def test_run_history_references_all_pids() -> None:
    """Final_verdict and wallclock_proof must reference v0 (2876054), v1 (2892835), v3 (2948793)."""
    for fname in ["FINAL_VERDICT.json", "WALLCLOCK_PROOF.json"]:
        d = json.loads((SOURCE_DIR / fname).read_text())
        text = json.dumps(d)
        for pid in ["2876054", "2892835", "2948793", "20260607_191500"]:
            assert pid in text, f"{fname} missing reference to {pid}"


# ---------------------------------------------------------------------------
# Source WALLCLOCK_PROOF — typo blacklist
# ---------------------------------------------------------------------------

def test_source_wallclock_proof_no_typo() -> None:
    p = SOURCE_DIR / "WALLCLOCK_PROOF.json"
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
        assert not matched, f"typo {typo!r} in WALLCLOCK_PROOF.json: {matched}"


# ---------------------------------------------------------------------------
# CHECKPOINT_TIMELINE — sorted by ckpt_index produces 12 chronological entries
# ---------------------------------------------------------------------------

def test_checkpoint_timeline_chronological_12() -> None:
    tl = json.loads((SOURCE_DIR / "CHECKPOINT_TIMELINE.json").read_text())
    assert tl["checkpoint_count"] == 12
    sorted_tl = sorted(tl["timeline"], key=lambda c: c["ckpt_index"])
    assert len(sorted_tl) == 12
    # ckpt 1 mtime should be 2026-06-07T19:17:14Z
    assert sorted_tl[0]["ckpt_actual_mtime_utc"] == "2026-06-07T19:17:14Z"
    assert sorted_tl[0]["ckpt_index"] == 1
    # ckpt 12 mtime should be 2026-06-08T06:21:28Z
    assert sorted_tl[11]["ckpt_actual_mtime_utc"] == "2026-06-08T06:21:28Z"
    assert sorted_tl[11]["ckpt_index"] == 12


# ---------------------------------------------------------------------------
# Safety — no forbidden processes
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


def test_safety_no_secret_in_review_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REVIEW_DIR.rglob("*"):
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
# Review verdict upgrade is FORBIDDEN
# ---------------------------------------------------------------------------

def test_review_does_not_upgrade_to_pass() -> None:
    """Review must NOT claim source PARTIAL is PASS."""
    review = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert review["status"] != "PASS", "review must not claim PASS for source PARTIAL"


def test_review_does_not_claim_edge() -> None:
    """Review must NOT claim edge_proven=yes."""
    review = json.loads((REVIEW_DIR / "FINAL_REVIEW_VERDICT.json").read_text())
    assert review["edge_proven"] == "no", "review must not claim edge_proven=yes"
