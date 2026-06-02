"""Read-only wallet-bound unsigned tx package builder for Base 10/20U probe.

Phase I of LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1.

This script:
  1. Builds the unsigned mint call data for Uniswap V3 NPM (Base) on the
     WETH/USDC 0.01% pool, with:
       - recipient = the user-bound wallet (placeholder OK; the script binds
         the wallet address from PHASE_E so the package is wallet-bound)
       - deadline = DEADLINE_PLACEHOLDER (uint256 max safe, never expires
         immediately; user will override at execution time)
       - amount0Desired / amount1Desired = from Phase H
       - amount0Min / amount1Min = with 0.5% slippage buffer
  2. Does NOT sign or send anything. The output is JSON / Markdown only.
  3. Builds the matching ERC20.approve call data for USDC (ApproveExact) since
     USDC allowance < 10/20 USDC needed.

ApproveExact policy: never ApproveMax. After LP exit, the script also builds
the matching approve(NPM, 0) revoke call (per invariant #10).

Strictly read-only. No signing, no transaction, no wallet client.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# === Frozen inputs (mirror scripts/lp_base_pool_state_refresh_v1_readonly.py) ===
CHAIN_ID = 8453
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
WALLET_MASK = "0xb05b...d835"
POOL = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
TOKEN0_WETH = "0x4200000000000000000000000000000000000006"
TOKEN1_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
FEE = 100
TICK_LOW = -200643
TICK_HIGH = -200243
NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"

# ApproveExact amount (USDC) — mirrors Phase H
# 10U: 10_000_000 (already covered by 5 current allowance: needs +10_000_000 more; approve 10_000_000 to be safe)
# 20U: 20_000_000 (current 5 < 20; needs +20_000_000 more; approve 20_000_000)
AMOUNTS = {
    10: {
        "amount0_desired_wei": 0,
        "amount1_desired_raw": 10_000_000,
        "amount0_min_wei": 0,
        "amount1_min_raw": 9_949_999,
        "usdc_approve_amount_raw": 10_000_000,
    },
    20: {
        "amount0_desired_wei": 0,
        "amount1_desired_raw": 20_000_000,
        "amount0_min_wei": 0,
        "amount1_min_raw": 19_899_999,
        "usdc_approve_amount_raw": 20_000_000,
    },
}

# Function selectors
# NonfungiblePositionManager.mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))
SEL_MINT = "0x88316456"
# ERC20.approve(address,uint256)
SEL_APPROVE = "0x095ea7b3"

# Deadline placeholder: very large but capped so the package shows
# the human is expected to override at execution time. We use a far-future
# timestamp (year 2099) and label it PLACEHOLDER so the human approves.
DEADLINE_PLACEHOLDER = 4070908800  # 2099-01-01 UTC


def int_padded(v: int) -> str:
    return hex(max(v, 0))[2:].rjust(64, "0")


def addr_padded(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


def int24_padded(v: int) -> str:
    # int24 signed, encoded as uint256
    if v < 0:
        v = (1 << 256) + v
    return hex(v)[2:].rjust(64, "0")


def encode_mint(
    token0: str, token1: str, fee: int, tick_lower: int, tick_upper: int,
    amount0_desired: int, amount1_desired: int, amount0_min: int, amount1_min: int,
    recipient: str, deadline: int,
) -> str:
    # Static encoding for tuple arg
    # selector + offset 0x20 + 11 fields
    body = (
        "0" * 62 + "20"
        + addr_padded(token0)
        + addr_padded(token1)
        + int_padded(fee)
        + int24_padded(tick_lower)
        + int24_padded(tick_upper)
        + int_padded(amount0_desired)
        + int_padded(amount1_desired)
        + int_padded(amount0_min)
        + int_padded(amount1_min)
        + addr_padded(recipient)
        + int_padded(deadline)
    )
    return SEL_MINT + body


def encode_approve(spender: str, amount: int) -> str:
    return SEL_APPROVE + addr_padded(spender) + int_padded(amount)


def build_package(notional: int) -> dict:
    a = AMOUNTS[notional]
    mint_data = encode_mint(
        token0=TOKEN0_WETH, token1=TOKEN1_USDC, fee=FEE,
        tick_lower=TICK_LOW, tick_upper=TICK_HIGH,
        amount0_desired=a["amount0_desired_wei"],
        amount1_desired=a["amount1_desired_raw"],
        amount0_min=a["amount0_min_wei"],
        amount1_min=a["amount1_min_raw"],
        recipient=WALLET,
        deadline=DEADLINE_PLACEHOLDER,
    )
    approve_usdc_data = encode_approve(NPM, a["usdc_approve_amount_raw"])
    approve_usdc_revoke_data = encode_approve(NPM, 0)
    return {
        "notional_usd": notional,
        "chain_id": CHAIN_ID,
        "wallet_address": WALLET,
        "wallet_address_masked": WALLET_MASK,
        "pool": POOL,
        "npm": NPM,
        "tx_sequence": [
            {
                "step": 1,
                "action": "ERC20.approve",
                "from": WALLET,
                "to": TOKEN1_USDC,
                "value_wei": 0,
                "data": approve_usdc_data,
                "data_meaning": {
                    "function": "approve(address,uint256)",
                    "selector": SEL_APPROVE,
                    "spender": NPM,
                    "amount_raw": a["usdc_approve_amount_raw"],
                    "amount_human": f"{a['usdc_approve_amount_raw']/1e6:.6f} USDC",
                    "policy": "ApproveExact (never ApproveMax)"
                },
                "invariant_check": "approve_never_max; amount equals LP-required USDC"
            },
            {
                "step": 2,
                "action": "NonfungiblePositionManager.mint",
                "from": WALLET,
                "to": NPM,
                "value_wei": 0,
                "data": mint_data,
                "data_meaning": {
                    "function": "mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))",
                    "selector": SEL_MINT,
                    "token0": TOKEN0_WETH,
                    "token1": TOKEN1_USDC,
                    "fee": FEE,
                    "tickLower": TICK_LOW,
                    "tickUpper": TICK_HIGH,
                    "amount0Desired_wei": a["amount0_desired_wei"],
                    "amount1Desired_raw": a["amount1_desired_raw"],
                    "amount0Min_wei": a["amount0_min_wei"],
                    "amount1Min_raw": a["amount1_min_raw"],
                    "recipient": WALLET,
                    "deadline": DEADLINE_PLACEHOLDER,
                    "deadline_iso": "2099-01-01T00:00:00Z",
                    "deadline_is_placeholder": True
                },
                "invariant_check": "recipient=wallet; deadline non-zero (far-future placeholder); amount0Min/amount1Min non-zero where amount>0"
            },
            {
                "step": 3,
                "action": "[decreaseLiquidity + collect + revoke (placeholder for next stage)]",
                "from": WALLET,
                "to": NPM,
                "value_wei": 0,
                "data": "<decreaseLiquidity call to be built when probe execution is approved>",
                "data_meaning": {
                    "note": "decreaseLiquidity + collect + ERC20.approve(NPM, 0) revoke will be built by the next stage (LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1 or similar) when execution is approved. This stage only ships the mint+approve package.",
                    "post_exit_revoke_invariant_10": "approve(NPM, 0) for both WETH and USDC after collect"
                }
            },
            {
                "step": 4,
                "action": "ERC20.approve (USDC revoke — per invariant #10, post-exit)",
                "from": WALLET,
                "to": TOKEN1_USDC,
                "value_wei": 0,
                "data": approve_usdc_revoke_data,
                "data_meaning": {
                    "function": "approve(address,uint256)",
                    "selector": SEL_APPROVE,
                    "spender": NPM,
                    "amount_raw": 0,
                    "amount_human": "0 USDC",
                    "policy": "post-exit revoke (ApproveMax never used; revoke to 0)"
                }
            }
        ],
        "approval_phase_summary": {
            "weth_approve_required": False,
            "weth_approve_amount_wei": 0,
            "usdc_approve_required": True,
            "usdc_approve_amount_raw": a["usdc_approve_amount_raw"],
            "usdc_revoke_required": True
        }
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=os.environ.get("REPORT_DIR", os.getcwd()))
    args = p.parse_args()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    out: dict = {
        "stage": "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
        "phase": "I_wallet_bound_unsigned_package",
        "ts": int(time.time()),
        "wallet_address_masked": WALLET_MASK,
        "frozen_pool": POOL,
        "npm": NPM,
        "chain_id": CHAIN_ID,
        "deadline_placeholder": DEADLINE_PLACEHOLDER,
        "deadline_placeholder_iso": "2099-01-01T00:00:00Z",
        "deadline_is_placeholder": True,
        "packages": {
            "10U": build_package(10),
            "20U": build_package(20)
        },
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "approval_max_never_used": True,
        "post_exit_revoke_invariant_10_planned": True
    }

    (run_dir / "wallet_bound_unsigned_package.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
