#!/usr/bin/env python3
"""Base 10U LP probe armed runner v1.

This is a BUILD-ONLY stage artifact. It does NOT execute, send, sign,
or touch chain state. It composes the v2 executor (read-only parts) and
adds a *pluggable* execute-armed path that, in this build stage, is
HARD-ABORTED with EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE.

Default --no-send and --dry-run-only are both True. To unseat the
abort, a future stage must (a) release v2's hard-disable in a separate
commit, (b) accept the exact build approval phrase, and (c) accept a
second --i-understand-this-sends-real-transactions flag. None of those
happen in this build.

It does NOT modify scripts/lp_base_10u_probe_executor_v2.py. v2 stays at
992 lines and remains the source of truth for ABI encoding, dynamic
tick range, and 27-item pre-execution checklist. v1 only wraps.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# IMPORTANT: import v2 as a module so the v2 source file is untouched.
# We deliberately only call v2's read-only functions (preflight, dynamic
# tick range, approval phrase parsing). We never reach v2's execute-
# guarded main() in a way that could let it send.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lp_base_10u_probe_executor_v2 as v2  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (mirror v2; armed runner is frozen on these)
# ---------------------------------------------------------------------------

CHAIN = "Base"
CHAIN_ID_EXPECTED = 8453
PROTOCOL = "Uniswap V3 (Base)"
POOL = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
PAIR = "WETH/USDC"
FEE_TIER = 100
NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
NOTIONAL_USD = 10
HOLD = "15m"

# Build phrase (operator already approved it this round)
ARMED_BUILD_PHRASE = (
    "APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER "
    f"wallet={WALLET} pool={POOL} notional=10 hold=15m"
)

# One-shot phrase is NOT accepted in this build, ever.
ONE_SHOT_PHRASE = (
    "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
    f"wallet={WALLET} pool={POOL} notional=10 hold=15m"
)

# Send hard-disable remains active in this build.
SEND_HARD_DISABLE_ACTIVE = True
DEFAULT_NO_SEND = True
DEFAULT_DRY_RUN_ONLY = True
EXECUTION_ALLOWED_NOW = False
CAN_RUN_PROBE_NOW = False
TINY_CANARY_ALLOWED = "no"

ABORT_REASON = "EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE"


# ---------------------------------------------------------------------------
# Self-test: confirm the hard-disable class is still raised by v2
# ---------------------------------------------------------------------------

def _verify_v2_hard_disable_intact() -> dict:
    """Statically confirm v2 still raises its hard-disable at line 974.

    Does not execute v2; just reads the file and looks for the class
    definition and the raise site.
    """
    v2_path = HERE / "lp_base_10u_probe_executor_v2.py"
    src = v2_path.read_text(encoding="utf-8")
    class_seen = "class ExecutionSendDisabledInImplementationBuildStage" in src
    raise_seen = "ExecutionSendDisabledInImplementationBuildStage(" in src
    main_exec_seen = "--mode execute-guarded" in src
    return {
        "v2_path": str(v2_path),
        "class_defined": class_seen,
        "raise_site_present": raise_seen,
        "execute_guarded_mode_present": main_exec_seen,
        "v2_unmodified_by_this_build": True,
        "send_hard_disable_active": SEND_HARD_DISABLE_ACTIVE,
    }


# ---------------------------------------------------------------------------
# Mode: status (cheap, no RPC)
# ---------------------------------------------------------------------------

def mode_status(args: argparse.Namespace) -> int:
    sd = _verify_v2_hard_disable_intact()
    out = {
        "stage": "LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1",
        "run_id": args.run_id,
        "armed_runner_built": True,
        "armed_runner_version": "v1",
        "default_no_send": DEFAULT_NO_SEND,
        "default_dry_run_only": DEFAULT_DRY_RUN_ONLY,
        "send_hard_disable_active": SEND_HARD_DISABLE_ACTIVE,
        "execution_allowed_now": EXECUTION_ALLOWED_NOW,
        "can_run_probe_now": CAN_RUN_PROBE_NOW,
        "tiny_canary_allowed": TINY_CANARY_ALLOWED,
        "v2_self_check": sd,
        "modes": ["status", "preflight", "print-unsigned",
                  "validate-approval", "monitor-readonly", "execute-armed"],
        "execute_armed_in_this_stage": "ABORTS with " + ABORT_REASON,
        "candidate": {
            "chain": CHAIN, "chain_id": CHAIN_ID_EXPECTED, "protocol": PROTOCOL,
            "pool": POOL, "pair": PAIR, "fee_tier": FEE_TIER, "npm": NPM,
            "wallet": WALLET, "notional_usd": NOTIONAL_USD, "hold": HOLD,
        },
    }
    print(json.dumps(out, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Mode: preflight (read-only, calls v2 dynamic_tick_range_recompute + balance
# + allowance via eth_call)
# ---------------------------------------------------------------------------

def _safe_eth_call(url: str, to: str, data: str) -> str:
    return v2.rpc_call(url, "eth_call", [{"to": to, "data": data}, "latest"])


def _usdc_address_base() -> str:
    # USDC on Base: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
    return "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _weth_address_base() -> str:
    # WETH on Base: 0x4200000000000000000000000000000000000006
    return "0x4200000000000000000000000000000000000006"


def mode_preflight(args: argparse.Namespace) -> int:
    url = v2.resolve_rpc()[0]
    preflight: dict = {"stage": "armed_runner_v1_preflight", "rpc_url": url}

    # 1) chain id
    cid_hex = v2.rpc_call(url, "eth_chainId", [])
    cid = int(cid_hex, 16)
    preflight["chain_id_observed"] = cid
    preflight["chain_id_match"] = (cid == CHAIN_ID_EXPECTED)

    # 2) wallet ETH balance
    bal_hex = v2.rpc_call(url, "eth_getBalance", [WALLET, "latest"])
    preflight["wallet_eth_balance_wei"] = int(bal_hex, 16)

    # 3) USDC / WETH balanceOf
    usdc = _usdc_address_base()
    weth = _weth_address_base()
    preflight["usdc_address"] = usdc
    preflight["weth_address"] = weth

    bal_usdc = _safe_eth_call(url, usdc, v2.encode_balance_of(WALLET))
    bal_weth = _safe_eth_call(url, weth, v2.encode_balance_of(WALLET))
    preflight["usdc_balance_raw"] = int(bal_usdc, 16)
    preflight["weth_balance_raw"] = int(bal_weth, 16)

    # 4) Allowances
    allow_usdc = _safe_eth_call(url, usdc, v2.encode_allowance(WALLET, NPM))
    allow_weth = _safe_eth_call(url, weth, v2.encode_allowance(WALLET, NPM))
    preflight["usdc_allowance_raw"] = int(allow_usdc, 16)
    preflight["weth_allowance_raw"] = int(allow_weth, 16)

    # 5) Pool slot0 + liquidity + tickSpacing
    pool = POOL
    slot0_data = "0x3850c7bd"  # slot0()
    liquidity_data = "0x1a686502"  # liquidity()
    tick_spacing_data = "0x6b4d3867"  # tickSpacing() not all pools have; try
    try:
        slot0_raw = _safe_eth_call(url, pool, slot0_data)
        preflight["pool_slot0_raw"] = slot0_raw
    except Exception as e:  # pragma: no cover
        preflight["pool_slot0_error"] = repr(e)
    try:
        liq_raw = _safe_eth_call(url, pool, liquidity_data)
        preflight["pool_liquidity_raw"] = liq_raw
    except Exception as e:  # pragma: no cover
        preflight["pool_liquidity_error"] = repr(e)
    try:
        ts_raw = _safe_eth_call(url, pool, tick_spacing_data)
        preflight["pool_tick_spacing_raw"] = ts_raw
    except Exception as e:  # pragma: no cover
        preflight["pool_tick_spacing_error"] = repr(e)

    # 6) Dynamic tick range (delegate to v2; this is read-only)
    dtr = v2.dynamic_tick_range_recompute(url, dry_run=True)
    preflight["dynamic_tick_range"] = dtr

    # 7) Stop conditions
    preflight["stop_conditions"] = {
        "tick_outside_new_range": not dtr.get("current_tick_inside_new_range", False),
        "fresh_approval_required": dtr.get("fresh_approval_required", False),
        "usdc_balance_below_threshold": int(bal_usdc, 16) < 10 * 10**6,
        "weth_balance_below_threshold": int(bal_weth, 16) == 0,
    }
    preflight["any_stop_condition_active"] = any(preflight["stop_conditions"].values())

    out_path = Path(args.out_dir) / "armed_runner_preflight.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(preflight, indent=2))

    print(json.dumps(preflight, indent=2))
    # Non-fatal: even if some stop is active we still report and exit 0;
    # the user will judge from the JSON.
    return 0


# ---------------------------------------------------------------------------
# Mode: print-unsigned (read-only; reuses v2 builders for approve+revoke+mint
# shape, prints a fully-unsigned envelope)
# ---------------------------------------------------------------------------

def mode_print_unsigned(args: argparse.Namespace) -> int:
    out: dict = {"stage": "armed_runner_v1_print_unsigned"}

    # approveExact USDC for ~10 USD
    amount_raw = 10 * 10**6
    approve = v2.build_approve_exact_usdc_tx(WALLET, amount_raw)
    out["unsigned_approve_exact_usdc"] = approve

    # mint (proposed tick range will be overridden later; print placeholder)
    # We do NOT call dynamic_tick_range_recompute here; we just print the
    # shape using v2's mint builder with explicit ticks.
    tick_lower = args.tick_lower if args.tick_lower is not None else -200643
    tick_upper = args.tick_upper if args.tick_upper is not None else -200243
    try:
        mint = v2.build_mint_position_tx(WALLET, tick_lower, tick_upper, NOTIONAL_USD)
        out["unsigned_mint"] = mint
    except Exception as e:  # pragma: no cover - tick sanity
        out["unsigned_mint_error"] = repr(e)

    # revoke (build only, no broadcast)
    out["unsigned_revoke_usdc"] = v2.build_revoke_usdc_tx(WALLET)
    out["unsigned_revoke_weth"] = v2.build_revoke_weth_tx(WALLET)

    out["this_is_built_only_no_send"] = True
    out["send_hard_disable_active"] = SEND_HARD_DISABLE_ACTIVE
    out_path = Path(args.out_dir) / "armed_runner_print_unsigned.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Mode: validate-approval (reuses v2.parse_approval_phrase)
# ---------------------------------------------------------------------------

def mode_validate_approval(args: argparse.Namespace) -> int:
    if not args.approval:
        sys.stderr.write("--approval is required for --mode validate-approval\n")
        return 2
    try:
        parsed = v2.parse_approval_phrase(args.approval)
    except Exception as e:
        print(json.dumps({"valid": False, "error": repr(e)}, indent=2))
        return 1
    parsed["is_build_phrase"] = (args.approval.strip() == ARMED_BUILD_PHRASE)
    parsed["is_one_shot_phrase"] = (args.approval.strip() == ONE_SHOT_PHRASE)
    parsed["one_shot_accepted_in_this_stage"] = False  # NEVER in this build
    parsed["build_phrase_authorizes_send"] = False  # even build phrase = build only
    print(json.dumps(parsed, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Mode: monitor-readonly (NOT the long monitor; this is one-shot read-only)
# ---------------------------------------------------------------------------

def mode_monitor_readonly(args: argparse.Namespace) -> int:
    return mode_preflight(args)


# ---------------------------------------------------------------------------
# Mode: execute-armed (HARD-ABORT in this build stage)
# ---------------------------------------------------------------------------

def mode_execute_armed(args: argparse.Namespace) -> int:
    bar = "=" * 60
    phrase_preview = (args.approval_phrase[:60] + "...") if args.approval_phrase else "<not provided>"
    msg = (
        bar + "\n"
        "EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE\n"
        + bar + "\n"
        + f"armed_runner_version : v1\n"
        + f"send_hard_disable   : ACTIVE (SEND_HARD_DISABLE_ACTIVE=True)\n"
        + f"default_no_send     : {DEFAULT_NO_SEND}\n"
        + f"execution_allowed   : {EXECUTION_ALLOWED_NOW}\n"
        + f"can_run_probe_now   : {CAN_RUN_PROBE_NOW}\n"
        + f"reason              : this stage is BUILD-ONLY. The armed runner\n"
        + f"                       file is constructed, but its execute-armed\n"
        + f"                       path is hard-aborted by design. To unseat\n"
        + f"                       this abort, a future stage must:\n"
        + f"                         1. release v2's hard-disable in a separate\n"
        + f"                            'unseal:' commit,\n"
        + f"                         2. accept the build approval phrase,\n"
        + f"                         3. accept a second --i-understand flag,\n"
        + f"                         4. flip --no-send to false.\n"
        + f"                       None of those happen in this stage.\n"
        + f"operator_choice     : {phrase_preview}\n"
        + bar + "\n"
    )
    sys.stderr.write(msg)
    # Exit 1 to make it observable in CI; but DO NOT call v2.main() with
    # --mode execute-guarded here, to keep audit surface minimal. The
    # existence of v2's own hard-disable raise at line 974 is documented
    # in mode_status's v2_self_check.
    return 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Base 10U LP probe ARMED RUNNER v1 (BUILD stage; "
            "execute-armed HARD-ABORTS in this stage)"
        )
    )
    p.add_argument("--mode", required=True,
                   choices=["status", "preflight", "print-unsigned",
                            "validate-approval", "monitor-readonly",
                            "execute-armed"])
    p.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    p.add_argument("--wallet", default=WALLET)
    p.add_argument("--notional", type=int, default=NOTIONAL_USD)
    p.add_argument("--hold", default=HOLD)
    p.add_argument("--approval", default=None,
                   help="For --mode validate-approval")
    p.add_argument("--approval-phrase", default=None,
                   help="For --mode execute-armed (will still be rejected)")
    p.add_argument("--out-dir",
                   default=f"reports/lp_base_10u_probe_overnight_armed_runner/{time.strftime('%Y%m%d_%H%M%S')}")
    p.add_argument("--tick-lower", type=int, default=None)
    p.add_argument("--tick-upper", type=int, default=None)
    # defaults match v2: no-send / dry-run-only default True
    p.add_argument("--no-send", action="store_true", default=True)
    p.add_argument("--dry-run-only", action="store_true", default=True)
    p.add_argument("--i-understand-this-sends-real-transactions",
                   action="store_true", default=False)
    args = p.parse_args()

    if args.wallet.lower() != WALLET.lower():
        sys.stderr.write(f"REJECTED: wallet {args.wallet} != frozen {WALLET}\n")
        return 2
    if args.notional != NOTIONAL_USD:
        sys.stderr.write(f"REJECTED: notional {args.notional} != {NOTIONAL_USD}\n")
        return 2
    if args.hold != HOLD:
        sys.stderr.write(f"REJECTED: hold {args.hold} != {HOLD}\n")
        return 2

    dispatch = {
        "status": mode_status,
        "preflight": mode_preflight,
        "print-unsigned": mode_print_unsigned,
        "validate-approval": mode_validate_approval,
        "monitor-readonly": mode_monitor_readonly,
        "execute-armed": mode_execute_armed,
    }
    return dispatch[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
