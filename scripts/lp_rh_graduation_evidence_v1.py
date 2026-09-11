#!/usr/bin/env python3
"""lp_rh_graduation_evidence_v1.py — RH-08 毕业收尾证据与交付物生成器

生成 PRD §21 / RH-08 毕业收尾证据四份文件中的三份交付物：
1. READINESS_DASHBOARD.md (带生成时刻、HEAD、工作区状态头部)
2. FULL_TEST_RAW.log (--skip-tests 时跳过)
3. GRADUATION_VERDICT.json (结构化裁决与 fail-close 状态)

所有数据库访问必须严格只读 (mode=ro)，绝不修改现有逻辑。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_readiness_v1_readonly import (
    _build_state,
    open_store,
    render_dashboard,
)

DEFAULT_DB_PATH = REPO_ROOT / "reports" / "lp_rh" / "scanner.db"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "lp_rh"
DEFAULT_ASSET_ADDRESS = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"


def get_git_metadata(repo_root: Optional[Path] = None) -> Tuple[Optional[str], Optional[bool]]:
    """Query git short hash (12 chars) and working tree cleanliness."""
    root = str(repo_root or REPO_ROOT)
    try:
        proc_hash = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        code_version = proc_hash.stdout.strip() if proc_hash.returncode == 0 else None
    except Exception:
        code_version = None

    try:
        proc_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc_status.returncode == 0:
            clean = (len(proc_status.stdout.strip()) == 0)
        else:
            clean = None
    except Exception:
        clean = None

    return code_version, clean


def parse_fault_injection_report(report_path: Path) -> Dict[str, Any]:
    """Parse FAULT_INJECTION_REPORT.md for scenario counts.

    Returns dict with report_present, scenarios_passed, scenarios_total.
    If report does not exist or counts cannot be parsed, fail-close with nulls.
    """
    if not report_path.is_file():
        return {
            "report_present": False,
            "scenarios_passed": None,
            "scenarios_total": None,
        }

    try:
        content = report_path.read_text(encoding="utf-8")
    except Exception:
        return {
            "report_present": True,
            "scenarios_passed": None,
            "scenarios_total": None,
        }

    # Matches patterns like:
    # **`PASS`** (6/6 场景注入均成功阻断...)
    # or (6/6 场景...)
    m = re.search(r"\((\d+)\s*/\s*(\d+)\s*(?:个)?场景", content)
    if not m:
        # Try a more general regex like `PASS (6/6)` or `(\d+)/(\d+)`
        m = re.search(r"\((\d+)\s*/\s*(\d+)\)", content)

    if m:
        try:
            passed = int(m.group(1))
            total = int(m.group(2))
            return {
                "report_present": True,
                "scenarios_passed": passed,
                "scenarios_total": total,
            }
        except Exception:
            pass

    return {
        "report_present": True,
        "scenarios_passed": None,
        "scenarios_total": None,
    }


def parse_pytest_summary(output: str) -> Dict[str, Optional[int]]:
    """Extract passed, failed, total from pytest stdout/stderr.

    Example line: '4755 passed, 14 skipped in 50.95s'
    Example line: '1 failed, 10 passed in 1.2s'
    """
    passed, failed, skipped, errors = 0, 0, 0, 0
    m_pass = re.search(r"(\d+)\s+passed", output)
    if m_pass:
        passed = int(m_pass.group(1))
    m_fail = re.search(r"(\d+)\s+failed", output)
    if m_fail:
        failed = int(m_fail.group(1))
    m_skip = re.search(r"(\d+)\s+skipped", output)
    if m_skip:
        skipped = int(m_skip.group(1))
    m_err = re.search(r"(\d+)\s+error(?:s)?", output)
    if m_err:
        errors = int(m_err.group(1))

    if not m_pass and not m_fail and not m_err:
        # Unable to parse summary
        return {"total": None, "passed": None, "failed": None}

    total = passed + failed + errors
    return {
        "total": total,
        "passed": passed,
        "failed": failed + errors,
    }


def run_full_tests(
    out_dir: Path,
    repo_root: Path,
    code_version: Optional[str],
    working_tree_clean: Optional[bool],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Run pytest suite, stream raw stdout+stderr into FULL_TEST_RAW.log.

    Returns (full_test_summary_dict, full_test_log_status).
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    log_file = out_dir / "FULL_TEST_RAW.log"
    cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"]
    cmd_str = " ".join(cmd)

    header = (
        f"# FULL_TEST_RAW.log\n"
        f"- Generated At (UTC): {now_utc}\n"
        f"- Code Version: {code_version or 'unknown'}\n"
        f"- Working Tree Clean: {working_tree_clean}\n"
        f"- Command: {cmd_str}\n"
        f"--------------------------------------------------\n"
    )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = proc.stdout + "\n" + proc.stderr
        exit_code = proc.returncode
    except Exception as exc:
        combined_output = f"Execution failed: {exc}\n"
        exit_code = -1

    log_file.write_text(header + combined_output, encoding="utf-8")

    parsed = parse_pytest_summary(combined_output)
    full_test = {
        "total": parsed["total"],
        "passed": parsed["passed"],
        "failed": parsed["failed"],
        "exit_code": exit_code,
    }
    return full_test, str(log_file.name)


def build_verdict(
    state: Dict[str, Any],
    full_test: Optional[Dict[str, Any]],
    fault_injection: Optional[Dict[str, Any]],
    code_version: Optional[str],
    working_tree_clean: Optional[bool],
    db_path: str,
    generated_at: str,
) -> Dict[str, Any]:
    """Assemble the GRADUATION_VERDICT dictionary following PRD and spec fail-close rules."""
    stage_a_raw = state.get("stage_a")
    stage_b_raw = state.get("stage_b")
    live_gate_raw = state.get("live_gate")

    verdict_reasons: List[str] = []

    # 1. Stage A extraction
    if stage_a_raw is None:
        stage_a_data = None
        verdict_reasons.append("EVIDENCE_UNAVAILABLE:stage_a")
    else:
        stage_a_data = {
            "passed": stage_a_raw.get("passed"),
            "blockers": list(stage_a_raw.get("blockers") or []),
            "hours_covered": stage_a_raw.get("hours_covered"),
            "hours_required": stage_a_raw.get("hours_required"),
            "coverage_ratio": str(stage_a_raw.get("coverage_ratio")) if stage_a_raw.get("coverage_ratio") is not None else None,
        }
        for b in stage_a_data["blockers"]:
            verdict_reasons.append(f"STAGE_A: {b}")

    # 2. Stage B extraction
    if stage_b_raw is None:
        stage_b_data = None
        verdict_reasons.append("EVIDENCE_UNAVAILABLE:stage_b")
    else:
        stage_b_data = {
            "passed": stage_b_raw.get("passed"),
            "blockers": list(stage_b_raw.get("blockers") or []),
            "days_covered": stage_b_raw.get("days_covered"),
            "days_required": stage_b_raw.get("days_required"),
        }
        for b in stage_b_data["blockers"]:
            verdict_reasons.append(f"STAGE_B: {b}")

    # 3. Live Gate extraction
    if live_gate_raw is None:
        live_gate_data = None
        verdict_reasons.append("EVIDENCE_UNAVAILABLE:live_gate")
    else:
        live_gate_data = {
            "live_allowed": live_gate_raw.get("live_allowed"),
            "blockers": list(live_gate_raw.get("blockers") or []),
        }
        for b in live_gate_data["blockers"]:
            verdict_reasons.append(f"LIVE_GATE: {b}")

    # 4. Full test handling
    if full_test is None:
        full_test_data = None
    else:
        full_test_data = full_test
        if full_test.get("failed") and full_test["failed"] > 0:
            verdict_reasons.append(f"FULL_TEST_FAILED: {full_test['failed']} failures")
        if full_test.get("exit_code") != 0:
            verdict_reasons.append(f"FULL_TEST_NONZERO_EXIT: {full_test.get('exit_code')}")

    # 5. Fault injection handling
    if fault_injection is None:
        fault_injection_data = None
        verdict_reasons.append("EVIDENCE_UNAVAILABLE:fault_injection")
    else:
        fault_injection_data = fault_injection
        if not fault_injection.get("report_present"):
            verdict_reasons.append("EVIDENCE_UNAVAILABLE:fault_injection_report")
        elif fault_injection.get("scenarios_passed") is None:
            verdict_reasons.append("EVIDENCE_UNAVAILABLE:fault_injection_counts")

    # 6. Verdict evaluation (F08)
    stage_a_passed = bool(stage_a_data and stage_a_data.get("passed") is True)
    stage_b_passed = bool(stage_b_data and stage_b_data.get("passed") is True)
    live_gate_passed = bool(live_gate_data and live_gate_data.get("live_allowed") is True)

    manual_override_blocked = False

    has_test_failure = False
    if full_test_data is not None:
        if (full_test_data.get("failed") or 0) > 0 or full_test_data.get("exit_code") != 0:
            has_test_failure = True
    if fault_injection_data is not None:
        sp = fault_injection_data.get("scenarios_passed")
        st = fault_injection_data.get("scenarios_total")
        if not fault_injection_data.get("report_present") or sp is None or (st is not None and sp < st):
            has_test_failure = True

    if not stage_a_passed:
        verdict = "NOT_GRADUATED"
    elif has_test_failure:
        verdict = "OBSERVATION_INCOMPLETE"
    elif not stage_b_passed:
        verdict = "STAGE_A_PASSED"
    else:
        verdict = "SHADOW_VALIDATED"

    # 7. Tiny Live Authorization rule (Fail-close)
    all_three_passed = stage_a_passed and stage_b_passed and live_gate_passed
    if all_three_passed:
        # PRD requires explicit owner signoff; code check alone is insufficient.
        tiny_live_authorized = False
        verdict_reasons.append("OWNER_APPROVAL_REQUIRED: 代码判定通过不等于所有者批准，真钱须由所有者明确批准")
    else:
        tiny_live_authorized = False

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "code_version": code_version,
        "working_tree_clean": working_tree_clean,
        "db_path": db_path,
        "as_of": state.get("as_of"),
        "stage_a": stage_a_data,
        "stage_b": stage_b_data,
        "live_gate": live_gate_data,
        "full_test": full_test_data,
        "fault_injection": fault_injection_data,
        "verdict": verdict,
        "verdict_reasons": verdict_reasons,
        "tiny_live_authorized": tiny_live_authorized,
        "manual_override_blocked": manual_override_blocked,
    }


def generate_graduation_evidence(
    db_path: Path,
    out_dir: Path,
    asset_address: str,
    skip_tests: bool = False,
    repo_root: Optional[Path] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Execute complete graduation evidence pipeline."""
    repo = repo_root or REPO_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    code_version, working_tree_clean = get_git_metadata(repo)

    # 1. Run full tests if not skipped
    full_test: Optional[Dict[str, Any]] = None
    if not skip_tests:
        full_test, _ = run_full_tests(
            out_dir=out_dir,
            repo_root=repo,
            code_version=code_version,
            working_tree_clean=working_tree_clean,
        )

    # 2. Parse fault injection report
    fi_report_path = out_dir / "FAULT_INJECTION_REPORT.md"
    if not fi_report_path.exists():
        # Fallback to repo reports/lp_rh/FAULT_INJECTION_REPORT.md if searching in repo
        alt_path = repo / "reports" / "lp_rh" / "FAULT_INJECTION_REPORT.md"
        if alt_path.is_file() and out_dir != alt_path.parent:
            # Note: The spec says:
            # "fault_injection 一节：读 --out-dir/FAULT_INJECTION_REPORT.md 是否存在；存在就解析..."
            # So we strictly adhere to --out-dir/FAULT_INJECTION_REPORT.md
            pass
    fault_injection = parse_fault_injection_report(fi_report_path)

    # 3. Read state from DB via readiness read-only store
    # Ensure read-only connection
    conn = open_store(db_path, read_only=True)
    try:
        state = _build_state(
            conn,
            str(db_path),
            interval_secs=15.0,
            asset_address=asset_address,
            repo_root=str(repo),
        )
    finally:
        conn.close()

    # 4. Render and write READINESS_DASHBOARD.md
    raw_dashboard = render_dashboard(state)
    dashboard_header = (
        f"<!-- METADATA\n"
        f"generated_at: {generated_at}\n"
        f"code_version: {code_version or 'unknown'}\n"
        f"working_tree_clean: {working_tree_clean}\n"
        f"db_path: {db_path}\n"
        f"as_of: {state.get('as_of')}\n"
        f"-->\n\n"
    )
    dashboard_path = out_dir / "READINESS_DASHBOARD.md"
    dashboard_path.write_text(dashboard_header + raw_dashboard, encoding="utf-8")

    # 5. Build and write GRADUATION_VERDICT.json
    verdict_dict = build_verdict(
        state=state,
        full_test=full_test,
        fault_injection=fault_injection,
        code_version=code_version,
        working_tree_clean=working_tree_clean,
        db_path=str(db_path),
        generated_at=generated_at,
    )
    verdict_path = out_dir / "GRADUATION_VERDICT.json"
    verdict_path.write_text(json.dumps(verdict_dict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return 0, verdict_dict


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate RH graduation evidence deliverables (read-only)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to scanner.db (read-only)")
    parser.add_argument("--asset-address", default=DEFAULT_ASSET_ADDRESS, help="Asset address to audit")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for deliverables")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running pytest suite")
    parser.add_argument("--repo", default=None, help="Repo root path")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    repo_root = Path(args.repo) if args.repo else None

    exit_code, verdict_dict = generate_graduation_evidence(
        db_path=db_path,
        out_dir=out_dir,
        asset_address=args.asset_address,
        skip_tests=args.skip_tests,
        repo_root=repo_root,
    )
    print(f"Verdict: {verdict_dict['verdict']}")
    print(f"Deliverables generated at: {out_dir}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())


