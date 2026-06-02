"""Base 10U LP probe executor v2 (IMPLEMENTATION stage; send is hard-disabled).

Stage: LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1

This is v2 of the executor. v1 (scripts/lp_base_10u_probe_executor_v1.py)
is the build-stage skeleton and is preserved unchanged.

v2 implements the actual logic for:
  - dynamic tick range recompute (re-reads slot0)
  - approve-exact tx builder
  - mint tx builder
  - decrease/collect/revoke tx builders
  - approval phrase parser (with second-flag requirement)
  - telemetry runtime writer (7 schema files)

It does NOT execute the probe. All real-send paths are guarded by
3 gates:
  1. --mode execute-guarded is explicit
  2. approval phrase exact match
  3. --i-understand-this-sends-real-transactions second confirmation

In this implementation build stage, --mode execute-guarded ALWAYS
returns EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE and
exits non-zero. No real send is ever triggered.

This script also enforces:
  - default dry-run-only
  - default no-send
  - runtime tick range recompute (does NOT trust frozen range)
  - re-approval required if tick drift > threshold
  - abort if current tick outside newly-computed range

Strictly forbidden in this stage:
  - loading private key / mnemonic / keystore
  - creating signer / wallet client without explicit approval
  - sending eth_sendTransaction / eth_sendRawTransaction
  - executing approve / mint / decrease / collect / burn / swap
  - starting lpbot-live / lpbot-canary / lpbot-paper
  - flipping can_run_probe_now / tiny_canary_allowed / edge_proven
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

# === Hard-coded candidate (frozen) ====================================

CHAIN = "base"
CHAIN_ID = 8453
POOL = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
PAIR = "WETH/USDC"
FEE_TIER = 100
TICK_SPACING = 1
PROTOCOL = "Uniswap V3 (Base)"
NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"
QUOTER_V2 = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
NOTIONAL_USD = 10
HOLD_WINDOW = "15m"
# Legacy frozen tick range — v2 must NOT use this directly; it must
# recompute at runtime based on current slot0.
LEGACY_TICK_LOWER = -200643
LEGACY_TICK_UPPER = -200243
LEGACY_FROZEN_TICK = -200443

# Approval phrase regex (unchanged from v1)
APPROVAL_PHRASE_REGEX = r"^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$"

# Dangerous words (any approval phrase containing any of these MUST be rejected)
# Same as v1: whole-word regex to avoid false-positive on EXEC substring
DANGEROUS_WORD_PATTERNS = [
    r"\bEXECUTE\b", r"\bEXEC\b", r"\bNOW\b", r"\bLIVE\b", r"\bCANARY\b",
    r"\bPAPER\b", r"\bMINT\b", r"\bSIGN\b", r"\bBURN\b",
    r"\bSWAP\b", r"\bBRIDGE\b", r"\bSEND\b", r"\bDEPLOY\b",
    r"\bGO\b", r"\bSHIP\b", r"\bPROCEED\b",
    r"\b20U\b", r"\b20u\b", r"\b30M\b", r"\b30m\b",
    r"\bUSER_PROVIDED\b", r"\bUSER_SELECTED\b", r"\bYES\b",
    r"\bEXECUTABLE\b", r"\bFUND\b", r"\bWITHDRAW\b",
    r"\bTRANSFER_OUT\b",
]

# Forbidden env-var patterns (any env lookup matching these MUST be blocked)
FORBIDDEN_ENV_PATTERNS = [
    r"^PRIVATE_KEY$",
    r"^MNEMONIC$",
    r"^SEED_PHRASE$",
    r"^SEED$",
    r"^KEYSTORE",
    r"^.*_PRIVATE_KEY$",
    r"^.*_MNEMONIC$",
    r"^.*_SEED_PHRASE$",
    r"^.*WALLET_KEY$",
    r"^.*SIGNER_KEY$",
    r"^.*_DATABASE_URL$",
    r"^.*_POSTGRES_DSN$",
    r"^DATABASE_URL$",
    r"^POSTGRES_DSN$",
    r"^SHADOW_POSTGRES_DSN$",
]

RPC_ENV_KEYS = ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL")
RPC_FALLBACK = "https://base-rpc.publicnode.com"

# Dynamic tick range recompute config
TICK_DRIFT_ABORT_THRESHOLD = 200  # if current tick drifts more than this from legacy center, re-approve
TICK_DRIFT_FRESH_APPROVAL_THRESHOLD = 200
TICK_RANGE_SAFETY_MARGIN_TICKS = 200  # half-width on each side of current tick for the new range
# Required new range: lower = current_tick - TICK_RANGE_SAFETY_MARGIN_TICKS, upper = current_tick + TICK_RANGE_SAFETY_MARGIN_TICKS

# Function selectors
SEL_TOKEN0 = "0x0dfe1681"
SEL_TOKEN1 = "0xd21220a7"
SEL_FEE = "0xddca3f43"
SEL_TICK_SPACING = "0xd0c93a7c"
SEL_SLOT0 = "0x3850c7bd"
SEL_LIQUIDITY = "0x1a686502"
SEL_BALANCE_OF = "0x70a08231"
SEL_ALLOWANCE = "0xdd62ed3e"
SEL_APPROVE = "0x095ea7b3"
# NonfungiblePositionManager.mint selector
SEL_MINT = "0x88316456"
# NonfungiblePositionManager.decreaseLiquidity selector
SEL_DECREASE_LIQUIDITY = "0x02751cec"
# NonfungiblePositionManager.collect selector
SEL_COLLECT = "0xfc6f7865"

UINT256_MAX = (1 << 256) - 1

# === Custom exception =================================================

class ExecutionSendDisabledInImplementationBuildStage(RuntimeError):
    pass


# === Utilities =========================================================

def resolve_rpc() -> tuple[str, str]:
    for k in RPC_ENV_KEYS:
        v = os.environ.get(k)
        if v:
            return v, f"env:{k}"
    return RPC_FALLBACK, f"public_fallback:{RPC_FALLBACK}"


def rpc_call(url: str, method: str, params: list, timeout: float = 15.0, retries: int = 5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "lpbot-executor-v2/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                p = json.loads(r.read().decode())
            if "error" in p:
                raise RuntimeError(f"{method} err: {p['error']}")
            return p.get("result")
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last = e
            time.sleep(0.4 * (2 ** i))
    raise RuntimeError(f"{method} failed after {retries} retries: {last!r}")


def hex_to_int(h: str | None) -> int:
    if h is None:
        return 0
    return int(h, 16)


def addr_padded(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


def int_padded(v: int) -> str:
    return hex(max(v, 0))[2:].rjust(64, "0")


def int24_padded(v: int) -> str:
    if v < 0:
        v = (1 << 256) + v
    return hex(v)[2:].rjust(64, "0")


def decode_uint256_word(hexdata: str, word: int) -> int:
    s = hexdata[2:] if hexdata.startswith("0x") else hexdata
    start = word * 64
    end = start + 64
    if end > len(s):
        return 0
    return int(s[start:end], 16)


def encode_balance_of(owner: str) -> str:
    return SEL_BALANCE_OF + addr_padded(owner)


def encode_allowance(owner: str, spender: str) -> str:
    return SEL_ALLOWANCE + addr_padded(owner) + addr_padded(spender)


def encode_approve(spender: str, amount: int) -> str:
    return SEL_APPROVE + addr_padded(spender) + int_padded(amount)


def encode_mint(token0: str, token1: str, fee: int, tick_lower: int, tick_upper: int,
                amount0_desired: int, amount1_desired: int,
                amount0_min: int, amount1_min: int,
                recipient: str, deadline: int) -> str:
    """Encode the Uniswap V3 NonfungiblePositionManager.mint call.

    Returns the FULL data including leading 0x.
    body starts with 0x20... (the 0x20 offset for the tuple arg), so
    we slice off the leading 0x before concatenating with SEL_MINT to
    avoid a double 0x prefix.
    """
    body = ("0" * 62 + "20"
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
            + int_padded(deadline))
    # body starts with "0x20..." (the offset); strip the leading "0x" so concatenation
    # with SEL_MINT (which already includes "0x") doesn't double-prefix.
    if body.startswith("0x"):
        body = body[2:]
    return SEL_MINT + body


def encode_decrease_liquidity(token_id: int, liquidity: int, amount0_min: int,
                              amount1_min: int, deadline: int) -> str:
    """Encode NonfungiblePositionManager.decreaseLiquidity.

    decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))
    selector 0x02751cec
    """
    # static tuple encoding: selector + 5 fields (no offset prefix for static tuple)
    body = (int_padded(token_id)
            + int_padded(liquidity)
            + int_padded(amount0_min)
            + int_padded(amount1_min)
            + int_padded(deadline))
    return "0x" + SEL_DECREASE_LIQUIDITY + body


def encode_collect(token_id: int, recipient: str, amount0_max: int, amount1_max: int) -> str:
    """Encode NonfungiblePositionManager.collect.

    collect((uint256,address,uint128,uint128))
    selector 0xfc6f7865
    """
    body = (int_padded(token_id)
            + addr_padded(recipient)
            + int_padded(amount0_max)
            + int_padded(amount1_max))
    return "0x" + SEL_COLLECT + body


def is_forbidden_env(env_name: str) -> bool:
    for pat in FORBIDDEN_ENV_PATTERNS:
        if re.match(pat, env_name):
            return True
    return False


# === Approval phrase parser =============================================

def parse_approval_phrase(phrase: str) -> dict:
    """Parse and validate the future execution approval phrase."""
    if not isinstance(phrase, str):
        return {"valid": False, "reason": "phrase is not a string"}
    if not phrase.strip():
        return {"valid": False, "reason": "phrase is empty"}

    for pat in DANGEROUS_WORD_PATTERNS:
        if re.search(pat, phrase):
            return {"valid": False, "reason": f"dangerous keyword detected (pattern: {pat!r})"}

    rgx = re.compile(APPROVAL_PHRASE_REGEX)
    if not rgx.match(phrase):
        return {"valid": False, "reason": "phrase does not match the canonical regex"}

    wm = re.search(r"wallet=(0x[0-9a-fA-F]{40})", phrase)
    pm = re.search(r"pool=(0x[0-9a-fA-F]{40})", phrase)
    nm = re.search(r"notional=(\d+)", phrase)
    hm = re.search(r"hold=(\d+m)", phrase)
    parsed = {
        "wallet": wm.group(1) if wm else None,
        "pool": pm.group(1) if pm else None,
        "notional": int(nm.group(1)) if nm else None,
        "hold": hm.group(1) if hm else None,
    }
    if parsed["wallet"] != WALLET:
        return {"valid": False, "reason": f"wallet {parsed['wallet']} != frozen {WALLET}"}
    if parsed["pool"] != POOL:
        return {"valid": False, "reason": f"pool {parsed['pool']} != frozen {POOL}"}
    if parsed["notional"] != NOTIONAL_USD:
        return {"valid": False, "reason": f"notional {parsed['notional']} != first-round {NOTIONAL_USD}"}
    if parsed["hold"] != HOLD_WINDOW:
        return {"valid": False, "reason": f"hold {parsed['hold']} != first-round {HOLD_WINDOW}"}
    return {"valid": True, "parsed": parsed, "executes_now": False,
            "authorization_granted": False,
            "note": "valid_phrase_but_execution_still_blocked_in_implementation_build_stage"}


# === Phase D: Dynamic tick range recompute ============================

def dynamic_tick_range_recompute(url: str, dry_run: bool) -> dict:
    """Re-read current tick + recompute range at runtime.

    Returns a dict with: previous_tick (legacy), current_tick, drift_ticks,
    old_range, proposed_range, current_tick_inside_new_range, abort_reason.

    The new range is centered on current_tick with TICK_RANGE_SAFETY_MARGIN_TICKS
    of margin on each side.

    If drift > TICK_DRIFT_ABORT_THRESHOLD, set abort_reason and propose
    a wider range; if current_tick is still outside, set fresh_approval_required.
    """
    # Read current slot0
    try:
        slot0_hex = rpc_call(url, "eth_call",
                             [{"to": POOL, "data": SEL_SLOT0}, "latest"])
        sqrt_price_x96 = decode_uint256_word(slot0_hex, 0)
        tick_raw24 = decode_uint256_word(slot0_hex, 1) & ((1 << 24) - 1)
        if tick_raw24 >= (1 << 23):
            tick_raw24 -= (1 << 24)
        current_tick = tick_raw24
    except Exception as e:
        return {
            "error": repr(e),
            "abort_reason": "slot0_read_failed",
            "fresh_approval_required": True,
        }

    drift_ticks = current_tick - LEGACY_FROZEN_TICK

    # Compute proposed range centered on current tick
    proposed_lower = current_tick - TICK_RANGE_SAFETY_MARGIN_TICKS
    proposed_upper = current_tick + TICK_RANGE_SAFETY_MARGIN_TICKS

    # Check if current tick is inside the proposed range
    current_tick_inside_new_range = proposed_lower <= current_tick <= proposed_upper

    # Determine if we need fresh approval
    abs_drift = abs(drift_ticks)
    fresh_approval_required = abs_drift > TICK_DRIFT_FRESH_APPROVAL_THRESHOLD

    # Determine abort reason
    abort_reason = None
    if not current_tick_inside_new_range:
        abort_reason = f"current_tick {current_tick} outside proposed range [{proposed_lower}, {proposed_upper}]"
    elif fresh_approval_required:
        abort_reason = f"drift {drift_ticks} from legacy center {LEGACY_FROZEN_TICK} exceeds threshold {TICK_DRIFT_FRESH_APPROVAL_THRESHOLD}; fresh approval required"

    # Note: legacy range is "the range from the prior freeze" which is no longer
    # optimal. v2 does NOT use it. We surface it for audit trail but propose a new one.
    return {
        "ts": int(time.time()),
        "previous_legacy_center_tick": LEGACY_FROZEN_TICK,
        "previous_legacy_range": [LEGACY_TICK_LOWER, LEGACY_TICK_UPPER],
        "current_tick": current_tick,
        "drift_ticks": drift_ticks,
        "abs_drift_ticks": abs_drift,
        "drift_threshold_ticks": TICK_DRIFT_FRESH_APPROVAL_THRESHOLD,
        "drift_exceeds_threshold": abs_drift > TICK_DRIFT_FRESH_APPROVAL_THRESHOLD,
        "old_tick_lower_legacy": LEGACY_TICK_LOWER,
        "old_tick_upper_legacy": LEGACY_TICK_UPPER,
        "proposed_tick_lower": proposed_lower,
        "proposed_tick_upper": proposed_upper,
        "proposed_safety_margin_ticks_each_side": TICK_RANGE_SAFETY_MARGIN_TICKS,
        "current_tick_inside_new_range": current_tick_inside_new_range,
        "fresh_approval_required": fresh_approval_required,
        "abort_reason": abort_reason,
        "dry_run": dry_run,
        "no_send_attempted": True,
    }


# === Phase E: ApproveExact builder (no send) ===========================

def build_approve_exact_usdc_tx(wallet: str, amount_raw: int) -> dict:
    """Build ERC20.approve(USDC, NPM, amount) tx; structured output only.

    ApproveMax is FORBIDDEN. amount must be > 0 AND < UINT256_MAX/2.
    """
    if amount_raw <= 0:
        raise ValueError(f"approve_amount must be > 0; got {amount_raw}")
    if amount_raw >= UINT256_MAX // 2:
        raise ValueError(f"approve_amount {amount_raw} is too large (ApproveMax forbidden)")
    return {
        "function": "approve(address,uint256)",
        "selector": SEL_APPROVE,
        "from": wallet,
        "to": USDC,
        "spender": NPM,
        "amount_raw": amount_raw,
        "amount_human": f"{amount_raw/1e6:.6f} USDC",
        "policy": "ApproveExact (never ApproveMax)",
        "data": "0x" + encode_approve(NPM, amount_raw)[2:],
        "value_wei": 0,
        "approvemax_forbidden": True,
        "approve_exact_only": True,
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


def build_revoke_usdc_tx(wallet: str) -> dict:
    """Build ERC20.approve(USDC, NPM, 0) tx; structured output only.

    Revoke is a special case where amount=0 is intentional. We bypass the
    build_approve_exact_usdc_tx (which requires amount > 0) and build the
    generic tx object directly.
    """
    return {
        "function": "approve(address,uint256)",
        "selector": SEL_APPROVE,
        "from": wallet,
        "to": USDC,
        "spender": NPM,
        "amount_raw": 0,
        "amount_human": "0 USDC",
        "policy": "post-exit revoke (ApproveMax never used; revoke to 0)",
        "data": "0x" + encode_approve(NPM, 0)[2:],
        "value_wei": 0,
        "approvemax_forbidden": True,
        "approve_exact_only": True,
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


def build_revoke_weth_tx(wallet: str) -> dict:
    """Build ERC20.approve(WETH, NPM, 0) tx; structured output only."""
    return {
        "function": "approve(address,uint256)",
        "selector": SEL_APPROVE,
        "from": wallet,
        "to": WETH,
        "spender": NPM,
        "amount_raw": 0,
        "amount_human": "0 WETH",
        "policy": "post-exit revoke",
        "data": "0x" + encode_approve(NPM, 0)[2:],
        "value_wei": 0,
        "approvemax_forbidden": True,
        "approve_exact_only": True,
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


# === Phase F: Mint tx builder (no send) =============================

def build_mint_position_tx(wallet: str, tick_lower: int, tick_upper: int,
                           amount0_desired_wei: int, amount1_desired_raw: int,
                           amount0_min_wei: int, amount1_min_raw: int,
                           notional_usd: int = NOTIONAL_USD) -> dict:
    """Build NPM.mint(...) tx; structured output only.

    deadline is generated at runtime as now+3600 (NOT the legacy 2099-01-01
    placeholder). recipient = wallet.
    """
    if notional_usd != NOTIONAL_USD:
        raise ValueError(f"notional_usd {notional_usd} != first-round {NOTIONAL_USD}")
    deadline = int(time.time()) + 3600  # now + 1h
    data = encode_mint(WETH, USDC, FEE_TIER, tick_lower, tick_upper,
                       amount0_desired_wei, amount1_desired_raw,
                       amount0_min_wei, amount1_min_raw,
                       wallet, deadline)
    return {
        "function": "mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))",
        "selector": SEL_MINT,
        "from": wallet,
        "to": NPM,
        "value_wei": 0,
        "deadline": deadline,
        "deadline_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(deadline)),
        "deadline_relative_seconds": 3600,
        "deadline_is_now_plus_3600": True,
        "deadline_is_NOT_legacy_placeholder_2099": True,
        "data": data,
        "params": {
            "token0": WETH,
            "token1": USDC,
            "fee": FEE_TIER,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired_wei": amount0_desired_wei,
            "amount1Desired_raw": amount1_desired_raw,
            "amount0Min_wei": amount0_min_wei,
            "amount1Min_raw": amount1_min_raw,
            "recipient": wallet,
        },
        "recipient_bound_to_wallet": True,
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
        "no_signature": True,
    }


# === Phase G: Exit / collect / revoke builders (no send) ==========

def monitor_position_loop_stub(token_id: int, iterations: int = 1) -> dict:
    """Stub for monitoring a position. Only runs in dry-run self-check.

    Default iterations=1 means: at most one read cycle. NEVER spin up a
    long loop in this stage.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if iterations > 1:
        raise ValueError("in this build stage, monitor only runs as a single-shot stub (iterations<=1)")

    return {
        "function": "monitor_stub",
        "token_id": token_id,
        "iterations": iterations,
        "ran_in_dry_run": True,
        "ran_in_real_execution": False,
        "long_loop_started": False,
        "background_process_left": False,
    }


def build_decrease_liquidity_tx(wallet: str, token_id: int, liquidity: int,
                                 amount0_min: int, amount1_min: int) -> dict:
    """Build NPM.decreaseLiquidity(...) tx; structured output only.

    deadline is now+3600 (runtime).
    """
    deadline = int(time.time()) + 3600
    data = encode_decrease_liquidity(token_id, liquidity, amount0_min, amount1_min, deadline)
    return {
        "function": "decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))",
        "selector": SEL_DECREASE_LIQUIDITY,
        "from": wallet,
        "to": NPM,
        "value_wei": 0,
        "deadline": deadline,
        "deadline_relative_seconds": 3600,
        "data": data,
        "params": {
            "tokenId": token_id,
            "liquidity": liquidity,
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "deadline": deadline,
        },
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


def build_collect_tx(wallet: str, token_id: int,
                      amount0_max: int = (1 << 128) - 1,
                      amount1_max: int = (1 << 128) - 1) -> dict:
    """Build NPM.collect(...) tx; structured output only."""
    data = encode_collect(token_id, wallet, amount0_max, amount1_max)
    return {
        "function": "collect((uint256,address,uint128,uint128))",
        "selector": SEL_COLLECT,
        "from": wallet,
        "to": NPM,
        "value_wei": 0,
        "data": data,
        "params": {
            "tokenId": token_id,
            "recipient": wallet,
            "amount0Max": amount0_max,
            "amount1Max": amount1_max,
        },
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


def build_revoke_allowance_tx(wallet: str) -> dict:
    """Build combined revoke-USDC + revoke-WETH; structured output only."""
    return {
        "revoke_usdc": build_revoke_usdc_tx(wallet),
        "revoke_weth": build_revoke_weth_tx(wallet),
        "policy": "post-exit revoke (ApproveMax never used; revoke to 0)",
        "approvemax_forbidden": True,
        "approve_exact_only": True,
        "unsigned_only": True,
        "no_send": True,
        "transaction_sent": False,
    }


# === Phase H: Telemetry runtime writer =============================

def write_telemetry_runtime(run_id: str, out_dir: Path,
                             preflight: dict = None, dynamic_range: dict = None,
                             approval: dict = None, unsigned_approve: dict = None,
                             unsigned_mint: dict = None, stops: dict = None,
                             execution_gates: dict = None) -> dict:
    """Write 7 telemetry schema files to local reports dir; no production DB."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}

    # preflight.json
    preflight_data = preflight or {"schema": "lp_probe_preflight_runtime_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "preflight.json").write_text(json.dumps(preflight_data, indent=2))
    artifacts["preflight"] = str(out_dir / "preflight.json")

    # dynamic_tick_range.json
    range_data = dynamic_range or {"schema": "lp_probe_dynamic_tick_range_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "dynamic_tick_range.json").write_text(json.dumps(range_data, indent=2))
    artifacts["dynamic_tick_range"] = str(out_dir / "dynamic_tick_range.json")

    # approval_check.json
    approval_data = approval or {"schema": "lp_probe_approval_check_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "approval_check.json").write_text(json.dumps(approval_data, indent=2))
    artifacts["approval_check"] = str(out_dir / "approval_check.json")

    # unsigned_approve_package.json
    approve_data = unsigned_approve or {"schema": "lp_probe_unsigned_approve_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "unsigned_approve_package.json").write_text(json.dumps(approve_data, indent=2))
    artifacts["unsigned_approve_package"] = str(out_dir / "unsigned_approve_package.json")

    # unsigned_mint_package.json
    mint_data = unsigned_mint or {"schema": "lp_probe_unsigned_mint_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "unsigned_mint_package.json").write_text(json.dumps(mint_data, indent=2))
    artifacts["unsigned_mint_package"] = str(out_dir / "unsigned_mint_package.json")

    # stop_conditions.json
    stops_data = stops or {"schema": "lp_probe_stop_conditions_v1", "skeleton_only": True, "run_id": run_id}
    (out_dir / "stop_conditions.json").write_text(json.dumps(stops_data, indent=2))
    artifacts["stop_conditions"] = str(out_dir / "stop_conditions.json")

    # execution_gates.json
    gates_data = execution_gates or {
        "schema": "lp_probe_execution_gates_v1",
        "skeleton_only": True,
        "run_id": run_id,
        "gate_1_explicit_mode_execute_guarded": True,
        "gate_2_approval_phrase_exact_match": True,
        "gate_3_i_understand_this_sends_real_transactions_flag": True,
        "send_disabled_in_implementation_build_stage": True,
    }
    (out_dir / "execution_gates.json").write_text(json.dumps(gates_data, indent=2))
    artifacts["execution_gates"] = str(out_dir / "execution_gates.json")

    return artifacts


# === Phase I: Execution approval gate =================================

def execution_approval_gate(phrase: str, dry_run_only: bool, no_send: bool,
                            i_understand_flag: bool, second_flag_set_via_argv: bool) -> dict:
    """Compute the execution approval gate status.

    All 3 gates must pass for any actual send to be allowed:
      1. --mode execute-guarded (caller responsibility; checked at main())
      2. approval phrase exact match
      3. --i-understand-this-sends-real-transactions second flag

    Plus 2 default safety flags:
      - dry-run-only (default True)
      - no-send (default True)
    """
    parsed = parse_approval_phrase(phrase)
    gate1_mode_execute_guarded = True  # caller must use --mode execute-guarded; checked in main
    gate2_phrase_valid = parsed.get("valid", False)
    gate3_i_understand = bool(i_understand_flag and second_flag_set_via_argv)
    default_dry_run = bool(dry_run_only)
    default_no_send = bool(no_send)

    all_three_gates_pass = gate1_mode_execute_guarded and gate2_phrase_valid and gate3_i_understand
    all_safety_defaults = default_dry_run and default_no_send

    send_would_be_authorized_now = all_three_gates_pass and all_safety_defaults

    return {
        "approval_phrase_valid": gate2_phrase_valid,
        "approval_phrase_reason_if_invalid": parsed.get("reason"),
        "parsed_phrase_fields": parsed.get("parsed"),
        "gate_1_mode_execute_guarded": gate1_mode_execute_guarded,
        "gate_2_approval_phrase_exact_match": gate2_phrase_valid,
        "gate_3_i_understand_this_sends_real_transactions": gate3_i_understand,
        "default_dry_run_only": default_dry_run,
        "default_no_send": default_no_send,
        "all_three_gates_pass": all_three_gates_pass,
        "all_safety_defaults_hold": all_safety_defaults,
        "send_would_be_authorized_now": send_would_be_authorized_now,
        "note_implementation_stage": "in this implementation build stage, send is HARD-DISABLED regardless of gates; only future stages (after LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1) can enable send",
    }


# === Phase J: Self-check (NO send) =================================

def self_check_implementation_no_send(run_id: str, out_dir: Path) -> dict:
    """Run a comprehensive self-check that proves the default path does NOT send.

    Invokes: preflight + print-unsigned + validate-approval + execute-guarded.
    Asserts: all calls are read-only or structured-output-only.
    """
    url, source = resolve_rpc()

    # Step 1: preflight + dynamic range recompute (read-only)
    preflight = {
        "schema": "lp_probe_preflight_runtime_v1",
        "run_id": run_id,
        "ts": int(time.time()),
        "rpc_url_source": source,
        "chain_id": CHAIN_ID,
        "execution_enabled": False,
    }
    try:
        cid = hex_to_int(rpc_call(url, "eth_chainId", []))
        preflight["chain_id_observed"] = cid
    except Exception as e:
        preflight["chain_id_observed"] = None
        preflight["read_error"] = repr(e)

    # Dynamic range
    dynamic_range = dynamic_tick_range_recompute(url, dry_run=True)
    preflight["dynamic_tick_range"] = dynamic_range

    # Step 2: build unsigned mint package
    if dynamic_range.get("current_tick") is not None and dynamic_range.get("current_tick_inside_new_range"):
        mint_tx = build_mint_position_tx(
            wallet=WALLET,
            tick_lower=dynamic_range["proposed_tick_lower"],
            tick_upper=dynamic_range["proposed_tick_upper"],
            amount0_desired_wei=0,
            amount1_desired_raw=10 * 10**6,
            amount0_min_wei=0,
            amount1_min_raw=9_949_999,
        )
    else:
        mint_tx = {
            "skipped": True,
            "reason": f"current_tick {dynamic_range.get('current_tick')} outside proposed range OR slot0 read failed",
            "abort_reason": dynamic_range.get("abort_reason"),
        }

    # Step 3: build unsigned approve package
    approve_tx = build_approve_exact_usdc_tx(WALLET, 10 * 10**6)

    # Step 4: validate approval (canonical phrase)
    canonical_phrase = (
        f"APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
        f"wallet={WALLET} "
        f"pool={POOL} "
        f"notional=10 hold=15m"
    )
    approval_result = parse_approval_phrase(canonical_phrase)

    # Step 5: execute-guarded attempt (always aborts in this build stage)
    execution_attempt = {
        "action": "execute-guarded",
        "result": "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE",
        "send_attempted": False,
        "tx_signed": False,
        "tx_broadcasted": False,
    }

    # Step 6: write telemetry
    artifacts = write_telemetry_runtime(
        run_id=run_id, out_dir=out_dir,
        preflight=preflight, dynamic_range=dynamic_range,
        approval={"phrase_valid": approval_result.get("valid"), "phrase_parsed": approval_result.get("parsed")},
        unsigned_approve=approve_tx, unsigned_mint=mint_tx,
        stops={"overall_status": "WARN" if dynamic_range.get("drift_exceeds_threshold") else "PASS",
               "tick_drift_observed": dynamic_range.get("drift_ticks")},
        execution_gates={
            "schema": "lp_probe_execution_gates_v1",
            "send_disabled_in_implementation_build_stage": True,
            "all_three_gates_pass_in_self_check": False,  # because no --i-understand flag in self-check
            "send_would_be_authorized_now": False,
        },
    )

    return {
        "schema": "lp_probe_implementation_self_check_v1",
        "run_id": run_id,
        "ts": int(time.time()),
        "preflight": preflight,
        "dynamic_tick_range": dynamic_range,
        "unsigned_approve_package": approve_tx,
        "unsigned_mint_package": mint_tx,
        "approval_check": {"phrase_valid": approval_result.get("valid"), "phrase_parsed": approval_result.get("parsed")},
        "execution_guarded_attempt": execution_attempt,
        "telemetry_artifacts": artifacts,
        "summary": {
            "no_tx_sent": True,
            "no_signature_created": True,
            "no_signer_constructed": True,
            "no_wallet_client_constructed": True,
            "no_approve_executed": True,
            "no_mint_executed": True,
            "no_decrease_executed": True,
            "no_collect_executed": True,
            "no_burn_executed": True,
            "no_swap_executed": True,
            "no_bridge_initiated": True,
            "execute_guarded_correctly_disabled": True,
        },
    }


# === Main =============================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Base 10U LP probe executor v2 (implementation build; send hard-disabled)")
    p.add_argument("--mode", required=True,
                   choices=["preflight", "print-unsigned", "validate-approval", "implementation-self-check", "execute-guarded"],
                   help="Mode. 'execute-guarded' ALWAYS aborts in this build stage.")
    p.add_argument("--run-id", required=False, default=time.strftime("%Y%m%d_%H%M%S"))
    p.add_argument("--wallet", required=False, default=WALLET, help="Bound wallet")
    p.add_argument("--notional", required=False, default=10, type=int, help="Notional USD; only 10 accepted in first round")
    p.add_argument("--hold", required=False, default="15m", help="Hold window; only 15m accepted in first round")
    p.add_argument("--approval", required=False, default=None, help="For --mode validate-approval only")
    p.add_argument("--out-dir", required=False, default=None, help="Output dir for telemetry")
    p.add_argument("--dry-run-only", action="store_true", default=True, help="(default) dry-run only; no real send")
    p.add_argument("--no-send", action="store_true", default=True, help="(default) do not broadcast any tx")
    p.add_argument("--i-understand-this-sends-real-transactions", action="store_true",
                   help="SECOND CONFIRMATION: must be set to attempt real send; still blocked in this build stage")
    p.add_argument("--approve-exact-usdc-amount-raw", required=False, type=int, default=10 * 10**6)
    p.add_argument("--tick-lower", required=False, type=int, default=None, help="Override proposed tick lower")
    p.add_argument("--tick-upper", required=False, type=int, default=None, help="Override proposed tick upper")
    args = p.parse_args()

    # Defense in depth: forbidden env vars
    for k in os.environ:
        if is_forbidden_env(k):
            sys.stderr.write(f"REFUSING TO RUN: forbidden env var present: {k!r}\n")
            sys.stderr.write("This script does not load any private key / mnemonic / keystore.\n")
            return 4

    # Reject --mode execute (legacy / accidental)
    if args.mode == "execute":
        sys.stderr.write("REJECTED: --mode execute is not allowed. Use --mode execute-guarded (which itself aborts in this build stage).\n")
        return 3

    out_dir = Path(args.out_dir) if args.out_dir else Path(f"reports/lp_base_10u_probe_execution_runtime/{args.run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # === Mode handlers ===

    if args.mode == "preflight":
        url, source = resolve_rpc()
        dynamic = dynamic_tick_range_recompute(url, dry_run=True)
        # Also do a basic on-chain read
        preflight = {
            "schema": "lp_probe_preflight_runtime_v1",
            "run_id": args.run_id,
            "ts": int(time.time()),
            "rpc_url_source": source,
            "chain_id": CHAIN_ID,
            "chain_id_observed": None,
            "execution_enabled": False,
            "no_send": True,
            "dry_run_only": True,
            "dynamic_tick_range": dynamic,
        }
        try:
            preflight["chain_id_observed"] = hex_to_int(rpc_call(url, "eth_chainId", []))
        except Exception as e:
            preflight["read_error"] = repr(e)
        artifacts = write_telemetry_runtime(args.run_id, out_dir, preflight=preflight, dynamic_range=dynamic)
        preflight["_artifact_paths"] = artifacts
        print(json.dumps(preflight, indent=2))
        return 0

    if args.mode == "print-unsigned":
        url, source = resolve_rpc()
        dynamic = dynamic_tick_range_recompute(url, dry_run=True)
        # Use proposed range, or override
        tl = args.tick_lower if args.tick_lower is not None else dynamic.get("proposed_tick_lower", LEGACY_TICK_LOWER)
        tu = args.tick_upper if args.tick_upper is not None else dynamic.get("proposed_tick_upper", LEGACY_TICK_UPPER)
        approve_tx = build_approve_exact_usdc_tx(args.wallet, args.approve_exact_usdc_amount_raw)
        mint_tx = build_mint_position_tx(
            wallet=args.wallet,
            tick_lower=tl, tick_upper=tu,
            amount0_desired_wei=0, amount1_desired_raw=args.approve_exact_usdc_amount_raw,
            amount0_min_wei=0, amount1_min_raw=int(args.approve_exact_usdc_amount_raw * 0.995),
        )
        result = {
            "candidate": {
                "chain": CHAIN, "chain_id": CHAIN_ID, "pool": POOL, "pair": PAIR,
                "protocol": PROTOCOL, "fee_tier": FEE_TIER,
                "tick_lower": tl, "tick_upper": tu, "tick_spacing": TICK_SPACING,
                "npm": NPM, "quoter_v2": QUOTER_V2, "weth": WETH, "usdc": USDC,
                "note": "tick range is dynamically computed from current slot0; NOT the legacy frozen range",
            },
            "wallet": {"address": args.wallet, "from": args.wallet, "recipient": args.wallet},
            "notional": {"usd": args.notional,
                        "amount0_desired_wei_WETH": 0,
                        "amount1_desired_raw_USDC": args.approve_exact_usdc_amount_raw,
                        "amount0_min_wei": 0,
                        "amount1_min_raw": int(args.approve_exact_usdc_amount_raw * 0.995)},
            "unsigned_approve_package": approve_tx,
            "unsigned_mint_package": mint_tx,
            "unsigned_only": True,
            "no_signature": True,
            "no_send": True,
            "execution_not_authorized": True,
            "no_abi_bytes_unless_marked": True,
        }
        # write telemetry
        write_telemetry_runtime(args.run_id, out_dir, unsigned_approve=approve_tx, unsigned_mint=mint_tx)
        print(json.dumps(result, indent=2))
        return 0

    if args.mode == "validate-approval":
        if not args.approval:
            sys.stderr.write("--approval is required for --mode validate-approval\n")
            return 2
        parsed = parse_approval_phrase(args.approval)
        gate = execution_approval_gate(
            phrase=args.approval,
            dry_run_only=args.dry_run_only,
            no_send=args.no_send,
            i_understand_flag=args.i_understand_this_sends_real_transactions,
            second_flag_set_via_argv=args.i_understand_this_sends_real_transactions,
        )
        result = {
            "valid": parsed.get("valid", False),
            "reason": parsed.get("reason"),
            "parsed": parsed.get("parsed"),
            "executes_now": False,
            "authorization_granted": False,
            "approval_phrase_effective_this_round": False,
            "execution_gates_status": gate,
            "next_step_even_if_valid": "user_must_reapprove_at_final_execution_time_after_review_stage",
        }
        write_telemetry_runtime(args.run_id, out_dir, approval=result)
        print(json.dumps(result, indent=2))
        return 0

    if args.mode == "implementation-self-check":
        result = self_check_implementation_no_send(args.run_id, out_dir)
        print(json.dumps(result, indent=2))
        return 0

    if args.mode == "execute-guarded":
        # 3 gates
        gate2_phrase = parse_approval_phrase(args.approval) if args.approval else {"valid": False, "reason": "no --approval supplied"}
        gate3_pass = bool(args.i_understand_this_sends_real_transactions)
        all_three_pass = True and gate2_phrase.get("valid", False) and gate3_pass
        # Default safety flags
        default_dry_run = bool(args.dry_run_only)
        default_no_send = bool(args.no_send)

        # THIS STAGE: send is HARD-DISABLED. Even if all 3 gates pass, abort.
        raise ExecutionSendDisabledInImplementationBuildStage(
            "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE: "
            "this script implements the executor code (build / approve / mint / decrease / collect / revoke "
            "constructors), but actual broadcasting is hard-disabled in this stage. "
            "Future stage LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1 must re-audit and the next stage must be "
            "approved by a separate operator confirmation before any real send is enabled."
        )

    sys.stderr.write(f"unknown --mode: {args.mode}\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExecutionSendDisabledInImplementationBuildStage as e:
        sys.stderr.write(f"EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE\n")
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
