#!/usr/bin/env python3
"""RH-02bk-1 — synthetic test evidence generator (read-only).

Runs the repo test suite once and writes the results together with the
current code version as a machine-readable evidence file. This file is
intended to serve as the `synthetic_tests_passed` evidence source for the
Stage A gate (wiring the gate is a separate, later task).

Fail-close semantics:
  * code_version comes from `git rev-parse --short=12 HEAD`. If it cannot be
    resolved, no file is written and the process exits with code 2.
  * all_passed requires exit_code==0 AND failed==0 AND errors==0 AND total>0.
    A zero-test run (total==0) is NEVER a pass.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
CODE_VERSION_SOURCE = "git rev-parse --short=12 HEAD"
SUMMARY_KEYS = ("total", "passed", "failed", "errors", "skipped", "duration_secs")


def resolve_code_version(repo: str) -> tuple[str, bool]:
    """Return (short_sha_12, working_tree_clean). Raise RuntimeError on failure."""
    rev = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=repo, capture_output=True, text=True,
    )
    if rev.returncode != 0:
        raise RuntimeError(
            f"git rev-parse failed (rc={rev.returncode}): {rev.stderr.strip()}"
        )
    sha = rev.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{12}", sha):
        raise RuntimeError(f"unexpected git short sha: {sha!r}")
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo, capture_output=True, text=True,
    )
    if status.returncode != 0:
        raise RuntimeError(
            f"git status failed (rc={status.returncode}): {status.stderr.strip()}"
        )
    tracked = [
        ln for ln in status.stdout.splitlines()
        if ln.strip() and not ln.startswith("??")
    ]
    return sha, len(tracked) == 0


def parse_pytest_summary(text: str) -> dict:
    """Parse the trailing summary line of `pytest -q`.

    Returns a dict with keys total/passed/failed/errors/skipped/duration_secs.
    When no summary line can be found, every value is None (not 0).
    """
    result = {k: None for k in SUMMARY_KEYS}
    if not text:
        return result
    lines = [ln for ln in text.splitlines() if ln.strip()]
    summary = None
    for ln in reversed(lines):
        if re.search(r"\bin\s+\d+(?:\.\d+)?s\b", ln):
            summary = ln
            break
    if summary is None:
        return result
    m = re.search(r"\bin\s+(\d+(?:\.\d+)?)s\b", summary)
    if m:
        result["duration_secs"] = float(m.group(1))
    head = summary[: m.start()] if m else summary
    counts: dict[str, int] = {}
    for num, word in re.findall(
        r"(\d+)\s+(passed|failed|skipped|errors|error|xfailed|xpassed|warnings|warning)",
        head,
    ):
        counts[word] = int(num)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    skipped = counts.get("skipped", 0)
    errors = counts.get("error", 0) + counts.get("errors", 0)
    xfailed = counts.get("xfailed", 0)
    xpassed = counts.get("xpassed", 0)
    result["passed"] = passed
    result["failed"] = failed
    result["skipped"] = skipped
    result["errors"] = errors
    result["total"] = passed + failed + skipped + errors + xfailed + xpassed
    return result


def build_evidence(
    *,
    repo: str | Path,
    tests_path: str = "tests/",
    run: bool = True,
) -> dict:
    repo_str = str(repo)
    sha, clean = resolve_code_version(repo_str)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    command = f"python3 -m pytest {tests_path} -q -p no:cacheprovider"

    if not run:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "code_version": sha,
            "code_version_source": CODE_VERSION_SOURCE,
            "working_tree_clean": clean,
            "command": command,
            "exit_code": None,
            "total": None,
            "passed": None,
            "failed": None,
            "errors": None,
            "skipped": None,
            "duration_secs": None,
            "all_passed": False,
        }

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", tests_path, "-q", "-p", "no:cacheprovider"],
        cwd=repo_str,
        capture_output=True,
        text=True,
    )
    exit_code = proc.returncode
    summary = parse_pytest_summary(f"{proc.stdout}\n{proc.stderr}")

    total = summary["total"]
    passed = summary["passed"]
    failed = summary["failed"]
    errors = summary["errors"]
    skipped = summary["skipped"]
    duration_secs = summary["duration_secs"]

    all_passed = bool(
        exit_code == 0
        and failed == 0
        and errors == 0
        and total is not None
        and total > 0
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "code_version": sha,
        "code_version_source": CODE_VERSION_SOURCE,
        "working_tree_clean": clean,
        "command": command,
        "exit_code": exit_code,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "duration_secs": duration_secs,
        "all_passed": all_passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic test evidence for LP RH Stage A gate."
    )
    default_repo = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--repo",
        default=str(default_repo),
        help="Repository root (default: script parent directory's parent)",
    )
    parser.add_argument(
        "--out",
        default="reports/lp_rh/synthetic_tests_evidence.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--tests-path",
        default="tests/",
        help="Tests path to pass to pytest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print evidence skeleton to stdout without running tests or writing file",
    )
    args = parser.parse_args(argv)

    try:
        evidence = build_evidence(
            repo=args.repo,
            tests_path=args.tests_path,
            run=not args.dry_run,
        )
    except RuntimeError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    if args.dry_run:
        print(json.dumps(evidence, indent=2))
        return 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path} all_passed={evidence['all_passed']}")
    return 0 if evidence["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

