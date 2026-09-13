"""Paper readiness verdict aggregator (16 gates + report + CLI).

Provides compute_paper_readiness() aggregating 16 concrete Paper-technical gates.
Each gate is a pure function returning:
  {"pass": bool, "evidence": dict, "reason": str | None}

Verdict rules:
  - "PASS" iff all REQUIRED gates have pass=True AND no REQUIRED gate carries an
    UNKNOWN-class reason (UNKNOWN/UNOBSERVED/NOT_DETERMINABLE/HEAD_MISMATCH/...
    /FILE_MISSING/PARSE_ERROR/SUBPROCESS_TIMEOUT/RUN_ID_MISMATCH).
  - Otherwise: "FAIL".  ADVISORY gate failures do not block verdict but are
    surfaced in the report.
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_readiness_v1_readonly import usable_providers_from_db

# Verdict-blocking reasons.  Any REQUIRED gate returning one of these reasons is
# treated as FAIL (UNKNOWN-class), never as PASS even if its ``pass`` field is
# True.  ADVISORY gates are exempt.
UNKNOWN_REASONS = frozenset({
    "UNKNOWN",
    "UNOBSERVED",
    "NOT_DETERMINABLE",
    "HEAD_MISMATCH",
    "FILE_MISSING",
    "PARSE_ERROR",
    "SUBPROCESS_TIMEOUT",
    "RUN_ID_MISMATCH",
    "DB_PATH_NOT_SET",
    "OBSERVED:FILE_MISSING",
    "OBSERVED:PARSE_ERROR",
    "OBSERVED:HEAD_MISMATCH",
    "OBSERVED:RUN_ID_MISMATCH",
})

# Backwards-compat alias used by older imports / tests.
INCONCLUSIVE_REASONS = UNKNOWN_REASONS

REQUIRED_GATES = frozenset({
    "g1_all_pytest_pass",
    "g2_audit_regression_pass",
    "g3_entry_integration_tests_pass",
    "g4_full_cost_nav_wired",
    "g5_liquidation_unit_matrix",
    "g6_no_grant_no_virtual_position",
    "g7_grant_baseline_sync",
    "g8_pool_state_excludes_invalid",
    "g9_reconciliation_binding_failclose",
    "g10_coverage_denominator_consistent",
    "g14_keys_created_zero",
    "g15_signatures_zero",
    "g16_broadcasts_zero",
})

ADVISORY_GATES = frozenset({
    "g11_two_providers_usable",
    "g12_live_allowed_false",
    "g13_tiny_live_authorized_false",
})

VALID_AUDIT_MODES = frozenset({
    "AST_EXTRACTED_FULL",
    "AST_EXTRACTED_PARTIAL",
    "AST_EXTRACTED_SUMMARY",
    "AST_EXTRACTED_RULES",
    "AST_EXTRACTED_RH02_SERIES",
    "AST_EXTRACTED_RULES_V1",
    "AST_EXTRACTED_RULES_V2",
    "AST_EXTRACTED_RULES_V3",
    "AST_EXTRACTED_AUDIT_PROBE",
    "REPO_CHECKOUT",
    "REPO_CHECKOUT_FULL",
    "REPO_CHECKOUT_PARTIAL",
})


def _run_pytest_gate(target_args: list[str], timeout: int = 120) -> dict:
    """Run pytest with subprocess; parse JUnit XML for ground truth.

    PASS only when JUnit file exists, is non-empty, and reports
    ``failures==0`` and ``errors==0`` with at least one test collected.
    """
    run_dir = Path(tempfile.mkdtemp(prefix="lpbot-readiness-"))
    junit_path = run_dir / "junit.xml"
    cmd = [
        sys.executable, "-m", "pytest", *target_args,
        "-q", "--tb=no", "-p", "no:cacheprovider",
        "--junitxml", str(junit_path),
        "--no-header",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pass": False, "evidence": {"timeout": True, "junit_path": str(junit_path)},
                "reason": "SUBPROCESS_TIMEOUT"}

    evidence: dict[str, Any] = {
        "returncode": proc.returncode,
        "junit_path": str(junit_path),
    }
    if not junit_path.exists() or junit_path.stat().st_size == 0:
        return {"pass": False, "evidence": evidence,
                "reason": "FILE_MISSING" if not junit_path.exists() else "PARSE_ERROR"}

    try:
        tree = ET.parse(str(junit_path))
        root = tree.getroot()
        testsuite = root if root.tag == "testsuite" else root.find("testsuite")
        if testsuite is None:
            return {"pass": False, "evidence": evidence, "reason": "PARSE_ERROR"}
        tests = int(testsuite.get("tests", "0") or 0)
        failures = int(testsuite.get("failures", "0") or 0)
        errors = int(testsuite.get("errors", "0") or 0)
        skipped = int(testsuite.get("skipped", "0") or 0)
        evidence.update({"tests": tests, "failures": failures, "errors": errors, "skipped": skipped})
    except (ET.ParseError, ValueError) as exc:
        return {"pass": False, "evidence": {**evidence, "parse_exc": repr(exc)},
                "reason": "PARSE_ERROR"}

    if tests <= 0:
        return {"pass": False, "evidence": evidence, "reason": "NOT_DETERMINABLE"}

    passed = failures == 0 and errors == 0
    reason = None if passed else f"{failures} failures + {errors} errors / {tests} tests"
    return {"pass": passed, "evidence": evidence, "reason": reason}


def g1_all_pytest_pass(timeout: int = 120) -> dict:
    """1. All repository pytest tests pass."""
    return _run_pytest_gate(["tests/"], timeout=timeout)


def g2_audit_regression_pass(timeout: int = 120, json_out: str | None = None) -> dict:
    """2. Offline audit regression reproduces 0 defects and 0 errors.

    Strict schema validation:
      - audit JSON must exist and parse
      - head field must equal `git rev-parse HEAD` (when available)
      - mode field must be in VALID_AUDIT_MODES
      - probe_errors and defects_reproduced must be present as int fields
    """
    run_dir = Path(tempfile.mkdtemp(prefix="lpbot-readiness-"))
    if json_out is None:
        json_out = str(run_dir / "audit.json")
    cmd = ["python3", "tools/audit_repro/audit_repro.py", "--repo", ".",
           "--allow-other-head", "--json-out", json_out]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pass": False, "evidence": {"timeout": True}, "reason": "SUBPROCESS_TIMEOUT"}

    p = Path(json_out)
    report: dict[str, Any] = {}
    parse_source = None
    if p.exists():
        try:
            report = json.loads(p.read_text(encoding="utf-8"))
            parse_source = "file"
        except Exception as exc:
            return {"pass": False, "evidence": {"json_out": str(p), "parse_exc": repr(exc)},
                    "reason": "PARSE_ERROR"}
    else:
        return {"pass": False, "evidence": {"json_out": str(p), "exists": False},
                "reason": "FILE_MISSING"}

    if parse_source is None and proc.stdout:
        try:
            report = json.loads(proc.stdout)
            parse_source = "stdout"
        except Exception as exc:
            return {"pass": False, "evidence": {"parse_exc": repr(exc)},
                    "reason": "PARSE_ERROR"}

    # Strict schema: probe_errors and defects_reproduced MUST be present as int.
    if "probe_errors" not in report or "defects_reproduced" not in report:
        return {"pass": False, "evidence": {"report_keys": sorted(list(report.keys()))},
                "reason": "PARSE_ERROR"}
    if not isinstance(report["probe_errors"], int) or not isinstance(report["defects_reproduced"], int):
        return {"pass": False, "evidence": {
            "probe_errors_type": type(report["probe_errors"]).__name__,
            "defects_reproduced_type": type(report["defects_reproduced"]).__name__,
        }, "reason": "PARSE_ERROR"}

    errs = report["probe_errors"]
    defs = report["defects_reproduced"]

    # head field must match git rev-parse HEAD
    head = report.get("head")
    try:
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        git_head = None
    if head is None or (git_head and head != git_head):
        return {"pass": False, "evidence": {"report_head": head, "git_head": git_head,
                                              "errs": errs, "defs": defs},
                "reason": "HEAD_MISMATCH"}

    # mode field must be in VALID_AUDIT_MODES
    mode = report.get("mode")
    if mode not in VALID_AUDIT_MODES:
        return {"pass": False, "evidence": {"mode": mode, "errs": errs, "defs": defs,
                                              "valid_modes": sorted(VALID_AUDIT_MODES)},
                "reason": "NOT_DETERMINABLE"}

    # run_id sanity
    run_id = report.get("run_id")
    if run_id is None:
        return {"pass": False, "evidence": {"report_keys": sorted(list(report.keys()))},
                "reason": "PARSE_ERROR"}

    passed = (proc.returncode == 0) and (errs == 0) and (defs == 0)
    reason = None if passed else f"Audit defects: PROBE_ERROR={errs}, DEFECT_REPRODUCED={defs}"
    return {"pass": passed, "evidence": {"probe_errors": errs, "defects_reproduced": defs,
            "counts": {"PROBE_ERROR": errs, "DEFECT_REPRODUCED": defs},
            "returncode": proc.returncode, "head": head, "mode": mode, "run_id": run_id},
            "reason": reason}


def g3_entry_integration_tests_pass(timeout: int = 120) -> dict:
    """3. Entry integration tests pass."""
    args = sorted(glob.glob("tests/test_rh07_fix_c_r2_*.py")) + [
        "tests/test_lp_rh_shadow_daemon_v1_readonly.py", "tests/test_lp_rh_shadow_runner_v1_readonly.py",
    ]
    return _run_pytest_gate(args, timeout=timeout)


def g4_full_cost_nav_wired(runner_path: str | Path = "scripts/lp_rh_shadow_runner_v1_readonly.py") -> dict:
    """4. Shadow runner references SHADOW_SCENARIO and computes full cost NAV."""
    path = Path(runner_path)
    if not path.exists():
        return {"pass": False, "evidence": {"path": str(path)}, "reason": f"File not found: {path}"}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"pass": False, "evidence": {"path": str(path)}, "reason": f"AST parse error: {exc}"}

    has_scenario = any(
        (isinstance(n, ast.Constant) and n.value in ("SHADOW_SCENARIO", "DEFAULT_SCENARIO", "DEFAULT_CFG"))
        or (isinstance(n, ast.Name) and n.id in ("SHADOW_SCENARIO", "DEFAULT_SCENARIO", "DEFAULT_CFG"))
        for n in ast.walk(tree)
    )
    has_cost_nav = any(
        (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "compute_full_cost_nav")
        or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "compute_full_cost_nav")
        or (isinstance(n, ast.Attribute) and n.attr == "full_cost_nav")
        for n in ast.walk(tree)
    )
    passed = has_scenario and has_cost_nav
    return {"pass": passed, "evidence": {"has_scenario_reference": has_scenario, "has_full_cost_nav": has_cost_nav},
            "reason": None if passed else f"scenario_ref={has_scenario}, full_cost_nav_ref={has_cost_nav}"}


def _run_suite_gate(path: str, timeout: int = 120, filter_k: str | None = None) -> dict:
    if not Path(path).exists():
        return {"pass": False, "evidence": {"path": path, "exists": False}, "reason": f"BLOCKED_BY_W6: {path} not found"}
    args = [path] if not filter_k else [path, "-k", filter_k]
    return _run_pytest_gate(args, timeout=timeout)


def g5_liquidation_unit_matrix(timeout: int = 120) -> dict:
    """5. Liquidation unit matrix tests pass."""
    return _run_suite_gate("tests/test_paper_d_liquidation_matrix.py", timeout=timeout)


def g6_no_grant_no_virtual_position(timeout: int = 120) -> dict:
    """6. No-grant no-virtual-position test passes."""
    p = "tests/test_paper_a_no_grant.py"
    return _run_pytest_gate([p], timeout=timeout) if Path(p).exists() else {"pass": False, "evidence": {"path": p}, "reason": f"{p} not found"}


def g7_grant_baseline_sync(timeout: int = 120) -> dict:
    """7. Grant baseline sync test passes."""
    return _run_suite_gate("tests/test_paper_b_delayed_grant.py", timeout=timeout)


def g8_pool_state_excludes_invalid(timeout: int = 120) -> dict:
    """8. Pool state excludes invalid test passes."""
    return _run_suite_gate("tests/test_paper_e_pool_state.py", timeout=timeout)


def g9_reconciliation_binding_failclose(timeout: int = 120) -> dict:
    """9. Reconciliation binding fail-close test passes."""
    path = "tests/test_lp_rh_graduation_reconciliation_v1_readonly.py"
    filter_k = "fail_close"
    if not Path(path).exists() and Path("tests/test_rh07_fix_c_r2_05_reconciliation_evidence_selector.py").exists():
        path = "tests/test_rh07_fix_c_r2_05_reconciliation_evidence_selector.py"
        filter_k = "fails_close or fail_close"
    return _run_pytest_gate([path, "-k", filter_k], timeout=timeout)


def g10_coverage_denominator_consistent(timeout: int = 120) -> dict:
    """10. Coverage denominator consistency test passes."""
    return _run_pytest_gate(["tests/test_lp_rh_readiness_v1_readonly.py", "-k", "coverage_denom or denom"], timeout=timeout)


def g11_two_providers_usable(db_path: str | None = None) -> dict:
    """11. (ADVISORY) At least two usable providers available in rh_rpc_health."""
    resolved = db_path or os.environ.get("LPBOT_RPC_HEALTH_DB")
    if not resolved:
        return {"pass": False, "evidence": {}, "reason": "DB_PATH_NOT_SET"}
    try:
        res = usable_providers_from_db(resolved)
        count = res.get("count", 0)
        return {"pass": count >= 2, "evidence": res, "reason": None if count >= 2 else f"Only {count} usable providers (>=2 required)"}
    except Exception as exc:
        return {"pass": False, "evidence": {"error": str(exc)}, "reason": f"DB_READ_ERROR: {exc}"}


def _check_toml_flag(flag: str, config_path: str | Path | None) -> dict:
    p = Path(config_path or os.environ.get("LPBOT_CONFIG_PATH") or "configs/config.shadow.toml")
    if not p.exists():
        return {"pass": False, "evidence": {"path": str(p)}, "reason": f"Config not found: {p}"}
    has_flag = bool(re.search(rf"^\s*{flag}\s*=\s*true\b", p.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE))
    return {"pass": not has_flag, "evidence": {"path": str(p), f"{flag}_present": has_flag},
            "reason": f"{flag} = true found in config" if has_flag else None}


def g12_live_allowed_false(config_path: str | Path | None = None) -> dict:
    """12. (ADVISORY) live_allowed is not set to true in config."""
    return _check_toml_flag("live_allowed", config_path)


def g13_tiny_live_authorized_false(config_path: str | Path | None = None) -> dict:
    """13. (ADVISORY) tiny_live_authorized is not set to true in config."""
    return _check_toml_flag("tiny_live_authorized", config_path)


def _read_counters(runtime_counters_path: str | Path | None = None) -> tuple[dict, str | None]:
    """Read runtime counters JSON.  Returns (counters, reason).

    reason is None on full success, otherwise an OBSERVED:* sentinel that
    _check_counter converts into a verdict-blocking reason.
    """
    p = Path(runtime_counters_path or os.environ.get("LPBOT_RUNTIME_COUNTERS_PATH")
             or "reports/paper_runtime_counters.json")
    counters = {"keys_created": 0, "signatures": 0, "broadcasts": 0}
    if not p.exists():
        return counters, "OBSERVED:FILE_MISSING"
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        return counters, f"OBSERVED:PARSE_ERROR"
    try:
        data = json.loads(text)
    except Exception as exc:
        return counters, f"OBSERVED:PARSE_ERROR"

    if not isinstance(data, dict):
        return counters, "OBSERVED:PARSE_ERROR"

    # head/run_id cross-check when present in the counters file.
    try:
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
    except Exception:
        git_head = None
    file_head = data.get("head")
    if file_head is not None and git_head and file_head != git_head:
        return counters, "OBSERVED:HEAD_MISMATCH"
    file_run_id = data.get("run_id")
    expected_run_id = data.get("expected_run_id")
    if expected_run_id is not None and file_run_id is not None and file_run_id != expected_run_id:
        return counters, "OBSERVED:RUN_ID_MISMATCH"

    for k in counters:
        if k in data:
            try:
                counters[k] = int(data[k])
            except (TypeError, ValueError):
                return counters, "OBSERVED:PARSE_ERROR"
    return counters, None


def _check_counter(key: str, runtime_counters_path: str | Path | None) -> dict:
    c, observed_reason = _read_counters(runtime_counters_path)
    if observed_reason is not None:
        return {"pass": False, "evidence": c, "reason": observed_reason}
    val = c.get(key, 0)
    return {"pass": val == 0, "evidence": c, "reason": None if val == 0 else f"{key} is {val} (must be 0)"}


def g14_keys_created_zero(runtime_counters_path: str | Path | None = None) -> dict:
    """14. Zero unauthorized keys created."""
    return _check_counter("keys_created", runtime_counters_path)


def g15_signatures_zero(runtime_counters_path: str | Path | None = None) -> dict:
    """15. Zero unauthorized signatures produced."""
    return _check_counter("signatures", runtime_counters_path)


def g16_broadcasts_zero(runtime_counters_path: str | Path | None = None) -> dict:
    """16. Zero unauthorized broadcasts executed."""
    return _check_counter("broadcasts", runtime_counters_path)


GATE_NAMES = [
    "g1_all_pytest_pass",
    "g2_audit_regression_pass",
    "g3_entry_integration_tests_pass",
    "g4_full_cost_nav_wired",
    "g5_liquidation_unit_matrix",
    "g6_no_grant_no_virtual_position",
    "g7_grant_baseline_sync",
    "g8_pool_state_excludes_invalid",
    "g9_reconciliation_binding_failclose",
    "g10_coverage_denominator_consistent",
    "g11_two_providers_usable",
    "g12_live_allowed_false",
    "g13_tiny_live_authorized_false",
    "g14_keys_created_zero",
    "g15_signatures_zero",
    "g16_broadcasts_zero",
]


def compute_paper_readiness(
    *, db_path: str | None = None, config_path: str | None = None, runtime_counters_path: str | None = None
) -> dict:
    """Compute aggregate Paper readiness across all 16 gates.

    verdict == "PASS" iff every REQUIRED gate is pass=True AND no REQUIRED gate
    has a verdict-blocking reason (UNKNOWN/UNOBSERVED/NOT_DETERMINABLE/...).

    ADVISORY gates DO NOT block verdict but are surfaced in the gates dict and
    contribute to advisory_unknown in the summary.
    """
    mod = sys.modules[__name__]
    gates: dict[str, dict] = {}
    passed, failed, unknown = 0, 0, 0
    advisory_failed = 0
    kw_map = {
        "g11_two_providers_usable": {"db_path": db_path},
        "g12_live_allowed_false": {"config_path": config_path},
        "g13_tiny_live_authorized_false": {"config_path": config_path},
        "g14_keys_created_zero": {"runtime_counters_path": runtime_counters_path},
        "g15_signatures_zero": {"runtime_counters_path": runtime_counters_path},
        "g16_broadcasts_zero": {"runtime_counters_path": runtime_counters_path},
    }
    for name in GATE_NAMES:
        fn = getattr(mod, name)
        kw = kw_map.get(name, {})
        res = fn(**kw) if kw else fn()
        gates[name] = res
        is_pass = res.get("pass") is True
        reason = res.get("reason")
        is_advisory = name in ADVISORY_GATES
        if is_pass:
            passed += 1
        elif reason in UNKNOWN_REASONS:
            unknown += 1
            if is_advisory:
                advisory_failed += 1
        else:
            if is_advisory:
                advisory_failed += 1
            else:
                failed += 1

    # REQUIRED-only verdict check: any unknown OR failed on a REQUIRED gate -> FAIL.
    required_fail = False
    for name in REQUIRED_GATES:
        g = gates.get(name, {})
        if g.get("pass") is not True:
            required_fail = True
            break

    verdict = "PASS" if not required_fail else "FAIL"

    return {
        "verdict": verdict,
        "gates": gates,
        "summary": {
            "passed": passed,
            "failed": failed,
            "unknown": unknown,
            "inconclusive": unknown,  # back-compat
            "advisory_unknown": advisory_failed,
        },
    }


def render_report(verdict_dict: dict, *, out_path: Path) -> None:
    """Render Markdown report for paper readiness verdict."""
    verdict = verdict_dict.get("verdict", "UNKNOWN")
    summary = verdict_dict.get("summary", {})
    lines = [
        "# Paper Readiness Report",
        "",
        f"- **Verdict**: `{verdict}`",
        f"- **Passed**: {summary.get('passed') or 0}",
        f"- **Failed**: {summary.get('failed') or 0}",
        f"- **Unknown**: {summary.get('unknown') or 0}",
        f"- **Advisory unknowns**: {summary.get('advisory_unknown') or 0}",
        "",
        "| Gate | Tier | Status | Reason |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for name, g in verdict_dict.get("gates", {}).items():
        tier = "ADVISORY" if name in ADVISORY_GATES else "REQUIRED"
        if g.get("pass") is True:
            status = "PASS"
        elif g.get("reason") in UNKNOWN_REASONS:
            status = "UNKNOWN"
        else:
            status = "FAIL"
        reason = g.get("reason") or "OK"
        lines.append(f"| `{name}` | {tier} | **{status}** | {reason} |")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """CLI endpoint."""
    parser = argparse.ArgumentParser(description="Aggregate 16 Paper readiness gates.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--config-path", type=str, default=None)
    parser.add_argument("--runtime-counters", type=str, default=None)
    args = parser.parse_args()

    verdict_dict = compute_paper_readiness(
        db_path=args.db_path,
        config_path=args.config_path,
        runtime_counters_path=args.runtime_counters,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(verdict_dict, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        render_report(verdict_dict, out_path=args.md_out)
    return 0 if verdict_dict.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
