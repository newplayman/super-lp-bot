#!/usr/bin/env python3
"""Finalize / status reporter for lp_bsc_fee_velocity_overnight runs.

Read-only by contract:
- No wallet, signer, keystore, or tx-broadcast symbols anywhere in this file.
- No outbound network calls. The only side effects are writes to the report
  directory the caller passes in.
- Never overwrites final/FINAL_VERDICT.json unless --overwrite-final is passed
  AND the runner process is not active AND data CSVs have rows.

Usage:
    python3 scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py \
        --run-id 20260601_185436 \
        --report-dir reports/lp_bsc_fee_velocity_overnight/20260601_185436 \
        --mode auto

Modes:
    auto              Decide between running / partial / complete based on
                      live process check + checkpoint progress (default).
    running           Force running branch (do not write any final).
    partial           Force partial branch.
    complete          Force complete branch (allowed only with --overwrite-final).

Branches:
    running           → RUNNING_STATUS.json + RUNNING_STATUS_CN.md
                        recommended_next_stage = WAIT_FOR_OVERNIGHT_COMPLETION
    partial           → PARTIAL_FINAL_VERDICT.json
                        recommended_next_stage = LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT
    complete          → final/FINAL_VERDICT_REBUILT.json + FINAL_AUTHORITY_REBUILT_CN.md
                        recommended_next_stage = LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1
                        (still requires data CSVs to have rows; otherwise downgrades to partial)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


ALLOWED_NEXT_STAGES = {
    "WAIT_FOR_OVERNIGHT_COMPLETION",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


@dataclass
class ProcessStatus:
    tmux_session_active: bool = False
    runner_process_active: bool = False
    runner_pid: Optional[int] = None
    runner_user: Optional[str] = None
    status_source: str = "local_vps_process_check"
    process_check_error: Optional[str] = None


@dataclass
class CheckpointAudit:
    selected_pool_count: int = 0
    pool_count: int = 0
    windows: list = field(default_factory=list)
    window_count: int = 0
    expected_target_count: int = 0
    completed_target_count: int = 0
    remaining_target_count: int = 0
    progress_pct: float = 0.0
    last_checkpoint_at_unix: Optional[int] = None
    latest_block: Optional[int] = None
    is_completed: bool = False


@dataclass
class DataStatus:
    pool_fee_velocity_row_count: int = 0
    swap_logs_decoded_row_count: int = 0
    pool_fee_velocity_exists: bool = False
    swap_logs_decoded_exists: bool = False
    @property
    def has_rows(self) -> bool:
        return self.pool_fee_velocity_row_count > 0 or self.swap_logs_decoded_row_count > 0


@dataclass
class FinalStatus:
    final_exists: bool = False
    final_mtime_unix: Optional[int] = None
    final_status: Optional[str] = None
    final_selected_pool_count: Optional[int] = None
    final_is_current: bool = False
    final_is_stale_or_unverified: bool = True


def _read_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _count_csv_rows(path: Path) -> int:
    """Count non-header rows in a CSV file. Returns 0 if missing or header-only."""
    if not path.is_file():
        return 0
    try:
        with path.open(newline="") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
        if not rows:
            return 0
        # First row is the header.
        return max(0, len(rows) - 1)
    except OSError:
        return 0


def _mtime_or_none(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    return int(path.stat().st_mtime)


def check_process_status(run_id: str) -> ProcessStatus:
    status = ProcessStatus()
    # Process check via ps — works regardless of which tmux daemon owns the session.
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,user,cmd"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout
        pattern = re.compile(rf"\b(lp_bsc_fee_velocity_overnight_runner|lp_bsc_fee_velocity_overnight_backfill).*\b{re.escape(run_id)}\b")
        match_pid = None
        match_user = None
        for line in out.splitlines():
            stripped = line.strip()
            if "grep " in stripped:
                continue
            if pattern.search(stripped):
                parts = stripped.split(None, 2)
                if len(parts) >= 3:
                    try:
                        match_pid = int(parts[0])
                    except ValueError:
                        match_pid = None
                    match_user = parts[1]
                    break
        if match_pid is not None:
            status.runner_process_active = True
            status.runner_pid = match_pid
            status.runner_user = match_user
    except (subprocess.SubprocessError, OSError) as exc:
        status.process_check_error = f"ps_failed:{type(exc).__name__}"
    # tmux check is best-effort — across users we may not see the session,
    # but the ps result is what governs the final-authority decision.
    try:
        tmux_out = subprocess.run(
            ["tmux", "ls"], check=False, capture_output=True, text=True, timeout=5,
        ).stdout
        if f"lp_bsc_fee_velocity_overnight_{run_id}" in tmux_out:
            status.tmux_session_active = True
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        pass
    # If ps says a runner process is alive, declare tmux active even if our
    # uid can't see the deploy-owned session — the runner process tree is
    # definitive evidence the supervising tmux exists.
    if status.runner_process_active and not status.tmux_session_active:
        status.tmux_session_active = True
    return status


def audit_checkpoint(report_dir: Path) -> CheckpointAudit:
    state_path = report_dir / "checkpoint" / "state.json"
    state = _read_json(state_path) or {}
    pool_count = int(state.get("pool_count", 0) or 0)
    selected_pool_count = int(state.get("selected_pool_count", 0) or 0)
    windows = list(state.get("windows", []) or [])
    window_count = len(windows)
    expected = pool_count * window_count
    completed_targets = state.get("completed_targets") or []
    completed = len(completed_targets)
    remaining = max(0, expected - completed)
    progress_pct = round(100.0 * completed / expected, 2) if expected else 0.0
    return CheckpointAudit(
        selected_pool_count=selected_pool_count,
        pool_count=pool_count,
        windows=windows,
        window_count=window_count,
        expected_target_count=expected,
        completed_target_count=completed,
        remaining_target_count=remaining,
        progress_pct=progress_pct,
        last_checkpoint_at_unix=state.get("last_checkpoint_at"),
        latest_block=state.get("latest_block"),
        is_completed=(expected > 0 and completed == expected),
    )


def audit_data(report_dir: Path) -> DataStatus:
    fv = report_dir / "data" / "pool_fee_velocity.csv"
    sl = report_dir / "data" / "swap_logs_decoded.csv"
    return DataStatus(
        pool_fee_velocity_exists=fv.is_file(),
        swap_logs_decoded_exists=sl.is_file(),
        pool_fee_velocity_row_count=_count_csv_rows(fv),
        swap_logs_decoded_row_count=_count_csv_rows(sl),
    )


def audit_final(report_dir: Path, checkpoint: CheckpointAudit, runner_active: bool) -> FinalStatus:
    fp = report_dir / "final" / "FINAL_VERDICT.json"
    status = FinalStatus(final_exists=fp.is_file())
    if not status.final_exists:
        return status
    status.final_mtime_unix = _mtime_or_none(fp)
    data = _read_json(fp) or {}
    status.final_status = data.get("status")
    status.final_selected_pool_count = data.get("selected_pool_count")
    # Staleness rules (from Phase G).
    final_contradicts_checkpoint = (
        status.final_selected_pool_count is not None
        and checkpoint.selected_pool_count > 0
        and status.final_selected_pool_count != checkpoint.selected_pool_count
    )
    final_older_than_checkpoint = (
        status.final_mtime_unix is not None
        and checkpoint.last_checkpoint_at_unix is not None
        and status.final_mtime_unix < checkpoint.last_checkpoint_at_unix
    )
    if runner_active or final_contradicts_checkpoint or final_older_than_checkpoint or not checkpoint.is_completed:
        status.final_is_current = False
        status.final_is_stale_or_unverified = True
    else:
        status.final_is_current = True
        status.final_is_stale_or_unverified = False
    return status


def decide_mode(
    requested: str,
    proc: ProcessStatus,
    checkpoint: CheckpointAudit,
    data: DataStatus,
    overwrite_final_requested: bool,
) -> tuple[str, str]:
    """Return (resolved_mode, reason)."""
    if requested in {"running", "partial", "complete"}:
        if requested == "complete" and proc.runner_process_active:
            return ("running", "explicit_complete_overridden_runner_still_active")
        if requested == "complete" and not checkpoint.is_completed:
            return ("partial", "explicit_complete_overridden_checkpoint_not_completed")
        if requested == "complete" and not data.has_rows:
            return ("partial", "explicit_complete_overridden_data_csvs_empty")
        if requested == "complete" and not overwrite_final_requested:
            return ("partial", "explicit_complete_requires_overwrite_final_flag")
        return (requested, f"explicit_{requested}")
    # auto
    if proc.runner_process_active:
        return ("running", "auto_runner_active")
    if not checkpoint.is_completed:
        return ("partial", "auto_runner_inactive_checkpoint_partial")
    if not data.has_rows:
        return ("partial", "auto_completed_but_data_csvs_empty")
    if not overwrite_final_requested:
        return ("partial", "auto_completed_but_overwrite_final_not_requested")
    return ("complete", "auto_runner_inactive_checkpoint_complete_data_available")


def write_running_status(
    report_dir: Path,
    run_id: str,
    proc: ProcessStatus,
    checkpoint: CheckpointAudit,
    data: DataStatus,
    final: FinalStatus,
    reason: str,
) -> dict:
    payload = {
        "stage": "LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1",
        "branch": "running",
        "run_id": run_id,
        "decision_reason": reason,
        "tmux_session_active": proc.tmux_session_active,
        "runner_process_active": proc.runner_process_active,
        "runner_pid": proc.runner_pid,
        "runner_user": proc.runner_user,
        "checkpoint_selected_pool_count": checkpoint.selected_pool_count,
        "checkpoint_pool_count": checkpoint.pool_count,
        "completed_target_count": checkpoint.completed_target_count,
        "expected_target_count": checkpoint.expected_target_count,
        "progress_pct": checkpoint.progress_pct,
        "pool_fee_velocity_row_count": data.pool_fee_velocity_row_count,
        "swap_logs_decoded_row_count": data.swap_logs_decoded_row_count,
        "final_exists": final.final_exists,
        "final_is_current": final.final_is_current,
        "final_is_stale_or_unverified": final.final_is_stale_or_unverified,
        "authoritative_status_source": "checkpoint_and_run_log",
        "final_overwritten": False,
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "can_run_probe_now": False,
        "wallet_or_tx_touched": False,
        "recommended_next_stage": "WAIT_FOR_OVERNIGHT_COMPLETION",
    }
    (report_dir / "RUNNING_STATUS.json").write_text(json.dumps(payload, indent=2) + "\n")
    md = [
        "# Overnight Run 当前运行状态（RUNNING）",
        "",
        f"- run_id: `{run_id}`",
        f"- decision_reason: `{reason}`",
        f"- tmux_session_active: `{proc.tmux_session_active}`",
        f"- runner_process_active: `{proc.runner_process_active}`",
        f"- runner_pid: `{proc.runner_pid}`",
        f"- runner_user: `{proc.runner_user}`",
        "",
        "## 进度",
        "",
        f"- selected_pool_count: `{checkpoint.selected_pool_count}`",
        f"- pool_count: `{checkpoint.pool_count}`",
        f"- completed / expected: `{checkpoint.completed_target_count} / {checkpoint.expected_target_count}`",
        f"- progress_pct: `{checkpoint.progress_pct}%`",
        f"- pool_fee_velocity rows: `{data.pool_fee_velocity_row_count}`",
        f"- swap_logs_decoded rows: `{data.swap_logs_decoded_row_count}`",
        "",
        "## final 状态",
        "",
        f"- final_exists: `{final.final_exists}`",
        f"- final_is_current: `{final.final_is_current}`",
        f"- final_is_stale_or_unverified: `{final.final_is_stale_or_unverified}`",
        f"- authoritative_status_source: `checkpoint_and_run_log`",
        f"- final_overwritten_this_run: `False`",
        "",
        "## 下一步",
        "",
        "```text",
        "recommended_next_stage = WAIT_FOR_OVERNIGHT_COMPLETION",
        "```",
        "",
        "runner 仍在跑；不覆盖 final/FINAL_VERDICT.json；不发交易；不允许 probe / canary / live / paper。",
    ]
    (report_dir / "RUNNING_STATUS_CN.md").write_text("\n".join(md) + "\n")
    return payload


def write_partial_verdict(
    report_dir: Path,
    run_id: str,
    proc: ProcessStatus,
    checkpoint: CheckpointAudit,
    data: DataStatus,
    final: FinalStatus,
    reason: str,
) -> dict:
    payload = {
        "stage": "LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1",
        "branch": "partial",
        "status": "WARN",
        "run_id": run_id,
        "decision_reason": reason,
        "tmux_session_active": proc.tmux_session_active,
        "runner_process_active": proc.runner_process_active,
        "checkpoint_selected_pool_count": checkpoint.selected_pool_count,
        "checkpoint_pool_count": checkpoint.pool_count,
        "completed_target_count": checkpoint.completed_target_count,
        "expected_target_count": checkpoint.expected_target_count,
        "progress_pct": checkpoint.progress_pct,
        "pool_fee_velocity_row_count": data.pool_fee_velocity_row_count,
        "swap_logs_decoded_row_count": data.swap_logs_decoded_row_count,
        "final_exists": final.final_exists,
        "final_is_current": False,
        "final_is_stale_or_unverified": True,
        "authoritative_status_source": "checkpoint_partial",
        "final_overwritten": False,
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "can_run_probe_now": False,
        "wallet_or_tx_touched": False,
        "recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT",
    }
    (report_dir / "PARTIAL_FINAL_VERDICT.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def write_rebuilt_final(
    report_dir: Path,
    run_id: str,
    proc: ProcessStatus,
    checkpoint: CheckpointAudit,
    data: DataStatus,
    final: FinalStatus,
    reason: str,
) -> dict:
    rebuilt = {
        "stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_REBUILD_V1",
        "branch": "complete",
        "status": "PASS",
        "run_id": run_id,
        "decision_reason": reason,
        "selected_pool_count": checkpoint.selected_pool_count,
        "pool_count": checkpoint.pool_count,
        "expected_target_count": checkpoint.expected_target_count,
        "completed_target_count": checkpoint.completed_target_count,
        "windows_completed": list(checkpoint.windows),
        "pool_fee_velocity_row_count": data.pool_fee_velocity_row_count,
        "swap_logs_decoded_row_count": data.swap_logs_decoded_row_count,
        "rebuilt_from": ["data/pool_fee_velocity.csv", "data/swap_logs_decoded.csv", "checkpoint/state.json"],
        "authoritative_status_source": "completed_checkpoint_and_data",
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "can_run_probe_now": False,
        "wallet_or_tx_touched": False,
        "recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    }
    final_dir = report_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "FINAL_VERDICT_REBUILT.json").write_text(json.dumps(rebuilt, indent=2) + "\n")
    md = [
        "# Final 权威已重建（FINAL_AUTHORITY_REBUILT）",
        "",
        f"- run_id: `{run_id}`",
        f"- decision_reason: `{reason}`",
        f"- checkpoint_selected_pool_count: `{checkpoint.selected_pool_count}`",
        f"- completed / expected: `{checkpoint.completed_target_count} / {checkpoint.expected_target_count}`",
        f"- data rows: `{data.pool_fee_velocity_row_count}` pool_fee_velocity, `{data.swap_logs_decoded_row_count}` swap_logs_decoded",
        "",
        "重建文件: `final/FINAL_VERDICT_REBUILT.json`",
        "",
        "本脚本不覆盖原 `final/FINAL_VERDICT.json`；如需替换，须手工 review 后另外操作。",
    ]
    (report_dir / "FINAL_AUTHORITY_REBUILT_CN.md").write_text("\n".join(md) + "\n")
    return rebuilt


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize / status reporter for lp_bsc_fee_velocity_overnight runs.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--mode", default="auto", choices=["auto", "running", "partial", "complete"])
    parser.add_argument("--overwrite-final", action="store_true",
                        help="Allow the complete branch to write final/FINAL_VERDICT_REBUILT.json. "
                             "Original final/FINAL_VERDICT.json is NEVER overwritten by this script.")
    args = parser.parse_args(argv)

    report_dir: Path = args.report_dir
    if not report_dir.is_dir():
        print(f"ERROR: report dir does not exist: {report_dir}", file=sys.stderr)
        return 2

    proc = check_process_status(args.run_id)
    checkpoint = audit_checkpoint(report_dir)
    data = audit_data(report_dir)
    final = audit_final(report_dir, checkpoint, runner_active=proc.runner_process_active)

    resolved_mode, reason = decide_mode(args.mode, proc, checkpoint, data, args.overwrite_final)

    if resolved_mode == "running":
        payload = write_running_status(report_dir, args.run_id, proc, checkpoint, data, final, reason)
    elif resolved_mode == "partial":
        payload = write_partial_verdict(report_dir, args.run_id, proc, checkpoint, data, final, reason)
    elif resolved_mode == "complete":
        payload = write_rebuilt_final(report_dir, args.run_id, proc, checkpoint, data, final, reason)
    else:
        print(f"ERROR: unreachable mode: {resolved_mode}", file=sys.stderr)
        return 2

    if payload["recommended_next_stage"] not in ALLOWED_NEXT_STAGES:
        print(f"ERROR: recommended_next_stage {payload['recommended_next_stage']!r} not in allowed set", file=sys.stderr)
        return 2

    print(json.dumps({
        "branch": resolved_mode,
        "decision_reason": reason,
        "tmux_session_active": proc.tmux_session_active,
        "runner_process_active": proc.runner_process_active,
        "completed_target_count": checkpoint.completed_target_count,
        "expected_target_count": checkpoint.expected_target_count,
        "final_is_current": final.final_is_current,
        "final_is_stale_or_unverified": final.final_is_stale_or_unverified,
        "recommended_next_stage": payload["recommended_next_stage"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
