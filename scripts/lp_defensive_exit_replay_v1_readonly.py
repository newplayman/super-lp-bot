#!/usr/bin/env python3
"""Deterministic seven-scenario defensive-exit replay (paper/read-only)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lp_exit_policy_v1_readonly import (
    ExitMode,
    ExitPolicyConfig,
    QuoteResult,
    RpcHealth,
    action_allowed,
    build_paper_action_plan,
)


SCENARIO_NAMES = (
    "lower_breach_80pct_risky",
    "remove_only",
    "remove_to_stable",
    "quote_failure",
    "slippage_limit",
    "rpc_degraded",
    "rpc_exit_only",
)

def _config() -> ExitPolicyConfig:
    return ExitPolicyConfig(
        profile="MAJORS",
        risky_token_side="token0:ETH",
        stable_token_side="token1:USDC",
        risky_inventory_target=0.25,
        max_slippage_bps=75.0,
        major_cooldown_minutes=30,
    )


def _plan_observed(plan) -> dict[str, Any]:
    observed = asdict(plan)
    observed["mode"] = plan.mode.value
    observed["next_state"] = plan.next_state.value
    return observed


def _result(
    scenario: str,
    observed: dict[str, Any],
    checks: dict[str, Callable[[dict[str, Any]], bool]],
) -> dict[str, Any]:
    assertions = {name: bool(check(observed)) for name, check in checks.items()}
    return {
        "scenario": scenario,
        "paper_only": True,
        "passed": bool(assertions) and all(assertions.values()),
        "assertions": assertions,
        "observed": observed,
    }


def _lower_eighty_percent() -> dict[str, Any]:
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_ONLY,
        rpc_health=RpcHealth.NORMAL,
        quote=None,
        config=_config(),
        post_trade_risky_inventory_ratio=0.82,
        exit_latency_loss_usd=1.0,
    )
    return _result(
        "lower_breach_80pct_risky",
        _plan_observed(plan),
        {
            "inventory_at_least_80pct": lambda x: x["post_trade_risky_inventory_ratio"] >= 0.80,
            "remove_does_not_complete_risk_off": lambda x: not x["risk_off_complete"],
            "cannot_enter_cooldown": lambda x: x["next_state"] == "EXITING",
        },
    )


def _remove_only() -> dict[str, Any]:
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_ONLY,
        rpc_health=RpcHealth.NORMAL,
        quote=None,
        config=_config(),
        post_trade_risky_inventory_ratio=0.20,
    )
    return _result(
        "remove_only",
        _plan_observed(plan),
        {
            "remove_is_simulated": lambda x: x["remove_simulated"],
            "swap_not_requested": lambda x: not x["swap_requested"],
            "swap_not_allowed": lambda x: not x["swap_allowed"],
            "inventory_target_met": lambda x: x["risk_off_complete"],
        },
    )


def _remove_to_stable() -> dict[str, Any]:
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_TO_STABLE,
        rpc_health=RpcHealth.NORMAL,
        quote=QuoteResult.ok(expected_slippage_bps=20.0, expected_swap_cost_usd=2.0),
        config=_config(),
        post_trade_risky_inventory_ratio=0.25,
        actual_slippage_bps=22.0,
        exit_latency_loss_usd=0.75,
    )
    return _result(
        "remove_to_stable",
        _plan_observed(plan),
        {
            "quote_required": lambda x: x["quote_required"],
            "quote_passed": lambda x: x["quote_succeeded"],
            "swap_allowed": lambda x: x["swap_allowed"],
            "slippage_fields_recorded": lambda x: (
                x["expected_slippage_bps"] == 20.0 and x["actual_slippage_bps"] == 22.0
            ),
            "latency_loss_field_recorded": lambda x: x["exit_latency_loss_usd"] == 0.75,
        },
    )


def _quote_failure() -> dict[str, Any]:
    plan = build_paper_action_plan(
        mode=ExitMode.REMOVE_TO_STABLE,
        rpc_health=RpcHealth.NORMAL,
        quote=QuoteResult.failed("quote_timeout"),
        config=_config(),
        post_trade_risky_inventory_ratio=0.82,
    )
    return _result(
        "quote_failure",
        _plan_observed(plan),
        {
            "no_swap": lambda x: not x["swap_allowed"],
            "staged_limit_exit": lambda x: x["substate"] == "staged/limit_exit",
            "alerted": lambda x: x["alert"],
            "reason_recorded": lambda x: x["block_reason"] == "quote_failed",
        },
    )


def _slippage_limit() -> dict[str, Any]:
    plan = build_paper_action_plan(
        mode=ExitMode.PANIC_EXIT,
        rpc_health=RpcHealth.NORMAL,
        quote=QuoteResult.ok(expected_slippage_bps=125.0, expected_swap_cost_usd=12.5),
        config=_config(),
        post_trade_risky_inventory_ratio=0.90,
    )
    return _result(
        "slippage_limit",
        _plan_observed(plan),
        {
            "panic_never_blind_swaps": lambda x: not x["swap_allowed"],
            "staged_limit_exit": lambda x: x["substate"] == "staged/limit_exit",
            "alerted": lambda x: x["alert"],
            "reason_recorded": lambda x: x["block_reason"] == "slippage_limit",
        },
    )


def _rpc_observed(health: RpcHealth) -> dict[str, Any]:
    return {
        "rpc_health": health.value,
        "open_allowed": action_allowed(health, "open"),
        "add_allowed": action_allowed(health, "add"),
        "monitor_allowed": action_allowed(health, "monitor"),
        "remove_allowed": action_allowed(health, "remove"),
        "collect_allowed": action_allowed(health, "collect"),
        "swap_to_usdc_allowed": action_allowed(health, "swap_to_usdc"),
        "rebalance_allowed": action_allowed(health, "rebalance"),
        "approve_allowed": action_allowed(health, "approve"),
    }


def _rpc_degraded() -> dict[str, Any]:
    return _result(
        "rpc_degraded",
        _rpc_observed(RpcHealth.DEGRADED),
        {
            "open_and_add_blocked": lambda x: not x["open_allowed"] and not x["add_allowed"],
            "inventory_monitoring_continues": lambda x: x["monitor_allowed"],
            "risk_reduction_allowed": lambda x: (
                x["remove_allowed"] and x["collect_allowed"] and x["swap_to_usdc_allowed"]
            ),
        },
    )


def _rpc_exit_only() -> dict[str, Any]:
    return _result(
        "rpc_exit_only",
        _rpc_observed(RpcHealth.EXIT_ONLY),
        {
            "only_reduction_allowlist": lambda x: (
                x["remove_allowed"] and x["collect_allowed"] and x["swap_to_usdc_allowed"]
            ),
            "growth_actions_blocked": lambda x: (
                not x["open_allowed"] and not x["add_allowed"] and not x["rebalance_allowed"]
            ),
            "approve_blocked": lambda x: not x["approve_allowed"],
        },
    )


def run_scenarios() -> list[dict[str, Any]]:
    """Run all deterministic scenarios; callers can assert every result."""
    results = [
        _lower_eighty_percent(),
        _remove_only(),
        _remove_to_stable(),
        _quote_failure(),
        _slippage_limit(),
        _rpc_degraded(),
        _rpc_exit_only(),
    ]
    if tuple(row["scenario"] for row in results) != SCENARIO_NAMES:
        raise AssertionError("defensive replay scenario set/order changed")
    return results


def write_report(*, out_root: Path | str | None = None, stamp: str | None = None) -> Path:
    """Write a new replay report directory; existing reports are never modified."""
    root = Path(out_root) if out_root is not None else _REPO_ROOT / "reports" / "lp_defensive_exit_replay"
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = root / stamp
    report_dir.mkdir(parents=True, exist_ok=False)
    results = run_scenarios()
    passed_count = sum(1 for row in results if row["passed"])
    payload = {
        "schema_version": "lp_defensive_exit_replay_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "safety": {
            "private_key": False,
            "signing": False,
            "approval": False,
            "broadcast": False,
            "paid_service": False,
        },
        "passed": passed_count == len(results),
        "passed_scenarios": passed_count,
        "total_scenarios": len(results),
        "results": results,
    }
    (report_dir / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Defensive Exit Replay v1",
        "",
        f"Result: **{passed_count}/{len(results)} PASS**",
        "",
        "M0 paper-only replay: no signing, approval, or broadcast; no paid service.",
        "",
        "| Scenario | Result |",
        "|---|---|",
    ]
    lines.extend(
        f"| `{row['scenario']}` | {'PASS' if row['passed'] else 'FAIL'} |" for row in results
    )
    (report_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper-only defensive exit replay")
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--stamp", default=None)
    args = parser.parse_args()
    report_dir = write_report(out_root=args.out_root, stamp=args.stamp)
    print(report_dir)


if __name__ == "__main__":
    main()
