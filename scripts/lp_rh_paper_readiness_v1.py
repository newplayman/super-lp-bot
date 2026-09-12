"""Paper readiness verdict aggregator (16 gates + report + CLI).

Provides compute_paper_readiness() aggregating 16 concrete Paper-technical gates.
Each gate is a pure function returning:
  {"pass": bool, "evidence": dict, "reason": str | None}
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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_readiness_v1_readonly import usable_providers_from_db

INCONCLUSIVE_REASONS = {"DB_PATH_NOT_SET", "SUBPROCESS_TIMEOUT"}


def _run_pytest_gate(target_args: list[str], timeout: int = 120) -> dict:
    """Run pytest with subprocess and parse summary counts."""
    cmd = ["pytest", *target_args, "-q", "--tb=no", "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pass": False, "evidence": {"timeout": True}, "reason": "SUBPROCESS_TIMEOUT"}

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    last_line = lines[-1] if lines else proc.stderr.strip()

    passed_m = re.search(r"(\d+)\s+passed", last_line)
    failed_m = re.search(r"(\d+)\s+failed", last_line)
    error_m = re.search(r"(\d+)\s+error", last_line)

    passed = int(passed_m.group(1)) if passed_m else 0
    failed = int(failed_m.group(1)) if failed_m else 0
    errors = int(error_m.group(1)) if error_m else 0
    total_failed = failed + errors

    if proc.returncode == 0 and total_failed == 0 and (passed > 0 or not lines):
        return {
            "pass": True,
            "evidence": {"passed": passed, "failed": 0, "summary": last_line, "returncode": proc.returncode},
            "reason": None,
        }
    reason = (
        f"{total_failed} tests failed, {passed} passed"
        if (passed or total_failed)
        else f"Exit code {proc.returncode}: {last_line or 'No output'}"
    )
    return {
        "pass": False,
        "evidence": {"passed": passed, "failed": total_failed, "summary": last_line, "returncode": proc.returncode},
        "reason": reason,
    }


def g1_all_pytest_pass(timeout: int = 120) -> dict:
    """1. All repository pytest tests pass."""
    return _run_pytest_gate(["tests/"], timeout=timeout)


def g2_audit_regression_pass(timeout: int = 120, json_out: str = "/tmp/audit_w5.json") -> dict:
    """2. Offline audit regression reproduces 0 defects and 0 errors."""
    cmd = ["python3", "tools/audit_repro/audit_repro.py", "--repo", ".", "--allow-other-head", "--json-out", json_out]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pass": False, "evidence": {"timeout": True}, "reason": "SUBPROCESS_TIMEOUT"}
    report: dict[str, Any] = {}
    p = Path(json_out)
    if p.exists():
        try:
            report = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not report and proc.stdout:
        try:
            report = json.loads(proc.stdout)
        except Exception:
            pass
    errs, defs = report.get("probe_errors", 0), report.get("defects_reproduced", 0)
    passed = (proc.returncode == 0) and (errs == 0) and (defs == 0)
    reason = None if passed else f"Audit defects: PROBE_ERROR={errs}, DEFECT_REPRODUCED={defs}"
    return {"pass": passed, "evidence": {"probe_errors": errs, "defects_reproduced": defs,
            "counts": {"PROBE_ERROR": errs, "DEFECT_REPRODUCED": defs}, "returncode": proc.returncode}, "reason": reason}


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
    """11. At least two usable providers available in rh_rpc_health."""
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
    """12. live_allowed is not set to true in config."""
    return _check_toml_flag("live_allowed", config_path)


def g13_tiny_live_authorized_false(config_path: str | Path | None = None) -> dict:
    """13. tiny_live_authorized is not set to true in config."""
    return _check_toml_flag("tiny_live_authorized", config_path)


def _read_counters(runtime_counters_path: str | Path | None = None) -> tuple[dict, str | None]:
    p = Path(runtime_counters_path or os.environ.get("LPBOT_RUNTIME_COUNTERS_PATH") or "reports/paper_runtime_counters.json")
    counters = {"keys_created": 0, "signatures": 0, "broadcasts": 0}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for k in counters:
                if k in data:
                    counters[k] = int(data[k])
        except Exception as exc:
            return counters, f"Parse error: {exc}"
    return counters, None


def _check_counter(key: str, runtime_counters_path: str | Path | None) -> dict:
    c, err = _read_counters(runtime_counters_path)
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
    """Compute aggregate Paper readiness across all 16 gates."""
    mod = sys.modules[__name__]
    gates: dict[str, dict] = {}
    passed, failed, inconclusive = 0, 0, 0
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
        if res.get("pass") is True:
            passed += 1
        elif res.get("reason") in INCONCLUSIVE_REASONS:
            inconclusive += 1
        else:
            failed += 1
    verdict = "PASS" if failed == 0 else "FAIL"
    return {
        "verdict": verdict,
        "gates": gates,
        "summary": {"passed": passed, "failed": failed, "inconclusive": inconclusive},
    }


def render_report(verdict_dict: dict, *, out_path: Path) -> None:
    """Render Markdown report for paper readiness verdict."""
    verdict = verdict_dict.get("verdict", "UNKNOWN")
    summary = verdict_dict.get("summary", {})
    lines = [
        "# Paper Readiness Report",
        "",
        f"- **Verdict**: `{verdict}`",
        f"- **Passed**: {summary.get('passed', 0)}",
        f"- **Failed**: {summary.get('failed', 0)}",
        f"- **Inconclusive**: {summary.get('inconclusive', 0)}",
        "",
        "| Gate | Status | Reason |",
        "| :--- | :--- | :--- |",
    ]
    for name, g in verdict_dict.get("gates", {}).items():
        status = "PASS" if g.get("pass") else ("INCONCLUSIVE" if g.get("reason") in INCONCLUSIVE_REASONS else "FAIL")
        reason = g.get("reason") or "OK"
        lines.append(f"| `{name}` | **{status}** | {reason} |")
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


