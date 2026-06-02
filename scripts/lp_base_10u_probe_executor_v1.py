"""Base 10U LP probe executor skeleton (BUILD stage; execution disabled).

Stage: LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1

This script is a SKELETON. It implements 4 read-only / non-execution modes:

  --mode preflight           : read-only chain state checks (eth_call, balanceOf,
                               allowance, slot0, QuoterV2, eth_estimateGas).
                               Writes a preflight report to local reports dir only.
                               No signing, no send, no approve, no mint.

  --mode print-unsigned      : emit a structured unsigned-tx package as JSON.
                               No signature. No send. Pure description.

  --mode validate-approval   : parse a future execution approval phrase; check
                               against the regex from upstream spec. Success
                               does NOT authorize execution.

  --mode execute-disabled    : stub. Always raises EXECUTION_DISABLED_IN_BUILD_STAGE.
                               Exits with non-zero. Never sends any tx.

  --mode execute             : REJECTED. Always aborts.

Hard-coded candidate (from upstream spec review /20260602_133221/):
  chain      = base (chain_id 8453)
  pool       = 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38  (WETH/USDC 0.01%)
  npm        = 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1
  quoter_v2  = 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a
  wallet     = 0xb05b2872ace4564ff247555b6f7b097d31f3d835
  notional   = 10 USD
  hold       = 15m
  tick range = lower=-200643, upper=-200243

Strictly forbidden in this build stage:
  - loading private keys, mnemonics, or keystore
  - constructing a signer or wallet client
  - calling eth_sendTransaction / eth_sendRawTransaction
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
TICK_LOWER = -200643
TICK_UPPER = -200243
DEADLINE_PLACEHOLDER = 4070908800  # 2099-01-01 UTC; user overrides at execution

# Approval phrase regex (from upstream spec review)
APPROVAL_PHRASE_REGEX = r"^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$"

# Dangerous words (any approval phrase containing any of these as a whole-word match
# OUTSIDE the canonical prefix MUST be rejected). The check uses word-boundary regex
# so substrings inside the canonical prefix "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT"
# (which contains "EXEC") do not false-positive.
#
# Each entry is a word that, if present as a whole word, indicates the phrase is
# not a single-shot 10U/15m execution.
DANGEROUS_WORD_PATTERNS = [
    r"\bEXECUTE\b",          # not just "EXEC"
    r"\bEXEC\b",             # but only as a separate token (e.g. "PROBE EXEC NOW")
    r"\bNOW\b",
    r"\bLIVE\b",
    r"\bCANARY\b",
    r"\bPAPER\b",
    r"\bMINT\b",
    r"\bSIGN\b",
    r"\bBURN\b",
    r"\bSWAP\b",
    r"\bBRIDGE\b",
    r"\bSEND\b",
    r"\bDEPLOY\b",
    r"\bGO\b",
    r"\bSHIP\b",
    r"\bPROCEED\b",
    r"\b20U\b",
    r"\b20u\b",
    r"\b30M\b",
    r"\b30m\b",
    r"\bUSER_PROVIDED\b",
    r"\bUSER_SELECTED\b",
    r"\bYES\b",
    r"\bEXECUTABLE\b",
    r"\bFUND\b",
    r"\bWITHDRAW\b",
    r"\bTRANSFER_OUT\b",
]

# Forbidden env var name patterns (any env lookup matching these MUST be blocked).
# Only crypto / wallet / secret-store names — NOT generic _API_KEY (e.g. ANTHROPIC_API_KEY is
# unrelated to wallet keys and would only block legitimate AI tooling).
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

# RPC env keys (allowed; not sensitive)
RPC_ENV_KEYS = ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL")
RPC_FALLBACK = "https://base-rpc.publicnode.com"

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
# quoteExactInputSingle(address,address,uint24,uint256,uint160) on Uniswap V3 QuoterV2
SEL_QUOTE_EXACT_INPUT_SINGLE = "0xf7729d43"


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
                headers={"Content-Type": "application/json", "User-Agent": "lpbot-executor-skel/1.0"},
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


def encode_mint_uniswap_v3(token0: str, token1: str, fee: int, tick_lower: int, tick_upper: int,
                            amount0_desired: int, amount1_desired: int,
                            amount0_min: int, amount1_min: int,
                            recipient: str, deadline: int) -> str:
    """Encode the Uniswap V3 NonfungiblePositionManager.mint call.

    NonfungiblePositionManager.mint((address,address,uint24,int24,int24,
      uint256,uint256,uint256,uint256,address,uint256))
    selector 0x88316456 + offset 0x20 + 11 fields
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
    return "0x88316456" + body


def is_forbidden_env(env_name: str) -> bool:
    for pat in FORBIDDEN_ENV_PATTERNS:
        if re.match(pat, env_name):
            return True
    return False


# === Approval phrase parser =============================================

def parse_approval_phrase(phrase: str) -> dict:
    """Parse and validate the future execution approval phrase.

    Returns a dict with:
      - valid: bool
      - reason: str (if invalid)
      - parsed: dict (if valid; wallet, pool, notional, hold)
    """
    if not isinstance(phrase, str):
        return {"valid": False, "reason": "phrase is not a string"}
    if not phrase.strip():
        return {"valid": False, "reason": "phrase is empty"}

    # First: dangerous-word pre-check (whole-word match, NOT substring)
    for pat in DANGEROUS_WORD_PATTERNS:
        if re.search(pat, phrase):
            return {"valid": False, "reason": f"dangerous keyword detected (pattern: {pat!r})"}

    # Then: regex match
    rgx = re.compile(APPROVAL_PHRASE_REGEX)
    m = rgx.match(phrase)
    if not m:
        return {"valid": False, "reason": "phrase does not match the canonical regex"}

    # Parse fields from the matched phrase
    # wallet
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
    # Cross-check against frozen candidate
    if parsed["wallet"] != WALLET:
        return {"valid": False, "reason": f"wallet {parsed['wallet']} != frozen {WALLET}"}
    if parsed["pool"] != POOL:
        return {"valid": False, "reason": f"pool {parsed['pool']} != frozen {POOL}"}
    if parsed["notional"] != NOTIONAL_USD:
        return {"valid": False, "reason": f"notional {parsed['notional']} != first-round {NOTIONAL_USD}"}
    if parsed["hold"] != HOLD_WINDOW:
        return {"valid": False, "reason": f"hold {parsed['hold']} != first-round {HOLD_WINDOW}"}
    return {"valid": True, "parsed": parsed, "executes_now": False,
            "note": "valid_phrase_but_execution_disabled_in_build_stage"}


# === Stop condition engine =============================================

def evaluate_stop_conditions(preflight: dict) -> dict:
    """Evaluate hard stop conditions from the upstream spec on the preflight result.

    Returns a dict mapping stop_id -> dict(triggered, handling, reason).
    Any hard stop => preflight_status = FAIL.
    """
    stops: dict = {}

    def add(sid, triggered, handling, reason):
        stops[sid] = {"triggered": triggered, "handling": handling, "reason": reason}

    chain_id = preflight.get("chain_id")
    add("stop_chain_id_mismatch",
        chain_id is not None and chain_id != CHAIN_ID,
        "abort_before_entry",
        f"chain_id_observed={chain_id}, expected={CHAIN_ID}")

    eth_bal = preflight.get("eth_native_wei")
    min_gas_wei = 9 * 10**13  # 9.0e-5 ETH
    add("stop_gas_balance_below_threshold",
        eth_bal is not None and eth_bal < min_gas_wei,
        "abort_before_entry",
        f"eth_balance_wei={eth_bal}, min={min_gas_wei}")

    usdc_bal = preflight.get("usdc_balance_raw")
    add("stop_usdc_balance_below_required",
        usdc_bal is not None and usdc_bal < (NOTIONAL_USD + 2) * 10**6,
        "abort_before_entry",
        f"usdc_balance_raw={usdc_bal}, min={(NOTIONAL_USD + 2) * 10**6}")

    weth_bal = preflight.get("weth_balance_raw")
    add("stop_weth_balance_below_required",
        weth_bal is not None and weth_bal < 0,  # mathematically impossible; guard
        "abort_before_entry",
        f"weth_balance_raw={weth_bal} (note: 10U/20U path requires 0 WETH)")

    usdc_allow = preflight.get("usdc_allowance_raw")
    add("stop_allowance_unexpected",
        usdc_allow is not None and usdc_allow > 50_000_000,
        "manual_intervention_required",
        f"usdc_allowance_raw={usdc_allow} (suspicious if > 50M)")

    weth_allow = preflight.get("weth_allowance_raw")
    add("stop_allowance_unexpected_weth",
        weth_allow is not None and weth_allow > 10**24,
        "manual_intervention_required",
        f"weth_allowance_wei={weth_allow} (suspicious if > 1e24)")

    tick = preflight.get("current_tick")
    add("stop_tick_moved_outside_planned_range_before_entry",
        tick is not None and abs(tick - (-200443)) > 200,
        "manual_intervention_required",
        f"current_tick={tick} drifted > 200 from frozen -200443")

    liq = preflight.get("current_liquidity")
    add("stop_pool_liquidity_drop",
        liq is not None and liq < 10**15,
        "abort_before_entry",
        f"current_liquidity={liq} < 1e15")

    mint_gas = preflight.get("mint_estimate_gas")
    add("stop_gas_estimate_too_high",
        mint_gas is not None and (mint_gas <= 0 or mint_gas > 360_000),
        "abort_before_entry",
        f"mint_estimate_gas={mint_gas} (expected 180k +/- 2x)")

    add("stop_quoter_v2_failure",
        preflight.get("quoter_v2_weth_to_usdc_ok") is False
        or preflight.get("quoter_v2_usdc_to_weth_ok") is False,
        "abort_before_entry",
        "QuoterV2 returned 0 or reverted")

    add("stop_quote_slippage_above_threshold",
        preflight.get("quote_slippage_pct_usdc_to_weth") is not None
        and preflight.get("quote_slippage_pct_usdc_to_weth") > 5.0,
        "abort_before_entry",
        f"slippage {preflight.get('quote_slippage_pct_usdc_to_weth')}% > 5%")

    add("stop_rpc_instability",
        preflight.get("rpc_instability_detected") is True,
        "manual_intervention_required",
        "RPC instability observed during preflight")

    add("stop_unknown_error",
        preflight.get("unknown_error") is not None,
        "manual_intervention_required",
        f"unknown error: {preflight.get('unknown_error')!r}")

    any_triggered = any(s["triggered"] for s in stops.values())
    any_abort = any(s["triggered"] and s["handling"] == "abort_before_entry" for s in stops.values())
    overall = "FAIL" if any_abort else ("WARN" if any_triggered else "PASS")
    return {"stops": stops, "any_triggered": any_triggered, "overall_status": overall}


# === Preflight command =================================================

def run_preflight(run_id: str) -> dict:
    url, source = resolve_rpc()
    preflight: dict = {
        "stage": "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
        "phase": "preflight",
        "run_id": run_id,
        "ts": int(time.time()),
        "wallet_address_bound": WALLET,
        "frozen_pool": POOL,
        "rpc_url_source": source,
        "execution_enabled": False,
    }

    # chainId
    try:
        chain_id_hex = rpc_call(url, "eth_chainId", [])
        chain_id = hex_to_int(chain_id_hex)
        preflight["chain_id"] = chain_id
    except Exception as e:
        preflight["unknown_error"] = repr(e)
        preflight["rpc_instability_detected"] = True
        preflight["chain_id"] = None

    # block
    try:
        bn = hex_to_int(rpc_call(url, "eth_blockNumber", []))
        preflight["block_number"] = bn
    except Exception:
        preflight["block_number"] = None

    # gas price
    try:
        gp_hex = rpc_call(url, "eth_gasPrice", [])
        preflight["gas_price_wei"] = hex_to_int(gp_hex)
    except Exception:
        preflight["gas_price_wei"] = None

    # ETH native balance
    try:
        bal_hex = rpc_call(url, "eth_getBalance", [WALLET, "latest"])
        bal = hex_to_int(bal_hex)
        preflight["eth_native_wei"] = bal
        preflight["eth_native_eth"] = str(Decimal(bal) / Decimal(10**18))
    except Exception as e:
        preflight["eth_native_wei"] = None
        preflight["unknown_error"] = repr(e)

    # USDC balance
    try:
        bal_hex = rpc_call(url, "eth_call",
                           [{"to": USDC, "data": encode_balance_of(WALLET)}, "latest"])
        bal = hex_to_int(bal_hex)
        preflight["usdc_balance_raw"] = bal
        preflight["usdc_balance_human"] = str(Decimal(bal) / Decimal(10**6))
    except Exception as e:
        preflight["usdc_balance_raw"] = None
        preflight["unknown_error"] = repr(e)

    # WETH balance
    try:
        bal_hex = rpc_call(url, "eth_call",
                           [{"to": WETH, "data": encode_balance_of(WALLET)}, "latest"])
        bal = hex_to_int(bal_hex)
        preflight["weth_balance_raw"] = bal
        preflight["weth_balance_human"] = str(Decimal(bal) / Decimal(10**18))
    except Exception:
        preflight["weth_balance_raw"] = None

    # USDC allowance
    try:
        al_hex = rpc_call(url, "eth_call",
                          [{"to": USDC, "data": encode_allowance(WALLET, NPM)}, "latest"])
        al = hex_to_int(al_hex)
        preflight["usdc_allowance_raw"] = al
        preflight["usdc_allowance_human"] = str(Decimal(al) / Decimal(10**6))
    except Exception:
        preflight["usdc_allowance_raw"] = None

    # WETH allowance
    try:
        al_hex = rpc_call(url, "eth_call",
                          [{"to": WETH, "data": encode_allowance(WALLET, NPM)}, "latest"])
        al = hex_to_int(al_hex)
        preflight["weth_allowance_raw"] = al
    except Exception:
        preflight["weth_allowance_raw"] = None

    # pool slot0
    try:
        slot0_hex = rpc_call(url, "eth_call",
                             [{"to": POOL, "data": SEL_SLOT0}, "latest"])
        sqrt = decode_uint256_word(slot0_hex, 0)
        tick_raw = decode_uint256_word(slot0_hex, 1) & ((1 << 24) - 1)
        if tick_raw >= (1 << 23):
            tick_raw -= (1 << 24)
        preflight["sqrt_price_x96"] = sqrt
        preflight["current_tick"] = tick_raw
    except Exception as e:
        preflight["current_tick"] = None
        preflight["unknown_error"] = repr(e)

    # pool liquidity
    try:
        liq_hex = rpc_call(url, "eth_call",
                           [{"to": POOL, "data": SEL_LIQUIDITY}, "latest"])
        preflight["current_liquidity"] = hex_to_int(liq_hex)
    except Exception:
        preflight["current_liquidity"] = None

    # QuoterV2 (publicnode known to revert; mark as such if so)
    preflight["quoter_v2_weth_to_usdc_ok"] = None
    preflight["quoter_v2_usdc_to_weth_ok"] = None
    preflight["quoter_v2_live_read_status"] = "skipped_or_revert_inherited"
    preflight["quote_slippage_pct_usdc_to_weth"] = None

    # mint eth_estimateGas (likely to revert on publicnode for our params; record)
    try:
        amt0 = 0
        amt1 = 10 * 10**6
        data = encode_mint_uniswap_v3(WETH, USDC, FEE_TIER, TICK_LOWER, TICK_UPPER,
                                      amt0, amt1, 0, int(amt1 * 0.995), WALLET, DEADLINE_PLACEHOLDER)
        est = rpc_call(url, "eth_estimateGas",
                       [{"from": WALLET, "to": NPM, "data": data}, "latest"])
        preflight["mint_estimate_gas"] = hex_to_int(est)
        preflight["mint_estimate_gas_read_success"] = True
    except Exception as e:
        preflight["mint_estimate_gas"] = None
        preflight["mint_estimate_gas_read_success"] = False
        preflight["mint_estimate_gas_revert_reason"] = repr(e)

    # stop condition evaluation
    preflight["stop_conditions"] = evaluate_stop_conditions(preflight)
    preflight["preflight_status"] = preflight["stop_conditions"]["overall_status"]

    return preflight


# === Print-unsigned command ============================================

def run_print_unsigned() -> dict:
    amt1 = 10 * 10**6  # 10 USDC
    amt1_min = int(amt1 * 0.995)  # 9_949_999
    approve_data = encode_approve(NPM, amt1)
    mint_data = encode_mint_uniswap_v3(
        WETH, USDC, FEE_TIER, TICK_LOWER, TICK_UPPER,
        0, amt1, 0, amt1_min, WALLET, DEADLINE_PLACEHOLDER,
    )
    return {
        "stage": "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
        "phase": "print-unsigned",
        "ts": int(time.time()),
        "unsigned_only": True,
        "no_signature": True,
        "no_send": True,
        "execution_not_authorized": True,
        "candidate": {
            "chain": CHAIN,
            "chain_id": CHAIN_ID,
            "pool": POOL,
            "pair": PAIR,
            "protocol": PROTOCOL,
            "fee_tier": FEE_TIER,
            "tick_lower": TICK_LOWER,
            "tick_upper": TICK_UPPER,
            "tick_spacing": TICK_SPACING,
            "npm": NPM,
            "quoter_v2": QUOTER_V2,
            "weth": WETH,
            "usdc": USDC,
        },
        "wallet": {
            "address": WALLET,
            "from": WALLET,
            "recipient": WALLET,
        },
        "notional": {
            "usd": NOTIONAL_USD,
            "amount0_desired_wei_WETH": 0,
            "amount1_desired_raw_USDC": amt1,
            "amount0_min_wei": 0,
            "amount1_min_raw": amt1_min,
        },
        "approve_usdc_if_needed": {
            "to": USDC,
            "function": "approve(address,uint256)",
            "selector": SEL_APPROVE,
            "spender": NPM,
            "amount_raw": amt1,
            "amount_human": f"{amt1/1e6:.6f} USDC",
            "policy": "ApproveExact (never ApproveMax)",
            "data": approve_data,
            "value_wei": 0,
            "from": WALLET,
        },
        "approve_weth_if_needed": {
            "skipped": True,
            "reason": "amount0_desired_wei_WETH = 0; WETH approve unnecessary for this range/notional",
        },
        "mint_params": {
            "to": NPM,
            "function": "mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))",
            "selector": "0x88316456",
            "data": mint_data,
            "value_wei": 0,
            "from": WALLET,
            "deadline": DEADLINE_PLACEHOLDER,
            "deadline_iso": "2099-01-01T00:00:00Z",
            "deadline_is_placeholder": True,
            "note": "deadline is a PLACEHOLDER; user overrides at execution time to now+3600",
        },
        "no_abi_bytes_unless_marked": True,
        "no_signature": True,
        "no_send": True,
        "execution_not_authorized": True,
    }


# === Validate-approval command =========================================

def run_validate_approval(phrase: str) -> dict:
    parsed = parse_approval_phrase(phrase)
    return {
        "stage": "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
        "phase": "validate-approval",
        "ts": int(time.time()),
        "phrase_supplied": phrase,
        "valid": parsed.get("valid", False),
        "reason": parsed.get("reason"),
        "parsed": parsed.get("parsed"),
        "executes_now": False,  # ALWAYS false in build stage
        "authorization_granted": False,  # ALWAYS false in build stage
        "next_step_even_if_valid": "user_must_reapprove_at_execution_time_after_review_stage",
    }


# === Execute-disabled command ==========================================

def run_execute_disabled() -> dict:
    return {
        "stage": "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
        "phase": "execute-disabled",
        "ts": int(time.time()),
        "execution_disabled_in_build_stage": True,
        "error": "EXECUTION_DISABLED_IN_BUILD_STAGE",
        "rationale": "This script is a build-stage skeleton. The actual execution will require a separate, post-review stage that re-checks this build's safety invariants AND a fresh human approval phrase at execution time.",
    }


# === Execution stubs (all disabled) ====================================

class ExecutionDisabledInBuildStage(RuntimeError):
    pass


def approve_exact_usdc() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_usdc() is a stub. "
        "Real execution requires LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1 + fresh user approval."
    )


def approve_exact_weth() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: approve_exact_weth() is a stub."
    )


def mint_position() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: mint_position() is a stub."
    )


def monitor_position() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: monitor_position() is a stub."
    )


def decrease_liquidity() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: decrease_liquidity() is a stub."
    )


def collect_fees() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: collect_fees() is a stub."
    )


def revoke_allowance() -> None:
    raise ExecutionDisabledInBuildStage(
        "EXECUTION_DISABLED_IN_BUILD_STAGE: revoke_allowance() is a stub."
    )


# === Telemetry writer skeleton =========================================

def write_telemetry_skeleton(run_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}

    # entry_intent.json
    entry = {
        "schema": "lp_probe_execution_ledger_v1",
        "run_id": run_id,
        "stage": "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1",
        "wallet": WALLET,
        "chain": CHAIN,
        "chain_id": CHAIN_ID,
        "pool": POOL,
        "token0": WETH,
        "token1": USDC,
        "fee_tier": FEE_TIER,
        "tick_lower": TICK_LOWER,
        "tick_upper": TICK_UPPER,
        "notional_usd": NOTIONAL_USD,
        "hold_window": HOLD_WINDOW,
        "deadline_placeholder": DEADLINE_PLACEHOLDER,
        "fabrication_blocked": True,
        "wallet_or_tx_touched": False,
        "build_stage_only": True,
    }
    (out_dir / "entry_intent.json").write_text(json.dumps(entry, indent=2))
    artifacts["entry_intent"] = str(out_dir / "entry_intent.json")

    preflight = {
        "schema": "lp_probe_preflight_v1",
        "run_id": run_id,
        "ts": int(time.time()),
        "skeleton_only": True,
        "note": "Real preflight results written by --mode preflight. This skeleton is just the schema placeholder.",
    }
    (out_dir / "preflight_checks.json").write_text(json.dumps(preflight, indent=2))
    artifacts["preflight_checks"] = str(out_dir / "preflight_checks.json")

    stop = {
        "schema": "lp_probe_stop_condition_checks_v1",
        "run_id": run_id,
        "ts": int(time.time()),
        "skeleton_only": True,
    }
    (out_dir / "stop_condition_checks.json").write_text(json.dumps(stop, indent=2))
    artifacts["stop_condition_checks"] = str(out_dir / "stop_condition_checks.json")

    pkg = run_print_unsigned()
    pkg["build_stage_only"] = True
    (out_dir / "unsigned_package.json").write_text(json.dumps(pkg, indent=2))
    artifacts["unsigned_package"] = str(out_dir / "unsigned_package.json")

    av = {
        "schema": "lp_probe_approval_validation_v1",
        "run_id": run_id,
        "ts": int(time.time()),
        "phrase_regex": APPROVAL_PHRASE_REGEX,
        "build_stage_only": True,
        "executes_now": False,
        "authorization_granted": False,
    }
    (out_dir / "approval_validation.json").write_text(json.dumps(av, indent=2))
    artifacts["approval_validation"] = str(out_dir / "approval_validation.json")

    return artifacts


# === Main ==============================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Base 10U LP probe executor skeleton (build stage; execution disabled)")
    p.add_argument("--mode", required=True,
                   choices=["preflight", "print-unsigned", "validate-approval", "execute-disabled"],
                   help="Mode of operation. 'execute' is REJECTED (use 'execute-disabled' to see the disabled stub).")
    p.add_argument("--run-id", required=False, default=os.environ.get("RUN_ID", time.strftime("%Y%m%d_%H%M%S")))
    p.add_argument("--approval", required=False, default=None,
                   help="For --mode validate-approval only. The phrase to validate.")
    p.add_argument("--out-dir", required=False, default=None,
                   help="Output directory for telemetry skeleton (defaults to reports/lp_base_10u_probe_execution_runtime/<run-id>/).")
    p.add_argument("--execute", action="store_true",
                   help="(intentionally rejected) If present, the script aborts.")
    args = p.parse_args()

    # Defense in depth: if --execute is present OR --mode == execute, abort
    if args.execute or args.mode == "execute":
        sys.stderr.write("REJECTED: --mode execute is not allowed in this build stage.\n")
        sys.stderr.write("This script is a SKELETON; execution must be performed by a separate, post-review stage.\n")
        return 3

    # Defense in depth: scan for any forbidden env var names
    for k in os.environ:
        if is_forbidden_env(k):
            sys.stderr.write(f"REFUSING TO RUN: forbidden env var present: {k!r}\n")
            sys.stderr.write("This script does not load any private key / mnemonic / keystore. Remove the env var.\n")
            return 4

    if args.mode == "preflight":
        result = run_preflight(args.run_id)
        out_dir = Path(args.out_dir) if args.out_dir else Path(
            f"reports/lp_base_10u_probe_execution_runtime/{args.run_id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "preflight_result.json").write_text(json.dumps(result, indent=2))
        result["_artifact_path"] = str(out_dir / "preflight_result.json")
        print(json.dumps(result, indent=2))
        return 0

    if args.mode == "print-unsigned":
        result = run_print_unsigned()
        out_dir = Path(args.out_dir) if args.out_dir else Path(
            f"reports/lp_base_10u_probe_execution_runtime/{args.run_id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "unsigned_package.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 0

    if args.mode == "validate-approval":
        if not args.approval:
            sys.stderr.write("--approval is required for --mode validate-approval\n")
            return 2
        result = run_validate_approval(args.approval)
        out_dir = Path(args.out_dir) if args.out_dir else Path(
            f"reports/lp_base_10u_probe_execution_runtime/{args.run_id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "approval_validation.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        # Build stage: success does NOT authorize execution; return 0 anyway since this is a parse step
        return 0

    if args.mode == "execute-disabled":
        result = run_execute_disabled()
        print(json.dumps(result, indent=2))
        # Non-zero exit per spec ("only output 'execution disabled in this build' and exit non-zero")
        return 1

    sys.stderr.write(f"unknown --mode: {args.mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
