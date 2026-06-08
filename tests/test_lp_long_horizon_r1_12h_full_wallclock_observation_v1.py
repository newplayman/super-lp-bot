"""Tests for LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1.

Verifies:
  - All CLEAN field names exist in WALLCLOCK_PROOF.json
  - NO typo / corrupted field names exist (blacklist)
  - status is in {PASS, WARN, FAIL, PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION}
  - duration_wallclock_seconds >= 43200 if status == PASS
  - duration_wallclock_seconds_ok == (duration_wallclock_seconds >= 43200)
  - v0 (pid 2876054) and v1 (RUN_ID 20260607_184500) PARTIAL_WALLCLOCK_FAIL referenced
  - scheduler_mode is valid
  - 12/12 checkpoints completed
  - forbidden actions = 0
  - LOCKED fields maintained

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_r1_12h_full_wallclock_observation" / "20260607_191500"
DATA_DIR = ROOT / "data" / "lp_long_horizon_r1_12h_full_wallclock" / "20260607_191500"
V1_PARTIAL = ROOT / "reports" / "lp_long_horizon_r1_12h_full_wallclock_observation" / "20260607_184500" / "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION.json"

ALLOWED_STATUSES = {"PASS", "WARN", "FAIL", "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"}
ALLOWED_SCHEDULER_MODES = {"completion_anchored_sleep_3600", "start_ts_anchored_interval_3600"}
TYPO_BLACKLIST = [
    "CWALLCLICK_PROOF",
    "checkpointPinterval_drift_srconds",
    "finalize_aftertexpscaed_end",
    "cheartbeat_index",
    "stt_us",
]
REQUIRED_CLEAN_FIELDS = [
    "status", "run_id", "started_at", "ended_at",
    "duration_wallclock_seconds", "duration_wallclock_seconds_ok",
    "scheduler_mode", "checkpoint_count_so_far",
    "checkpoint_actual_timestamps", "checkpoint_actual_intervals_seconds",
    "max_checkpoint_interval_drift_seconds", "finalize_after_expected_end",
    "compressed", "short_supervisor_used", "full_supervisor_used",
    "wrapper_pid", "child_supervisor_pid",
    "data_dir", "report_dir", "command_used", "forbidden_actions_still_zero",
]


# ---------------------------------------------------------------------------
# Deliverables exist
# ---------------------------------------------------------------------------

def test_all_deliverables_exist() -> None:
    files = [
        "FINAL_VERDICT.json", "ONEPAGE_CN.md", "R1_12H_FULL_WALLCLOCK_OBSERVATION_REPORT_CN.md",
        "SOURCE_HEALTH.json",
        "WATCHLIST_EVOLUTION.json", "WATCHLIST_EVOLUTION.jsonl",
        "READY_EVOLUTION.json", "READY_EVOLUTION.jsonl",
        "DATA_QUALITY_SUMMARY.json",
        "CHECKPOINT_TIMELINE.json", "CHECKPOINT_TIMELINE.jsonl",
        "FORBIDDEN_ACTIONS_AUDIT.json",
        "COMMAND_USED.txt",
        "WALLCLOCK_PROOF.json",
    ]
    for f in files:
        assert (REPORT_DIR / f).exists(), f"missing deliverable: {f}"


# ---------------------------------------------------------------------------
# WALLCLOCK_PROOF.json — clean field names
# ---------------------------------------------------------------------------

def test_wallclock_proof_clean_fields_exist() -> None:
    p = REPORT_DIR / "WALLCLOCK_PROOF.json"
    d = json.loads(p.read_text())
    missing = [f for f in REQUIRED_CLEAN_FIELDS if f not in d]
    assert not missing, f"WALLCLOCK_PROOF.json missing required clean fields: {missing}"


def test_wallclock_proof_no_typo_field_names() -> None:
    """Assert NO typo / corrupted field names exist anywhere in WALLCLOCK_PROOF.json."""
    p = REPORT_DIR / "WALLCLOCK_PROOF.json"
    text = p.read_text()
    raw = json.loads(text)
    # Walk all key paths
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
        assert not matched, f"typo '{typo}' found in WALLCLOCK_PROOF.json keys: {matched}"


def test_wallclock_proof_status_in_allowed_set() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    assert d["status"] in ALLOWED_STATUSES, (
        f"status {d['status']!r} not in {ALLOWED_STATUSES}"
    )


def test_wallclock_proof_pass_requires_duration_43200() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    if d["status"] == "PASS":
        assert d["duration_wallclock_seconds"] >= 43200, (
            f"status=PASS but duration_wallclock_seconds={d['duration_wallclock_seconds']} < 43200"
        )
    if d["duration_wallclock_seconds"] >= 43200:
        assert d["status"] != "FAIL", (
            f"duration_wallclock_seconds >= 43200 but status=FAIL"
        )


def test_wallclock_proof_duration_ok_field_consistent() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    expected_ok = d["duration_wallclock_seconds"] >= 43200
    assert d["duration_wallclock_seconds_ok"] is expected_ok, (
        f"duration_wallclock_seconds_ok={d['duration_wallclock_seconds_ok']} but "
        f"duration_wallclock_seconds={d['duration_wallclock_seconds']} >= 43200 ? {expected_ok}"
    )


def test_wallclock_proof_scheduler_mode_valid() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    assert d["scheduler_mode"] in ALLOWED_SCHEDULER_MODES, (
        f"scheduler_mode {d['scheduler_mode']!r} not in {ALLOWED_SCHEDULER_MODES}"
    )


def test_wallclock_proof_12_ckpt_completed() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    assert d["checkpoint_count_so_far"] == 12


def test_wallclock_proof_intervals_have_11_entries() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    intervals = d["checkpoint_actual_intervals_seconds"]
    assert len(intervals) == 11, f"expected 11 intervals (12 ckpt - 1), got {len(intervals)}"
    for i in intervals:
        # intervals should be ~3600s (3600 + collector overhead, max drift small)
        assert 3500 <= i <= 3700, f"interval {i} out of expected range [3500, 3700]"


def test_wallclock_proof_max_drift_reasonable() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    max_drift = d["max_checkpoint_interval_drift_seconds"]
    assert max_drift <= 200, f"max_checkpoint_interval_drift_seconds={max_drift} too large"


def test_wallclock_proof_full_supervisor_no_compress() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    assert d["full_supervisor_used"] is True
    assert d["short_supervisor_used"] is False
    assert d["compressed"] is False


def test_wallclock_proof_run_history_audit() -> None:
    d = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    audit = d.get("run_history_audit", {})
    # Must reference v0 (pid 2876054) and v1 (pid 2892835)
    assert "2876054" in str(audit), "v0 (pid 2876054) not referenced in run_history_audit"
    assert "2892835" in str(audit), "v1 (pid 2892835) not referenced in run_history_audit"


# ---------------------------------------------------------------------------
# FINAL_VERDICT.json — no_typo + locked fields
# ---------------------------------------------------------------------------

def test_final_verdict_no_typo_field_names() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    raw = json.loads(p.read_text())
    text = p.read_text()
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
        assert not matched, f"typo '{typo}' found in FINAL_VERDICT.json: {matched}"


def test_final_verdict_locked_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["auto_advance_to_24h"] is False
    assert fv["longer_stage_started"] is False
    assert fv["actual_fee_data_available"] is False
    assert fv["fee_proxy_only"] is True


def test_final_verdict_pass_requires_duration_43200() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    if fv["status"] == "PASS":
        assert fv["duration_wallclock_seconds"] >= 43200


# ---------------------------------------------------------------------------
# CHECKPOINT_TIMELINE — actual file mtimes + supervisor log timestamps
# ---------------------------------------------------------------------------

def test_checkpoint_timeline_12_ckpts() -> None:
    tl = json.loads((REPORT_DIR / "CHECKPOINT_TIMELINE.json").read_text())
    assert tl["checkpoint_count"] == 12
    assert len(tl["timeline"]) == 12


def test_checkpoint_timeline_real_timestamps() -> None:
    """Timestamps must be from actual file mtimes or supervisor log (NOT estimated)."""
    tl = json.loads((REPORT_DIR / "CHECKPOINT_TIMELINE.json").read_text())
    for c in tl["timeline"]:
        # Every ckpt has ckpt_actual_mtime_utc (real)
        assert "ckpt_actual_mtime_utc" in c
        assert c["ckpt_actual_mtime_utc"].endswith("Z")


def test_checkpoint_timeline_jsonl_matches_json() -> None:
    j = json.loads((REPORT_DIR / "CHECKPOINT_TIMELINE.json").read_text())
    lines = (REPORT_DIR / "CHECKPOINT_TIMELINE.jsonl").read_text().strip().split("\n")
    assert len(lines) == 12
    for i, line in enumerate(lines):
        d = json.loads(line)
        assert d["ckpt_index"] == j["timeline"][i]["ckpt_index"]


# ---------------------------------------------------------------------------
# v0 + v1 history references
# ---------------------------------------------------------------------------

def test_v1_partial_verdict_referenced() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    wp = json.loads((REPORT_DIR / "WALLCLOCK_PROOF.json").read_text())
    # Either final verdict or wallclock proof mentions v1 / 20260607_184500
    combined = json.dumps(fv) + json.dumps(wp)
    assert "20260607_184500" in combined or "2892835" in combined, (
        "v1 partial verdict reference missing from final artifacts"
    )


def test_v1_partial_file_exists() -> None:
    assert V1_PARTIAL.exists(), f"v1 PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION.json missing at {V1_PARTIAL}"
    v1 = json.loads(V1_PARTIAL.read_text())
    assert v1["verdict"] == "PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION"


# ---------------------------------------------------------------------------
# Source health (honest record)
# ---------------------------------------------------------------------------

def test_source_health_no_fake_data() -> None:
    sh = json.loads((REPORT_DIR / "SOURCE_HEALTH.json").read_text())
    assert sh["no_fake_data_injection"] is True
    assert sh["chains_skipped"] == ["base"]


# ---------------------------------------------------------------------------
# Data dir integrity (12 ckpts real)
# ---------------------------------------------------------------------------

def test_data_dir_12_ckpts() -> None:
    ckpts = sorted([d for d in DATA_DIR.glob("checkpoint_*") if d.is_dir()])
    assert len(ckpts) == 12


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


def test_safety_no_secret_in_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REPORT_DIR.rglob("*"):
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
