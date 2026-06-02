#!/usr/bin/env python3
"""Base 10U LP probe READINESS MONITOR v1 (read-only; 8-10h loop).

This monitor watches the candidate Uniswap V3 (Base) WETH/USDC 0.01%
pool and the candidate wallet, recording each checkpoint to local
files in --output-dir. It NEVER sends, signs, or touches chain state.
It uses only read-only RPC (eth_chainId, eth_blockNumber, eth_call,
eth_getBalance, eth_estimateGas only in unsigned form).

Loop semantics:
  * interval = --interval-minutes (default 10)
  * runs for --max-hours (default 8) unless interrupted
  * on SIGINT/SIGTERM, writes a graceful stop record
  * --finalize re-scans the checkpoint dir and writes the FINAL summary
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lp_base_10u_probe_executor_v2 as v2  # noqa: E402
import lp_base_10u_probe_armed_runner_v1 as armed  # noqa: E402

CHAIN_ID_EXPECTED = 8453
FROZEN_TICK_CENTER = -200443
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WETH = "0x4200000000000000000000000000000000000006"


# ---------------------------------------------------------------------------

class GracefulExit(SystemExit):
    pass


def _install_signal_handlers(stop_flag: dict) -> None:
    def _h(_sig, _frm):
        stop_flag["stop"] = True
    signal.signal(signal.SIGINT, _h)
    signal.signal(signal.SIGTERM, _h)


# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_eth_call(url: str, to: str, data: str) -> str:
    return v2.rpc_call(url, "eth_call", [{"to": to, "data": data}, "latest"])


def _one_checkpoint(url: str, iteration: int) -> dict:
    """Read a single read-only snapshot of the candidate pool and wallet."""
    cp: dict = {
        "ts_iso": _now_iso(),
        "ts_unix": int(time.time()),
        "iteration": iteration,
    }

    # 1) chain id
    try:
        cid = int(v2.rpc_call(url, "eth_chainId", []), 16)
        cp["chain_id"] = cid
        cp["chain_id_match"] = (cid == CHAIN_ID_EXPECTED)
    except Exception as e:
        cp["chain_id_error"] = repr(e)

    # 2) block
    try:
        block_hex = v2.rpc_call(url, "eth_blockNumber", [])
        cp["block_number"] = int(block_hex, 16)
    except Exception as e:
        cp["block_number_error"] = repr(e)

    # 3) wallet balances
    try:
        cp["wallet_eth_wei"] = int(
            v2.rpc_call(url, "eth_getBalance", [armed.WALLET, "latest"]), 16
        )
    except Exception as e:
        cp["wallet_eth_wei_error"] = repr(e)

    try:
        cp["usdc_balance_raw"] = int(
            _safe_eth_call(url, USDC, v2.encode_balance_of(armed.WALLET)), 16
        )
    except Exception as e:
        cp["usdc_balance_error"] = repr(e)

    try:
        cp["weth_balance_raw"] = int(
            _safe_eth_call(url, WETH, v2.encode_balance_of(armed.WALLET)), 16
        )
    except Exception as e:
        cp["weth_balance_error"] = repr(e)

    # 4) allowances
    try:
        cp["usdc_allowance_raw"] = int(
            _safe_eth_call(url, USDC, v2.encode_allowance(armed.WALLET, armed.NPM)), 16
        )
    except Exception as e:
        cp["usdc_allowance_error"] = repr(e)

    try:
        cp["weth_allowance_raw"] = int(
            _safe_eth_call(url, WETH, v2.encode_allowance(armed.WALLET, armed.NPM)), 16
        )
    except Exception as e:
        cp["weth_allowance_error"] = repr(e)

    # 5) pool slot0
    try:
        slot0_raw = _safe_eth_call(url, armed.POOL, "0x3850c7bd")
        cp["pool_slot0_raw"] = slot0_raw
    except Exception as e:
        cp["pool_slot0_error"] = repr(e)

    # 6) pool liquidity
    try:
        cp["pool_liquidity_raw"] = _safe_eth_call(url, armed.POOL, "0x1a686502")
    except Exception as e:
        cp["pool_liquidity_error"] = repr(e)

    # 7) dynamic tick range (delegate to v2; read-only)
    try:
        dtr = v2.dynamic_tick_range_recompute(url, dry_run=True)
        cp["current_tick"] = dtr.get("current_tick")
        cp["drift_ticks"] = dtr.get("drift_ticks")
        cp["proposed_tick_lower"] = dtr.get("proposed_tick_lower")
        cp["proposed_tick_upper"] = dtr.get("proposed_tick_upper")
        cp["current_tick_inside_new_range"] = dtr.get("current_tick_inside_new_range")
        cp["fresh_approval_required"] = dtr.get("fresh_approval_required")
    except Exception as e:
        cp["dynamic_tick_range_error"] = repr(e)

    # 8) gas estimate (read-only; doesn't sign or send)
    try:
        gas_hex = v2.rpc_call(url, "eth_gasPrice", [])
        cp["gas_price_wei"] = int(gas_hex, 16)
    except Exception as e:
        cp["gas_price_error"] = repr(e)

    # 9) stop conditions summary
    cp["stop_conditions"] = {
        "tick_outside_new_range": (
            cp.get("current_tick_inside_new_range") is False
        ),
        "fresh_approval_required": bool(cp.get("fresh_approval_required")),
        "usdc_balance_below_threshold": (
            cp.get("usdc_balance_raw", 0) < 10 * 10**6
        ),
        "weth_balance_below_threshold": (
            cp.get("weth_balance_raw", 0) == 0
        ),
    }
    cp["any_stop_condition_active"] = any(cp["stop_conditions"].values())

    # 10) market safe for execution candidate heuristic
    safe = (
        cp.get("chain_id_match") is True
        and cp.get("current_tick_inside_new_range") is True
        and cp.get("usdc_balance_raw", 0) >= 10 * 10**6
        and cp.get("any_stop_condition_active") is False
    )
    cp["market_safe_for_execution_candidate"] = safe
    if safe:
        cp["reason"] = "all read-only checks pass; note fresh approval still required if armed runner unseal ever happens"
    else:
        cp["reason"] = "one or more read-only checks failed: " + json.dumps(
            {k: v for k, v in cp["stop_conditions"].items() if v},
            sort_keys=True
        )

    return cp


# ---------------------------------------------------------------------------

def _write_csv(csv_path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = [
        "ts_iso", "iteration", "chain_id", "block_number",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw",
        "current_tick", "drift_ticks", "proposed_tick_lower",
        "proposed_tick_upper", "current_tick_inside_new_range",
        "fresh_approval_required", "any_stop_condition_active",
        "gas_price_wei", "market_safe_for_execution_candidate",
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _read_checkpoints(checkpoints_dir: Path) -> list[dict]:
    if not checkpoints_dir.is_dir():
        return []
    out = []
    for p in sorted(checkpoints_dir.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def _finalize(checkpoints_dir: Path, out_dir: Path, run_id: str) -> int:
    rows = _read_checkpoints(checkpoints_dir)
    csv_path = out_dir / "readiness_timeseries.csv"
    _write_csv(csv_path, rows)

    ticks = [r["drift_ticks"] for r in rows if r.get("drift_ticks") is not None]
    gas = [r["gas_price_wei"] for r in rows if r.get("gas_price_wei") is not None]
    safe = sum(1 for r in rows if r.get("market_safe_for_execution_candidate") is True)
    unsafe = sum(1 for r in rows if r.get("market_safe_for_execution_candidate") is False)
    last_allow = rows[-1].get("usdc_allowance_raw") if rows else None
    last_balance = rows[-1].get("usdc_balance_raw") if rows else None

    if not rows:
        recommended = "STOP"
        reason = "no checkpoints collected"
    elif safe == 0:
        recommended = "DO_NOT_EXECUTE_MARKET_UNSAFE"
        reason = "0 checkpoints reported market_safe=true"
    elif all(r.get("fresh_approval_required") for r in rows):
        recommended = "REFRESH_DRY_RUN"
        reason = "fresh_approval_required=true throughout; re-warm allowance"
    else:
        recommended = "GO_TO_FINAL_EXECUTION_AUTHORIZATION"
        reason = "market conditions acceptable; proceed to final review (still NOT auto-execute)"

    summary = {
        "stage": "LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1",
        "run_id": run_id,
        "phase": "C7_finalize",
        "total_checkpoints": len(rows),
        "success_checkpoints": sum(
            1 for r in rows if "error" not in json.dumps(r) and r.get("chain_id_match")
        ),
        "failed_checkpoints": sum(
            1 for r in rows if "error" in json.dumps(r)
        ),
        "market_safe_count": safe,
        "market_unsafe_count": unsafe,
        "tick_drift_min": min(ticks) if ticks else None,
        "tick_drift_max": max(ticks) if ticks else None,
        "gas_estimate_min_wei": min(gas) if gas else None,
        "gas_estimate_max_wei": max(gas) if gas else None,
        "allowance_status_last": last_allow,
        "balance_status_last": last_balance,
        "recommended_operator_action": recommended,
        "recommended_reason": reason,
        "this_does_not_execute": True,
        "can_run_probe_now": False,
        "execution_allowed_now": False,
        "tiny_canary_allowed": "no",
        "send_hard_disable_active": True,
        "hard_disable_still_active": True,
    }
    summary_path = out_dir / "final_monitor_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    cn = (
        f"# Final Monitor Summary — {run_id}\n\n"
        f"- total_checkpoints: {summary['total_checkpoints']}\n"
        f"- success_checkpoints: {summary['success_checkpoints']}\n"
        f"- failed_checkpoints: {summary['failed_checkpoints']}\n"
        f"- market_safe_count: {summary['market_unsafe_count']}\n"
        f"- market_unsafe_count: {summary['market_unsafe_count']}\n"
        f"- tick_drift_min: {summary['tick_drift_min']}\n"
        f"- tick_drift_max: {summary['tick_drift_max']}\n"
        f"- gas_estimate_min_wei: {summary['gas_estimate_min_wei']}\n"
        f"- gas_estimate_max_wei: {summary['gas_estimate_max_wei']}\n"
        f"- allowance_status_last: {summary['allowance_status_last']}\n"
        f"- balance_status_last: {summary['balance_status_last']}\n"
        f"- recommended_operator_action: **{summary['recommended_operator_action']}**\n"
        f"- recommended_reason: {summary['recommended_reason']}\n\n"
        f"> Even if recommended_operator_action = GO_TO_FINAL_EXECUTION_AUTHORIZATION,\n"
        f"> this stage does NOT auto-execute. The user must explicitly request\n"
        f"> LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1 in the next prompt.\n"
    )
    (out_dir / "FINAL_MONITOR_SUMMARY_CN.md").write_text(cn)
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Base 10U LP probe READINESS MONITOR v1 (read-only)"
        )
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--wallet", default=armed.WALLET)
    p.add_argument("--pool", default=armed.POOL)
    p.add_argument("--notional", type=int, default=10)
    p.add_argument("--hold", default="15m")
    p.add_argument("--interval-minutes", type=int, default=10)
    p.add_argument("--max-hours", type=int, default=8)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--finalize", action="store_true",
                   help="Do not loop; just write FINAL summary from existing checkpoints")
    p.add_argument("--max-consecutive-rpc-failures", type=int, default=3)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    checkpoints_dir = out_dir / "checkpoints"
    log_path = out_dir / "monitor.log"
    state_path = out_dir / "state.json"
    csv_path = out_dir / "readiness_timeseries.csv"

    if args.wallet.lower() != armed.WALLET.lower():
        sys.stderr.write(f"REJECTED: wallet {args.wallet} != frozen {armed.WALLET}\n")
        return 2
    if args.notional != 10:
        sys.stderr.write(f"REJECTED: notional {args.notional} != 10\n")
        return 2
    if args.hold != "15m":
        sys.stderr.write(f"REJECTED: hold {args.hold} != 15m\n")
        return 2
    if args.pool.lower() != armed.POOL.lower():
        sys.stderr.write(f"REJECTED: pool {args.pool} != frozen {armed.POOL}\n")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    if args.finalize:
        return _finalize(checkpoints_dir, out_dir, args.run_id)

    url = v2.resolve_rpc()[0]
    log = open(log_path, "a", buffering=1)
    log.write(f"[{_now_iso()}] monitor started run_id={args.run_id} rpc={url}\n")

    rows: list[dict] = []
    state: dict = {
        "run_id": args.run_id,
        "rpc_url": url,
        "started_iso": _now_iso(),
        "interval_minutes": args.interval_minutes,
        "max_hours": args.max_hours,
        "consecutive_rpc_failures": 0,
        "degraded": False,
        "stopped_iso": None,
        "stopped_reason": None,
    }
    state_path.write_text(json.dumps(state, indent=2))

    stop_flag = {"stop": False}
    _install_signal_handlers(stop_flag)

    deadline = time.time() + args.max_hours * 3600
    iteration = 0
    try:
        while not stop_flag["stop"] and time.time() < deadline:
            iteration += 1
            try:
                cp = _one_checkpoint(url, iteration)
                state["consecutive_rpc_failures"] = 0
                state["degraded"] = False
            except Exception as e:
                state["consecutive_rpc_failures"] += 1
                log.write(f"[{_now_iso()}] rpc failure iter={iteration}: {e!r}\n")
                if state["consecutive_rpc_failures"] >= args.max_consecutive_rpc_failures:
                    state["degraded"] = True
                    log.write(
                        f"[{_now_iso()}] monitor DEGRADED after "
                        f"{state['consecutive_rpc_failures']} consecutive failures\n"
                    )
                state_path.write_text(json.dumps(state, indent=2))
                # sleep a single interval then try again
                time.sleep(args.interval_minutes * 60)
                continue

            cp_path = checkpoints_dir / f"checkpoint_{cp['ts_iso'].replace(':', '').replace('-', '')}.json"
            cp_path.write_text(json.dumps(cp, indent=2))
            rows.append(cp)
            _write_csv(csv_path, rows)
            log.write(
                f"[{cp['ts_iso']}] iter={iteration} tick={cp.get('current_tick')} "
                f"drift={cp.get('drift_ticks')} safe={cp.get('market_safe_for_execution_candidate')} "
                f"reason={cp.get('reason')}\n"
            )
            state["last_checkpoint_iso"] = cp["ts_iso"]
            state["last_tick"] = cp.get("current_tick")
            state["last_drift"] = cp.get("drift_ticks")
            state["last_market_safe"] = cp.get("market_safe_for_execution_candidate")
            state_path.write_text(json.dumps(state, indent=2))
            time.sleep(args.interval_minutes * 60)
    finally:
        if stop_flag["stop"]:
            state["stopped_reason"] = "SIGINT_or_SIGTERM"
        elif time.time() >= deadline:
            state["stopped_reason"] = "max_hours_reached"
        else:
            state["stopped_reason"] = "exit"
        state["stopped_iso"] = _now_iso()
        state_path.write_text(json.dumps(state, indent=2))
        log.write(f"[{_now_iso()}] monitor stopped reason={state['stopped_reason']}\n")
        log.close()
        _finalize(checkpoints_dir, out_dir, args.run_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
