"""Tests for scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py.

These tests run hermetically: each builds a synthetic report dir in a tmp
path, invokes the finalizer module's pure functions directly (so no real
process check is needed), and asserts the four decision branches plus the
read-only safety invariants.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "finalize_bsc_fee_velocity_overnight_run_v1_readonly.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("finalize_bsc_fee_velocity_overnight_run_v1_readonly", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


finalize = _load_module()


def _make_report_dir(
    tmp_path: Path,
    *,
    final_selected_pool_count: int = 0,
    final_status: str = "FAIL",
    final_mtime: int | None = None,
    checkpoint_selected_pool_count: int = 8,
    checkpoint_pool_count: int = 8,
    completed_targets: int = 34,
    windows: list[str] | None = None,
    last_checkpoint_at: int = 1780374291,
    pool_fee_velocity_rows: int = 0,
    swap_logs_decoded_rows: int = 0,
    run_log_lines: int = 70,
) -> Path:
    """Build a synthetic run report dir with controllable invariants."""
    windows = windows or ["24h", "72h", "7d", "14d", "30d"]
    rd = tmp_path / "report"
    (rd / "final").mkdir(parents=True)
    (rd / "checkpoint").mkdir()
    (rd / "data").mkdir()
    (rd / "logs").mkdir()

    final_path = rd / "final" / "FINAL_VERDICT.json"
    final_path.write_text(json.dumps({
        "status": final_status,
        "selected_pool_count": final_selected_pool_count,
        "swap_log_count": 0,
        "fee_ready_pool_count": 0,
    }))
    if final_mtime is not None:
        import os
        os.utime(final_path, (final_mtime, final_mtime))

    state_path = rd / "checkpoint" / "state.json"
    targets = [f"0xpool{i}|{w}" for i in range(checkpoint_pool_count) for w in windows][:completed_targets]
    state_path.write_text(json.dumps({
        "run_id": "20260601_185436",
        "pool_count": checkpoint_pool_count,
        "selected_pool_count": checkpoint_selected_pool_count,
        "windows": windows,
        "completed_targets": targets,
        "last_checkpoint_at": last_checkpoint_at,
        "latest_block": 101743639,
    }))

    fv_path = rd / "data" / "pool_fee_velocity.csv"
    fv_lines = ["run_id,pool_id"] + [f"r,{i}" for i in range(pool_fee_velocity_rows)]
    fv_path.write_text("\n".join(fv_lines) + "\n")

    sl_path = rd / "data" / "swap_logs_decoded.csv"
    sl_lines = ["run_id,pool_id"] + [f"r,{i}" for i in range(swap_logs_decoded_rows)]
    sl_path.write_text("\n".join(sl_lines) + "\n")

    log_path = rd / "logs" / "run.log"
    log_path.write_text("\n".join(f"[2026-06-01T19:13:{i:02d}Z] line {i}" for i in range(run_log_lines)) + "\n")
    return rd


@pytest.fixture
def runner_active():
    """Force ProcessStatus to report runner_process_active=True."""
    with mock.patch.object(finalize, "check_process_status", return_value=finalize.ProcessStatus(
        tmux_session_active=True,
        runner_process_active=True,
        runner_pid=12345,
        runner_user="deploy",
    )):
        yield


@pytest.fixture
def runner_inactive():
    with mock.patch.object(finalize, "check_process_status", return_value=finalize.ProcessStatus(
        tmux_session_active=False,
        runner_process_active=False,
    )):
        yield


# --- Safety / readonly invariants ----------------------------------------

def _executable_code(path: Path) -> str:
    """Return the script text with comments and triple-quoted docstrings stripped.

    The safety assertions need to flag actual code, not the README-style
    docstrings that *describe* what the script refuses to do.
    """
    raw = path.read_text(encoding="utf-8")
    # Strip triple-quoted strings (greedy single-line and multi-line).
    import re as _re
    no_docstrings = _re.sub(r'"""[\s\S]*?"""', '', raw)
    no_docstrings = _re.sub(r"'''[\s\S]*?'''", '', no_docstrings)
    # Strip hash-prefixed comments.
    lines = []
    for ln in no_docstrings.splitlines():
        stripped = ln.split("#", 1)[0]
        lines.append(stripped)
    return "\n".join(lines).lower()


def test_script_has_no_wallet_or_tx_symbols() -> None:
    text = _executable_code(SCRIPT_PATH)
    banned = [
        "eth_sendrawtransaction(",
        "eth_sendtransaction(",
        "signtransaction(",
        "createsigner",
        "wallet.load",
        "from_private_key",
        "private_key =",
        "private_key=",
        "mnemonic =",
        "keystore.",
        "keystore(",
        "load_keystore",
        "swap(",
        "mint(",
        "burn(",
    ]
    for b in banned:
        assert b not in text, f"banned token in finalize script (executable code): {b!r}"


def test_script_is_marked_readonly() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "_readonly" in SCRIPT_PATH.name
    assert "no wallet" in text.lower() or "read-only" in text.lower()


def test_allowed_next_stages_set_is_complete() -> None:
    assert finalize.ALLOWED_NEXT_STAGES == {
        "WAIT_FOR_OVERNIGHT_COMPLETION",
        "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT",
        "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
        "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }


# --- Checkpoint progress audit -------------------------------------------

def test_checkpoint_progress_basic(tmp_path: Path) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=34)
    cp = finalize.audit_checkpoint(rd)
    assert cp.selected_pool_count == 8
    assert cp.expected_target_count == 40
    assert cp.completed_target_count == 34
    assert cp.remaining_target_count == 6
    assert cp.progress_pct == 85.0
    assert cp.is_completed is False


def test_checkpoint_completed_when_targets_equal_expected(tmp_path: Path) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=40)
    cp = finalize.audit_checkpoint(rd)
    assert cp.is_completed is True


# --- Data CSV audit -------------------------------------------------------

def test_data_csv_header_only(tmp_path: Path) -> None:
    rd = _make_report_dir(tmp_path, pool_fee_velocity_rows=0, swap_logs_decoded_rows=0)
    ds = finalize.audit_data(rd)
    assert ds.pool_fee_velocity_row_count == 0
    assert ds.swap_logs_decoded_row_count == 0
    assert ds.has_rows is False


def test_data_csv_with_rows(tmp_path: Path) -> None:
    rd = _make_report_dir(tmp_path, pool_fee_velocity_rows=5, swap_logs_decoded_rows=12)
    ds = finalize.audit_data(rd)
    assert ds.pool_fee_velocity_row_count == 5
    assert ds.swap_logs_decoded_row_count == 12
    assert ds.has_rows is True


# --- Final staleness rule -------------------------------------------------

def test_stale_final_when_checkpoint_says_8_and_final_says_0(tmp_path: Path) -> None:
    rd = _make_report_dir(
        tmp_path,
        final_selected_pool_count=0,
        checkpoint_selected_pool_count=8,
        completed_targets=34,
    )
    cp = finalize.audit_checkpoint(rd)
    fs = finalize.audit_final(rd, cp, runner_active=True)
    assert fs.final_is_current is False
    assert fs.final_is_stale_or_unverified is True


def test_stale_final_when_final_mtime_older_than_checkpoint(tmp_path: Path) -> None:
    rd = _make_report_dir(
        tmp_path,
        final_mtime=1000,
        last_checkpoint_at=2000,
        checkpoint_selected_pool_count=8,
        completed_targets=40,
    )
    cp = finalize.audit_checkpoint(rd)
    fs = finalize.audit_final(rd, cp, runner_active=False)
    assert fs.final_is_current is False
    assert fs.final_is_stale_or_unverified is True


def test_checkpoint_8_overrides_stale_final_0_in_output(tmp_path: Path, runner_active) -> None:
    rd = _make_report_dir(tmp_path, final_selected_pool_count=0, checkpoint_selected_pool_count=8)
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
    ])
    assert rc == 0
    payload = json.loads((rd / "RUNNING_STATUS.json").read_text())
    assert payload["checkpoint_selected_pool_count"] == 8
    assert payload["runner_process_active"] is True


# --- Branch decision ------------------------------------------------------

def test_running_branch_when_runner_active_does_not_touch_final(tmp_path: Path, runner_active) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=34)
    final_path = rd / "final" / "FINAL_VERDICT.json"
    import os
    pre_mtime = final_path.stat().st_mtime
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
    ])
    assert rc == 0
    # Original final must be untouched
    assert final_path.stat().st_mtime == pre_mtime
    # No rebuilt final should have been written
    assert not (rd / "final" / "FINAL_VERDICT_REBUILT.json").exists()
    # RUNNING_STATUS files exist
    payload = json.loads((rd / "RUNNING_STATUS.json").read_text())
    assert payload["branch"] == "running"
    assert payload["final_overwritten"] is False
    assert payload["recommended_next_stage"] == "WAIT_FOR_OVERNIGHT_COMPLETION"
    assert payload["wallet_or_tx_touched"] is False
    assert payload["can_run_probe_now"] is False
    assert payload["tiny_canary_allowed"] == "no"
    assert payload["edge_proven"] == "no"


def test_partial_branch_when_runner_inactive_and_progress_incomplete(tmp_path: Path, runner_inactive) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=34)
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
    ])
    assert rc == 0
    payload = json.loads((rd / "PARTIAL_FINAL_VERDICT.json").read_text())
    assert payload["branch"] == "partial"
    assert payload["status"] == "WARN"
    assert payload["recommended_next_stage"] == "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT"
    assert payload["final_overwritten"] is False
    assert not (rd / "final" / "FINAL_VERDICT_REBUILT.json").exists()


def test_partial_branch_when_completed_but_data_empty(tmp_path: Path, runner_inactive) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=40, pool_fee_velocity_rows=0, swap_logs_decoded_rows=0)
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
        "--overwrite-final",  # even with the flag, empty data downgrades
    ])
    assert rc == 0
    payload = json.loads((rd / "PARTIAL_FINAL_VERDICT.json").read_text())
    assert payload["branch"] == "partial"
    assert "data_csvs_empty" in payload["decision_reason"]


def test_complete_branch_requires_overwrite_final_flag(tmp_path: Path, runner_inactive) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=40, pool_fee_velocity_rows=8, swap_logs_decoded_rows=12)
    # Without flag → partial
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
    ])
    assert rc == 0
    assert (rd / "PARTIAL_FINAL_VERDICT.json").exists()
    assert not (rd / "final" / "FINAL_VERDICT_REBUILT.json").exists()
    payload = json.loads((rd / "PARTIAL_FINAL_VERDICT.json").read_text())
    assert "overwrite_final_not_requested" in payload["decision_reason"]


def test_complete_branch_with_flag_writes_rebuilt_not_overwrite(tmp_path: Path, runner_inactive) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=40, pool_fee_velocity_rows=8, swap_logs_decoded_rows=12)
    original_final = rd / "final" / "FINAL_VERDICT.json"
    pre_mtime = original_final.stat().st_mtime
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
        "--overwrite-final",
    ])
    assert rc == 0
    rebuilt = rd / "final" / "FINAL_VERDICT_REBUILT.json"
    assert rebuilt.exists()
    payload = json.loads(rebuilt.read_text())
    assert payload["branch"] == "complete"
    assert payload["status"] == "PASS"
    assert payload["recommended_next_stage"] == "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1"
    # CRITICAL: the original final must NOT be touched.
    assert original_final.stat().st_mtime == pre_mtime


# --- Forced mode overrides ------------------------------------------------

def test_explicit_complete_overridden_when_runner_active(tmp_path: Path, runner_active) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=40, pool_fee_velocity_rows=8, swap_logs_decoded_rows=12)
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "complete",
        "--overwrite-final",
    ])
    assert rc == 0
    # active runner should force running branch despite --mode complete
    assert (rd / "RUNNING_STATUS.json").exists()
    assert not (rd / "final" / "FINAL_VERDICT_REBUILT.json").exists()


# --- recommended_next_stage allowlist ------------------------------------

def test_all_branches_emit_allowed_next_stage(tmp_path: Path, runner_active) -> None:
    rd = _make_report_dir(tmp_path, completed_targets=34)
    rc = finalize.main([
        "--run-id", "20260601_185436",
        "--report-dir", str(rd),
        "--mode", "auto",
    ])
    assert rc == 0
    payload = json.loads((rd / "RUNNING_STATUS.json").read_text())
    assert payload["recommended_next_stage"] in finalize.ALLOWED_NEXT_STAGES
