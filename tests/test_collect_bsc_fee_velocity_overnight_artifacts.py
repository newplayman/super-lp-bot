"""Tests for scripts/collect_bsc_fee_velocity_overnight_artifacts.sh.

The collect script is bash and supports two modes:
  - local /tmp first (no SSH)
  - SSH fallback (skipped here — exercised manually)

These tests run hermetically against a fake `/tmp` style source dir, asserting
that local-mode rsync works, that the stale-final warning fires, that
`--delete` is not used, and that audit reports already in the destination
are not clobbered.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "collect_bsc_fee_velocity_overnight_artifacts.sh"


def _build_source_run_dir(src: Path, *, final_mtime: int = 1000, state_mtime: int = 2000, log_mtime: int = 2000) -> None:
    (src / "final").mkdir(parents=True)
    (src / "checkpoint").mkdir()
    (src / "data").mkdir()
    (src / "logs").mkdir()
    (src / "final" / "FINAL_VERDICT.json").write_text(json.dumps({"status": "FAIL", "selected_pool_count": 0}))
    (src / "checkpoint" / "state.json").write_text(json.dumps({"pool_count": 8, "selected_pool_count": 8, "windows": ["24h"], "completed_targets": [], "last_checkpoint_at": state_mtime}))
    (src / "data" / "pool_fee_velocity.csv").write_text("header\n")
    (src / "data" / "swap_logs_decoded.csv").write_text("header\n")
    (src / "logs" / "run.log").write_text("[start]\n")
    os.utime(src / "final" / "FINAL_VERDICT.json", (final_mtime, final_mtime))
    os.utime(src / "checkpoint" / "state.json", (state_mtime, state_mtime))
    os.utime(src / "logs" / "run.log", (log_mtime, log_mtime))


def _run_collect(run_id: str, tmp_repo: Path, extra_args: list[str], *, source_mounted_at_tmp: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the COPY of the collect script that lives inside tmp_repo.

    The script computes its destination from `$(dirname "$0")/..`, so the
    test must invoke the copy under tmp_repo/scripts/ — passing the real
    repo's absolute path would target the real repo's reports dir instead.
    """
    env = os.environ.copy()
    script_under_test = tmp_repo / "scripts" / SCRIPT_PATH.name
    assert script_under_test.exists(), f"missing script copy at {script_under_test}"
    return subprocess.run(
        ["bash", str(script_under_test), "--run-id", run_id, *extra_args],
        cwd=str(tmp_repo),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _setup_repo_in_tmp(tmp_path: Path, run_id: str) -> Path:
    """Create a minimal repo layout in tmp_path: scripts/ and reports/."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT_PATH, repo / "scripts" / SCRIPT_PATH.name)
    (repo / "reports" / "lp_bsc_fee_velocity_overnight" / run_id).mkdir(parents=True)
    return repo


def _setup_tmp_source(run_id: str, *, final_mtime: int = 1000, state_mtime: int = 2000, log_mtime: int = 2000) -> Path:
    src = Path(f"/tmp/lp_bsc_fee_velocity_overnight_{run_id}")
    if src.exists():
        # Don't touch the real overnight run if the test happens to share the canonical run_id;
        # tests should always use a unique run_id like "test_<uuid>".
        raise RuntimeError(f"refusing to clobber {src}; test must use a unique run_id")
    _build_source_run_dir(src, final_mtime=final_mtime, state_mtime=state_mtime, log_mtime=log_mtime)
    return src


@pytest.fixture
def isolated_run_id(request):
    """Yield a unique synthetic run_id and clean /tmp afterwards."""
    safe_name = request.node.name.replace("[", "_").replace("]", "")
    run_id = f"testfixture_{safe_name}_{os.getpid()}"
    yield run_id
    src = Path(f"/tmp/lp_bsc_fee_velocity_overnight_{run_id}")
    if src.exists():
        shutil.rmtree(src, ignore_errors=True)


# --- Safety / format invariants ------------------------------------------

def _executable_bash(path: Path) -> str:
    """Return the bash script text with shell-comment lines stripped.

    Lines that *describe* a banned behavior (e.g. the file header that says
    "--delete is NOT used") must not trigger the safety assertion.
    """
    lines = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        stripped = ln.lstrip()
        if stripped.startswith("#") and not stripped.startswith("#!"):
            continue
        # Strip trailing inline comments.
        if "#" in ln:
            ln = ln.split("#", 1)[0]
        lines.append(ln)
    return "\n".join(lines)


def test_script_does_not_use_rsync_delete() -> None:
    text = _executable_bash(SCRIPT_PATH)
    # Must not use --delete in any rsync invocation (in executable code).
    assert "--delete" not in text, "collect script must not use --delete (would clobber audit reports and race the runner)"


def test_script_has_dual_mode_flags() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "--local-only" in text
    assert "--ssh-host" in text
    assert "--run-id" in text


def test_script_does_not_touch_wallets() -> None:
    text = _executable_bash(SCRIPT_PATH).lower()
    banned = ["eth_sendrawtransaction", "eth_sendtransaction", "private_key", "signtransaction", "wallet.load"]
    for b in banned:
        assert b not in text, f"banned token in collect script (executable code): {b!r}"


# --- Local mode happy path -----------------------------------------------

@pytest.mark.skipif(not Path("/tmp").is_dir(), reason="requires /tmp on this host")
def test_local_only_mode_syncs_and_warns_stale(tmp_path: Path, isolated_run_id) -> None:
    run_id = isolated_run_id
    repo = _setup_repo_in_tmp(tmp_path, run_id)
    src = _setup_tmp_source(run_id, final_mtime=1000, state_mtime=2000, log_mtime=2000)
    result = _run_collect(run_id, repo, ["--local-only"])
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "synced_from=local:" in result.stdout
    # Stale-final warning must fire because final_mtime < state_mtime
    assert "WARNING: final exists but may be stale" in result.stdout
    # Files arrived
    dest = repo / "reports" / "lp_bsc_fee_velocity_overnight" / run_id
    assert (dest / "final" / "FINAL_VERDICT.json").exists()
    assert (dest / "checkpoint" / "state.json").exists()
    assert (dest / "logs" / "run.log").exists()
    assert (dest / "data" / "pool_fee_velocity.csv").exists()


@pytest.mark.skipif(not Path("/tmp").is_dir(), reason="requires /tmp on this host")
def test_local_only_mode_no_warning_when_final_is_fresh(tmp_path: Path, isolated_run_id) -> None:
    run_id = isolated_run_id
    repo = _setup_repo_in_tmp(tmp_path, run_id)
    src = _setup_tmp_source(run_id, final_mtime=3000, state_mtime=2000, log_mtime=2000)
    result = _run_collect(run_id, repo, ["--local-only"])
    assert result.returncode == 0
    assert "WARNING: final exists but may be stale" not in result.stdout


@pytest.mark.skipif(not Path("/tmp").is_dir(), reason="requires /tmp on this host")
def test_local_only_mode_preserves_existing_audit_reports(tmp_path: Path, isolated_run_id) -> None:
    """If the repo report dir already has VPS_LOCAL_*.md from a previous phase,
    the rsync excludes must not delete them."""
    run_id = isolated_run_id
    repo = _setup_repo_in_tmp(tmp_path, run_id)
    dest = repo / "reports" / "lp_bsc_fee_velocity_overnight" / run_id
    sentinel = dest / "VPS_LOCAL_AUDIT_SENTINEL.md"
    sentinel.write_text("must survive sync\n")
    _setup_tmp_source(run_id)
    result = _run_collect(run_id, repo, ["--local-only"])
    assert result.returncode == 0
    assert sentinel.exists()
    assert sentinel.read_text() == "must survive sync\n"


@pytest.mark.skipif(not Path("/tmp").is_dir(), reason="requires /tmp on this host")
def test_local_mode_chosen_automatically_when_tmp_exists(tmp_path: Path, isolated_run_id) -> None:
    """Without --local-only or --ssh-host, local /tmp takes precedence if present."""
    run_id = isolated_run_id
    repo = _setup_repo_in_tmp(tmp_path, run_id)
    _setup_tmp_source(run_id)
    result = _run_collect(run_id, repo, [])
    assert result.returncode == 0
    assert "synced_from=local:" in result.stdout


def test_local_only_fails_when_tmp_missing(tmp_path: Path) -> None:
    """If we ask for local-only but the /tmp dir does not exist, exit nonzero."""
    run_id = f"definitely_nonexistent_{os.getpid()}"
    src = Path(f"/tmp/lp_bsc_fee_velocity_overnight_{run_id}")
    if src.exists():
        shutil.rmtree(src)
    repo = _setup_repo_in_tmp(tmp_path, run_id)
    result = _run_collect(run_id, repo, ["--local-only"])
    assert result.returncode != 0
    assert "local /tmp run dir not present" in result.stderr


# --- Required-arg invariants ---------------------------------------------

def test_missing_run_id_exits_nonzero(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=20,
    )
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()
