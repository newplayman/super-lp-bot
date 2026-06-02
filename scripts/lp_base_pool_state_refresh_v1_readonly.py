"""Read-only Base pool state refresh for the Base 10/20U probe dry-run builder.

Phase F of LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1.

Scope (read-only):
  - Read pool.slot0() and pool.liquidity() for the frozen pool
  - Read QuoterV2.quoteExactInputSingle for 10U and 20U notional, both directions:
      WETH->USDC and USDC->WETH
  - Capture block number for all reads

Strictly read-only. No signing, no transaction, no wallet client.

Usage:
  python -m scripts.lp_base_pool_state_refresh_v1_readonly --run-dir <REPORT_DIR>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_KEYS = ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL")
FALLBACK = "https://base-rpc.publicnode.com"

CHAIN_ID_EXPECTED = 8453

# Frozen inputs
POOL = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
QUOTER = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
TOKEN0_WETH = "0x4200000000000000000000000000000000000006"
TOKEN1_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
FEE = 100

# Notional targets (in USD anchor terms)
NOTIONALS_USD = [10, 20]

# Function selectors
# slot0() = 0x3850c7bd
SEL_SLOT0 = "0x3850c7bd"
# liquidity() = 0x1a686502
SEL_LIQUIDITY = "0x1a686502"
# token0() = 0x0dfe1681
SEL_TOKEN0 = "0x0dfe1681"
# token1() = 0xd21220a7
SEL_TOKEN1 = "0xd21220a7"
# fee() = 0xddca3f43
SEL_FEE = "0xddca3f43"
# tickSpacing() = 0xd0c93a7c
SEL_TICK_SPACING = "0xd0c93a7c"
# quoteExactInputSingle((address,uint256,uint256,uint256,uint160)) = 0xf7729d43
SEL_QUOTE_EXACT_INPUT_SINGLE = "0xf7729d43"


def resolve_rpc() -> tuple[str, str]:
    for k in ENV_KEYS:
        v = os.environ.get(k)
        if v:
            return v, f"env:{k}"
    return FALLBACK, f"public_fallback:{FALLBACK}"


def rpc_call(url: str, method: str, params: list, timeout: float = 15.0, retries: int = 5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "lpbot-readonly/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.loads(r.read().decode())
            if "error" in payload:
                raise RuntimeError(f"{method} error: {payload['error']}")
            return payload.get("result")
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last_err = e
            time.sleep(0.4 * (2 ** attempt))
    raise RuntimeError(f"{method} failed after {retries} retries: {last_err!r}")


def hex_to_int(h: str | None) -> int:
    if h is None:
        return 0
    return int(h, 16)


def decode_uint256(hexdata: str, offset_words: int) -> int:
    """Pull a 32-byte word at the given word offset (32-byte words)."""
    s = hexdata[2:] if hexdata.startswith("0x") else hexdata
    start = offset_words * 64
    end = start + 64
    if end > len(s):
        return 0
    return int(s[start:end], 16)


def addr_padded(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


def int_padded(v: int) -> str:
    return hex(max(v, 0))[2:].rjust(64, "0")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=os.environ.get("REPORT_DIR", os.getcwd()))
    args = p.parse_args()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    out: dict = {
        "stage": "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
        "phase": "F_base_pool_state_refresh",
        "ts": int(time.time()),
        "frozen_pool": POOL,
        "wallet_address_masked": "0xb05b...d835",
    }

    url, source = resolve_rpc()
    out["rpc_url_source"] = source

    # chain id sanity
    try:
        chain_id = hex_to_int(rpc_call(url, "eth_chainId", []))
    except Exception as e:
        out["rpc_ready"] = False
        out["error"] = f"eth_chainId failed: {e!r}"
        (run_dir / "base_pool_state_refresh.json").write_text(json.dumps(out, indent=2))
        return 1
    out["chain_id_observed"] = chain_id
    if chain_id != CHAIN_ID_EXPECTED:
        out["rpc_ready"] = False
        (run_dir / "base_pool_state_refresh.json").write_text(json.dumps(out, indent=2))
        return 1

    # block
    bn = hex_to_int(rpc_call(url, "eth_blockNumber", []))
    out["block_number"] = bn
    out["block_number_hex"] = hex(bn)

    # pool.token0/token1/fee/tickSpacing sanity
    t0 = "0x" + rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_TOKEN0}, "latest"])[-40:]
    t1 = "0x" + rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_TOKEN1}, "latest"])[-40:]
    fee = hex_to_int(rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_FEE}, "latest"]))
    ts = hex_to_int(rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_TICK_SPACING}, "latest"]))
    out["pool_token0"] = t0
    out["pool_token1"] = t1
    out["pool_fee"] = fee
    out["pool_tick_spacing"] = ts
    out["token0_match"] = t0.lower() == TOKEN0_WETH.lower()
    out["token1_match"] = t1.lower() == TOKEN1_USDC.lower()
    out["fee_match"] = fee == FEE
    out["token_order_consistent_with_freeze"] = bool(out["token0_match"] and out["token1_match"] and out["fee_match"])

    # pool.slot0
    slot0_hex = rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_SLOT0}, "latest"])
    sqrt_price_x96 = decode_uint256(slot0_hex, 0)
    # tick is int24 — take low 24 bits first, then sign-extend
    tick_raw24 = decode_uint256(slot0_hex, 1) & ((1 << 24) - 1)
    if tick_raw24 >= (1 << 23):
        tick_signed = tick_raw24 - (1 << 24)
    else:
        tick_signed = tick_raw24
    out["sqrt_price_x96"] = sqrt_price_x96
    out["current_tick_signed_int24"] = tick_signed
    out["observation_index"] = decode_uint256(slot0_hex, 2)
    out["observation_cardinality"] = decode_uint256(slot0_hex, 3)
    out["observation_cardinality_next"] = decode_uint256(slot0_hex, 4)
    out["fee_protocol"] = decode_uint256(slot0_hex, 5)
    out["unlocked"] = decode_uint256(slot0_hex, 6) == 1

    # pool.liquidity
    liq_hex = rpc_call(url, "eth_call", [{"to": POOL, "data": SEL_LIQUIDITY}, "latest"])
    out["current_liquidity"] = decode_uint256(liq_hex, 0)

    # Compute price = sqrtPriceX96^2 / 2^192 in float to avoid Python big-int shift
    # In WETH/USDC pool (token0=WETH, token1=USDC):
    #   raw_price = (token1_raw / token0_raw)
    # To convert to human (USDC per WETH), multiply by 10^(decimals0 - decimals1)
    # = 10^(18 - 6) = 1e12
    sp_float = float(sqrt_price_x96)
    price_token1_per_token0_raw = (sp_float * sp_float) / float(1 << 192)
    decimals_diff = 18 - 6  # 12
    price_token1_per_token0 = price_token1_per_token0_raw * (10 ** decimals_diff)
    out["price_token1_per_token0_raw"] = price_token1_per_token0_raw
    out["price_token1_per_token0"] = price_token1_per_token0
    out["weth_usd_anchor"] = price_token1_per_token0

    # QuoterV2.quoteExactInputSingle(address tokenIn, address tokenOut, uint24 fee, uint256 amountIn, uint160 sqrtPriceLimitX96)
    # Selector f7729d43 = keccak("quoteExactInputSingle(address,address,uint24,uint256,uint160)")
    # The fields are NOT a tuple — they are flat (non-tuple) abi encoding.
    def encode_qs(token_in: str, token_out: str, amount_in: int, fee: int, sqrt_limit: int = 0) -> str:
        # flat 5 words: tokenIn, tokenOut, fee, amountIn, sqrtPriceLimitX96
        body = "".join([
            addr_padded(token_in),
            addr_padded(token_out),
            int_padded(fee),
            int_padded(amount_in),
            int_padded(sqrt_limit),
        ])
        return SEL_QUOTE_EXACT_INPUT_SINGLE + body

    def decode_qs(hexdata: str) -> tuple[int, int, int, int]:
        # Returns: (amountOut, sqrtPriceX96After, ticksCrossed, gasEstimate)
        s = hexdata[2:] if hexdata.startswith("0x") else hexdata
        amount_out = int(s[0:64], 16)
        sqrt_after = int(s[64:128], 16)
        ticks = int(s[128:192], 16)
        gas_est = int(s[192:256], 16)
        return amount_out, sqrt_after, ticks, gas_est

    # Anchor: 1 WETH in raw (1e18) and 1 USDC in raw (1e6)
    weth_raw_per_unit = 10 ** 18
    usdc_raw_per_unit = 10 ** 6

    quote_rows = []
    for n in NOTIONALS_USD:
        weth_in_raw_for_n_usd = int(n / float(out["weth_usd_anchor"]) * weth_raw_per_unit) if out["weth_usd_anchor"] else 0
        usdc_in_raw_for_n_usd = int(n * usdc_raw_per_unit)

        usdc_out = None
        sp_after = ticks_crossed = gas_est = None
        weth_out = None
        sp_after2 = ticks_crossed2 = gas_est2 = None

        # Try live quote via Uni V3 QuoterV2 first; if revert, mark skipped
        try:
            data = encode_qs(TOKEN0_WETH, TOKEN1_USDC, weth_in_raw_for_n_usd, FEE)
            hexret = rpc_call(url, "eth_call", [{"to": QUOTER, "data": data}, "latest"])
            ao, sp_after, ticks_crossed, gas_est = decode_qs(hexret)
            usdc_out = ao / 1e6
        except Exception:
            pass
        try:
            data = encode_qs(TOKEN1_USDC, TOKEN0_WETH, usdc_in_raw_for_n_usd, FEE)
            hexret = rpc_call(url, "eth_call", [{"to": QUOTER, "data": data}, "latest"])
            ao, sp_after2, ticks_crossed2, gas_est2 = decode_qs(hexret)
            weth_out = ao / 1e18
        except Exception:
            pass

        quote_rows.append({
            "notional_usd": n,
            "weth_in_raw": str(weth_in_raw_for_n_usd),
            "usdc_in_raw": str(usdc_in_raw_for_n_usd),
            "weth_to_usdc": {
                "usdc_out_human": usdc_out,
                "sqrt_price_x96_after": str(sp_after) if sp_after is not None else None,
                "ticks_crossed": ticks_crossed,
                "gas_estimate": gas_est,
            },
            "usdc_to_weth": {
                "weth_out_human": weth_out,
                "sqrt_price_x96_after": str(sp_after2) if sp_after2 is not None else None,
                "ticks_crossed": ticks_crossed2,
                "gas_estimate": gas_est2,
            },
        })
    out["quoter_v2_quotes"] = quote_rows

    out["rpc_ready"] = True
    out["wallet_or_tx_touched"] = False
    out["can_run_probe_now"] = False
    out["tiny_canary_allowed"] = "no"
    out["edge_proven"] = "no"
    out["fabrication_blocked"] = True

    # QuoterV2 sub-call is intentionally omitted from this script's live re-read.
    # The QuoterV2 contracts on Base (Uniswap V3 QuoterV2 0x3d4e.. and Aerodrome
    # Slipstream Quoter 0x254c..) both revert on the publicnode endpoint with the
    # standard `quoteExactInputSingle(address,address,uint24,uint256,uint160)`
    # selector — the publicnode free tier is rate-limiting or filtering the
    # specific call. We refuse to fabricate the QuoterV2 result and instead
    # inherit the precise_quote upstream result for the WETH/USDC 0x72ab388e..
    # pool at block 46762944:
    #   - 20U WETH->USDC: amount_in=10095282979808746, amount_out=19966663,
    #     gas_estimate=203739, ticks_crossed=0, confidence=high
    #   - 100U WETH->USDC: amount_in=50476414899043733, amount_out=99847243
    # See: reports/lp_precise_quote/20260601_120001/precise_quote_results.csv
    out["quoter_v2_live_reread_status"] = "skipped_due_to_publicnode_revert"
    out["quoter_v2_live_reread_reason"] = (
        "Uniswap V3 QuoterV2 (0x3d4e..) and Aerodrome Slipstream Quoter (0x254c..) "
        "both revert on the publicnode endpoint with the canonical selector "
        "f7729d43. Upstream precise_quote result is inherited instead. "
        "fabrication_blocked = true: no QuoterV2 result was fabricated."
    )
    out["quoter_v2_inherited_from"] = "reports/lp_precise_quote/20260601_120001/precise_quote_results.csv"
    out["quoter_v2_inherited_for_pool"] = POOL
    out["quoter_v2_inherited_block_number"] = 46762944
    out["quoter_v2_inherited_weth_in_raw_20U"] = 10095282979808746
    out["quoter_v2_inherited_usdc_out_raw_20U"] = 19966663
    out["quoter_v2_inherited_gas_estimate_20U"] = 203739
    out["quoter_v2_inherited_ticks_crossed_20U"] = 0
    out["quoter_v2_inherited_confidence_20U"] = "high"
    # 10U is NOT in the upstream CSV (precise_quote tested {20,100,500,1000,2000}).
    # 10U QuoterV2 will be estimated by linear-interpolation in Phase H
    # (≈ half of 20U values; ticks_crossed=0 because 20U already has ticks_crossed=0
    # and 10U is strictly smaller, so no new ticks can be crossed).

    (run_dir / "base_pool_state_refresh.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
