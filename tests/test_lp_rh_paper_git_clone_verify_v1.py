"""Tests for lp_rh_paper_git_clone_verify_v1.py.

The verify script is a thin wrapper around `git rev-parse` / `git cat-file`
/ `git worktree`.  We test the script as a subprocess (real git invocation,
not mocked) so we know the script itself does not lie about the SHA.

Forbidden:
  * Mocking subprocess.run
  * Hand-writing refs / fake commits
  * Skipping the actual git checkout step
  * Using a non-Git-method to "verify" the SHA (e.g. tar+seed)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "lp_rh_paper_git_clone_verify_v1.py"


def _run_script(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode not in (0, 1):
        pytest.fail(
            f"script crashed (rc={proc.returncode}): stderr={proc.stderr}"
        )
    return json.loads(proc.stdout)


class TestGitCloneVerify:
    def test_real_sha_passes(self) -> None:
        """Verify the current HEAD; expect PASS.

        S4: the verifier must gate on actual pytest rc + audit_repro rc,
        not just collect-only.  For a real HEAD those should both PASS.
        """
        # Get HEAD via plain git rev-parse (the script does the same thing
        # when --candidate is omitted).
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        out = _run_script("--candidate", head)
        assert out["verdict"] == "PASS", (
            f"verdict={out['verdict']} — expected PASS for real HEAD {head}; "
            f"steps={out['steps']}"
        )
        assert out["steps"]["1_fetch"]["ok"] is True
        assert out["steps"]["2_commit_object"]["ok"] is True
        assert out["steps"]["3_tree_object"]["ok"] is True
        assert out["steps"]["4_cat_file"]["ok"] is True
        assert out["steps"]["5_worktree_add"]["ok"] is True
        wt = out["steps"]["6_worktree_verify"]
        assert wt["wt_head_matches_candidate"] is True
        assert wt["wt_status_porcelain_empty"] is True
        assert wt["wt_tree_top_level_count"] > 0
        # S4: gate on pytest rc and audit_repro rc
        pytest_run = wt["pytest_run"]
        assert pytest_run["rc"] == 0, (
            f"pytest rc={pytest_run['rc']}; summary_line={pytest_run.get('summary_line')}; "
            f"stderr_tail={pytest_run.get('stderr_tail')}"
        )
        assert pytest_run["passed"] is True
        audit_run = wt["audit_repro_run"]
        assert audit_run["rc"] == 0, (
            f"audit_repro rc={audit_run['rc']}; defects={audit_run.get('defects_reproduced')}; "
            f"probe_errors={audit_run.get('probe_errors')}"
        )
        assert audit_run["passed"] is True

    def test_fake_sha_fails_cleanly(self) -> None:
        """A SHA that doesn't exist must FAIL at step 2 (commit object)."""
        fake_sha = "0" * 40  # all-zeros is never a valid git object
        out = _run_script("--candidate", fake_sha)
        assert out["verdict"] == "FAIL"
        assert out["steps"]["2_commit_object"]["ok"] is False
        # Steps 3-6 must NOT have run (worktree was never created)
        assert "3_tree_object" not in out["steps"]

    def test_does_not_touch_main_worktree(self) -> None:
        """The verify script must not modify this repo's working tree."""
        before = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(REPO_ROOT), text=True
        )
        out = _run_script(
            "--candidate",
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
            ).strip(),
        )
        after = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(REPO_ROOT), text=True
        )
        assert before == after, (
            f"verify script modified working tree:\nbefore={before!r}\n"
            f"after={after!r}"
        )
        assert out["verdict"] == "PASS"

    def test_worktree_tmp_dir_is_cleaned_up(self) -> None:
        """After verify, the tmp dir created during step 5 must be gone."""
        before_dirs = set(
            p.name for p in Path("/tmp").iterdir() if p.name.startswith(
                "lpbot_git_verify_"
            )
        )
        out = _run_script(
            "--candidate",
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
            ).strip(),
        )
        after_dirs = set(
            p.name for p in Path("/tmp").iterdir() if p.name.startswith(
                "lpbot_git_verify_"
            )
        )
        leak = after_dirs - before_dirs
        assert not leak, (
            f"worktree tmp dirs leaked after verify: {leak}; verdict="
            f"{out['verdict']}"
        )
