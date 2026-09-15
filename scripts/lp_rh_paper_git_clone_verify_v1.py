#!/usr/bin/env python3
"""Real git-clone independent verification (RH_CORE_REAL_SOURCE_CLOSEOUT_V1 §4).

Per Owner directive: do NOT use verify-seed fake checkout.  The candidate
SHA must be verified as a real Git object via fetch + git cat-file + tree
inspection in a tmp dir.

Steps performed:
  1. `git fetch <origin> <branch>` to refresh remote refs (no force, no push).
  2. `git rev-parse --verify <candidate>^{commit}` — confirm commit object exists.
  3. `git rev-parse --verify <candidate>^{tree}` — confirm tree object exists.
  4. `git cat-file -e <candidate>^{commit}` — object readable from this repo.
  5. `git worktree add <tmp_dir> <candidate>` — independent checkout.
  6. Inside the worktree:
       git rev-parse HEAD  → candidate SHA (must match)
       git status --porcelain → empty (no uncommitted state carried over)
       git log -1 --format='%H %s' → real commit, not constructed
       git ls-tree HEAD | wc -l → tree contents non-empty
  7. `git worktree remove --force <tmp_dir>` — clean up.

Output: JSON to stdout (and optional --json-out path).

Hard rules:
  * Read-only on the candidate SHA — never modifies history, never force-pushes.
  * Never uses tar/seed/verify-seed fake checkouts.
  * Never writes to the worktree we're verifying (uses `git worktree add`).
  * All temp dirs under $TMPDIR or /tmp/lpbot_git_verify_$$.
  * On any failure, exits 1 with the failing step in evidence.

Usage:
    python3 scripts/lp_rh_paper_git_clone_verify_v1.py \\
        --repo /opt/lpbot/lp-bot-v3-origin-check \\
        --remote origin \\
        --branch feat/prd-v2.1-m0-shadow \\
        --candidate <SHA> \\
        --json-out reports/git_clone_verify_<date>.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run(
    args: list[str], *, cwd: Path | None = None, check: bool = True
) -> tuple[int, str, str]:
    """Run subprocess; return (rc, stdout, stderr).  Raise on non-zero if check."""
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)} (rc={proc.returncode}); "
            f"stderr={proc.stderr.strip()}"
        )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _git(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    rc, out, err = _run(["git", *args], cwd=cwd, check=check)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="Path to existing local repo")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="feat/prd-v2.1-m0-shadow")
    p.add_argument(
        "--candidate",
        default=None,
        help="Candidate SHA to verify.  If omitted, uses repo's HEAD.",
    )
    p.add_argument("--json-out", default="")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        print(
            f"ERROR: {repo} is not a git repo (no .git dir)", file=sys.stderr
        )
        return 1

    # Step 0 — determine candidate SHA
    candidate = args.candidate or _git(
        ["rev-parse", "HEAD"], cwd=repo
    )

    evidence: dict[str, Any] = {
        "started_at": _now_iso(),
        "repo": str(repo),
        "remote": args.remote,
        "branch": args.branch,
        "candidate": candidate,
        "steps": {},
    }

    # Step 1 — fetch (best-effort; offline repos skip with WARNING)
    fetch_ok = True
    fetch_warning: str | None = None
    try:
        _git(["fetch", args.remote, args.branch], cwd=repo, check=False)
    except Exception as exc:
        fetch_warning = f"fetch failed: {exc}; continuing with local objects"
        fetch_ok = False
    evidence["steps"]["1_fetch"] = {
        "ok": fetch_ok,
        "warning": fetch_warning,
    }

    # Step 2 — rev-parse candidate^{commit}
    try:
        commit_obj = _git(
            ["rev-parse", "--verify", f"{candidate}^{{commit}}"], cwd=repo
        )
    except Exception as exc:
        evidence["steps"]["2_commit_object"] = {
            "ok": False,
            "error": str(exc),
        }
        evidence["verdict"] = "FAIL"
        evidence["ended_at"] = _now_iso()
        return _emit(evidence, args.json_out)
    evidence["steps"]["2_commit_object"] = {
        "ok": True,
        "commit_object": commit_obj,
    }

    # Step 3 — rev-parse candidate^{tree}
    try:
        tree_obj = _git(
            ["rev-parse", "--verify", f"{candidate}^{{tree}}"], cwd=repo
        )
    except Exception as exc:
        evidence["steps"]["3_tree_object"] = {
            "ok": False,
            "error": str(exc),
        }
        evidence["verdict"] = "FAIL"
        evidence["ended_at"] = _now_iso()
        return _emit(evidence, args.json_out)
    evidence["steps"]["3_tree_object"] = {
        "ok": True,
        "tree_object": tree_obj,
    }

    # Step 4 — git cat-file -e
    try:
        _git(["cat-file", "-e", f"{candidate}^{{commit}}"], cwd=repo)
    except Exception as exc:
        evidence["steps"]["4_cat_file"] = {
            "ok": False,
            "error": str(exc),
        }
        evidence["verdict"] = "FAIL"
        evidence["ended_at"] = _now_iso()
        return _emit(evidence, args.json_out)
    evidence["steps"]["4_cat_file"] = {"ok": True}

    # Step 5 — worktree add
    tmp_root = Path(
        os.environ.get("TMPDIR", "/tmp")
    ) / f"lpbot_git_verify_{os.getpid()}_{int(datetime.now().timestamp())}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    evidence["worktree_tmp"] = str(tmp_root)

    worktree_path = tmp_root / "wt"
    try:
        _git(
            ["worktree", "add", "--detach", str(worktree_path), candidate],
            cwd=repo,
        )
    except Exception as exc:
        evidence["steps"]["5_worktree_add"] = {
            "ok": False,
            "error": str(exc),
        }
        evidence["verdict"] = "FAIL"
        evidence["ended_at"] = _now_iso()
        shutil.rmtree(tmp_root, ignore_errors=True)
        return _emit(evidence, args.json_out)
    evidence["steps"]["5_worktree_add"] = {
        "ok": True,
        "path": str(worktree_path),
    }

    # Step 6 — verify inside the worktree
    try:
        wt_head = _git(["rev-parse", "HEAD"], cwd=worktree_path)
        wt_status = _git(
            ["status", "--porcelain", "--untracked-files=all"],
            cwd=worktree_path,
        )
        wt_log = _git(["log", "-1", "--format=%H %s"], cwd=worktree_path)
        # Tree contents — count entries in the top-level tree
        wt_tree_listing = _git(["ls-tree", "HEAD"], cwd=worktree_path)
        wt_tree_count = len(
            [line for line in wt_tree_listing.splitlines() if line.strip()]
        )

        # Step 6a — REAL pytest run inside the worktree, not just collect.
        # Run a smoke scope (the four paper-readiness test modules) so we
        # catch broken imports / syntax errors that --collect-only would
        # miss.  We capture rc and tail of output for evidence.
        rc_pytest, out_pytest, err_pytest = _run(
            [
                sys.executable, "-m", "pytest",
                "tests/test_lp_rh_paper_data_validity_v1.py",
                "tests/test_lp_rh_paper_daemon_entry_v1.py",
                "tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py",
                "tests/test_lp_rh_paper_git_clone_verify_v1.py",
                "-q", "--tb=line", "--no-header",
                "-p", "no:cacheprovider",
            ],
            cwd=worktree_path,
            check=False,
        )
        pytest_passed = rc_pytest == 0
        pytest_summary_line = ""
        for ln in (out_pytest or "").splitlines():
            s = ln.strip()
            if " passed" in s and (" failed" in s or " error" in s
                                    or s.endswith("passed")):
                pytest_summary_line = s
                break

        # Step 6b — REAL audit_repro run.  This catches AST-extraction
        # regressions (defects_reproduced, probe_errors) that pytest alone
        # would not detect.
        rc_audit, out_audit, err_audit = _run(
            [
                sys.executable, "tools/audit_repro/audit_repro.py",
                "--repo", str(worktree_path),
                "--allow-other-head",
                "--json-out", str(tmp_root / "audit.json"),
            ],
            cwd=worktree_path,
            check=False,
        )
        audit_passed = rc_audit == 0
        audit_defects = None
        audit_probe_errors = None
        audit_path = str(tmp_root / "audit.json")
        try:
            audit_blob = json.loads(
                Path(audit_path).read_text(encoding="utf-8")
            )
            counts = audit_blob.get("counts") or {}
            audit_defects = counts.get("DEFECT_REPRODUCED")
            audit_probe_errors = counts.get("PROBE_ERROR")
        except Exception as exc:
            audit_passed = False
            audit_defects = f"audit.json unreadable: {exc}"

        evidence["steps"]["6_worktree_verify"] = {
            "ok": True,
            "wt_head": wt_head,
            "wt_head_matches_candidate": wt_head == candidate,
            "wt_status_porcelain_empty": wt_status == "",
            "wt_status_porcelain": wt_status,
            "wt_log": wt_log,
            "wt_tree_top_level_count": wt_tree_count,
            "pytest_run": {
                "rc": rc_pytest,
                "passed": pytest_passed,
                "summary_line": pytest_summary_line,
                "stdout_tail": out_pytest[-1000:] if out_pytest else "",
                "stderr_tail": err_pytest[-500:] if err_pytest else "",
            },
            "audit_repro_run": {
                "rc": rc_audit,
                "passed": audit_passed,
                "defects_reproduced": audit_defects,
                "probe_errors": audit_probe_errors,
                "stdout_tail": out_audit[-500:] if out_audit else "",
                "stderr_tail": err_audit[-500:] if err_audit else "",
            },
        }
    finally:
        # Step 7 — clean up worktree
        try:
            _git(
                ["worktree", "remove", "--force", str(worktree_path)],
                cwd=repo,
                check=False,
            )
        except Exception:
            pass
        shutil.rmtree(tmp_root, ignore_errors=True)

    # Final verdict — gates on rc of BOTH pytest AND audit_repro.  Per
    # Owner directive, collecting tests is not enough; the verifier must
    # actually run them and FAIL if either exits non-zero.
    wt_step = evidence["steps"].get("6_worktree_verify", {})
    pytest_run = wt_step.get("pytest_run", {})
    audit_run = wt_step.get("audit_repro_run", {})
    verdict_ok = (
        wt_step.get("wt_head_matches_candidate", False)
        and wt_step.get("wt_status_porcelain_empty", False)
        and wt_step.get("wt_tree_top_level_count", 0) > 0
        and pytest_run.get("passed", False)
        and audit_run.get("passed", False)
    )
    evidence["verdict"] = "PASS" if verdict_ok else "FAIL"
    evidence["ended_at"] = _now_iso()
    return _emit(evidence, args.json_out)


def _emit(evidence: dict[str, Any], json_out: str) -> int:
    print(json.dumps(evidence, indent=2, default=str))
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(evidence, indent=2, default=str))
    return 0 if evidence.get("verdict") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
