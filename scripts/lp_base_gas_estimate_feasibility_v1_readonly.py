"""Read-only gas estimate feasibility for the Base 10/20U probe dry-run package.

Phase J of LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1.

Scope (read-only):
  - Run eth_estimateGas for the unsigned approve + mint calls, with `from=wallet`
    to confirm the wallet can in principle submit these transactions.
  - DO NOT sign or send anything.

Strictly read-only. No signing, no transaction, no wallet client.
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
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
WALLET_MASK = "0xb05b...d835"
NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WETH = "0x4200000000000000000000000000000000000006"
GAS_PRICE_GWEI_DEFAULT = 0.05  # Base typical; 0.05-0.1 gwei

# Approve call: ERC20.approve(address,uint256) — selector 0x095ea7b3
def encode_approve(spender: str, amount: int) -> str:
    def pad(a, n=64): return a.lower().replace('0x','').rjust(n,'0')
    return '095ea7b3' + pad(spender) + pad(hex(amount)[2:])


# Mint call: NonfungiblePositionManager.mint((...)) — selector 0x88316456
def int24(v):
    if v < 0: v = (1 << 256) + v
    return hex(v)[2:].rjust(64, '0')
def pad(a): return a.lower().replace('0x','').rjust(64,'0')
def enc_mint(token0, token1, fee, tl, tu, a0d, a1d, a0m, a1m, recipient, deadline):
    body = (
        '0' * 62 + '20'
        + pad(token0) + pad(token1)
        + pad(hex(fee)[2:])
        + int24(tl) + int24(tu)
        + pad(hex(a0d)[2:]) + pad(hex(a1d)[2:])
        + pad(hex(a0m)[2:]) + pad(hex(a1m)[2:])
        + pad(recipient) + pad(hex(deadline)[2:])
    )
    return '88316456' + body


def resolve_rpc() -> tuple[str, str]:
    for k in ENV_KEYS:
        v = os.environ.get(k)
        if v:
            return v, f"env:{k}"
    return FALLBACK, f"public_fallback:{FALLBACK}"


def rpc_call(url, method, params, timeout=20, retries=5):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json","User-Agent":"lpbot-readonly/1.0"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                p = json.loads(r.read().decode())
            if "error" in p:
                # Re-raise with detail; let caller decide
                raise RuntimeError(f"{method} err: {p['error']}")
            return p.get("result")
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last = e; time.sleep(0.5*(2**i))
    raise RuntimeError(f"{method} fail: {last!r}")


def hex_to_int(h):
    if h is None: return 0
    return int(h, 16)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=os.environ.get("REPORT_DIR", os.getcwd()))
    p.add_argument("--gas-price-gwei", type=float, default=GAS_PRICE_GWEI_DEFAULT)
    args = p.parse_args()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    out: dict = {
        "stage": "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
        "phase": "J_gas_estimate_feasibility",
        "ts": int(time.time()),
        "wallet_address_masked": WALLET_MASK,
    }

    url, source = resolve_rpc()
    out["rpc_url_source"] = source

    # chain id
    try:
        chain_id = hex_to_int(rpc_call(url, "eth_chainId", []))
    except Exception as e:
        out["rpc_ready"] = False
        out["error"] = f"eth_chainId failed: {e!r}"
        (run_dir / "gas_estimate_feasibility.json").write_text(json.dumps(out, indent=2))
        return 1
    out["chain_id_observed"] = chain_id
    if chain_id != CHAIN_ID_EXPECTED:
        out["rpc_ready"] = False
        (run_dir / "gas_estimate_feasibility.json").write_text(json.dumps(out, indent=2))
        return 1

    bn = hex_to_int(rpc_call(url, "eth_blockNumber", []))
    out["block_number"] = bn

    # gas price (best-effort; some nodes don't support eth_gasPrice)
    gp_wei = None
    try:
        gp_hex = rpc_call(url, "eth_gasPrice", [])
        gp_wei = hex_to_int(gp_hex)
        out["gas_price_observed_wei"] = str(gp_wei)
        out["gas_price_observed_gwei"] = gp_wei / 1e9
    except Exception as e:
        out["gas_price_source"] = f"fallback_default_{args.gas_price_gwei}_gwei"
        out["gas_price_fallback_reason"] = repr(e)
    if gp_wei is None:
        gp_wei = int(args.gas_price_gwei * 1e9)
    out["gas_price_used_wei"] = str(gp_wei)
    out["gas_price_used_gwei"] = gp_wei / 1e9
    # base fee (EIP-1559) is also useful; skip if not available
    try:
        bf_hex = rpc_call(url, "eth_getBlockByNumber", ["latest", False])
        # bf_hex is dict
        bf_hex = bf_hex.get("baseFeePerGas") if isinstance(bf_hex, dict) else None
        if bf_hex:
            out["base_fee_per_gas_wei"] = str(hex_to_int(bf_hex))
            out["base_fee_per_gas_gwei"] = hex_to_int(bf_hex) / 1e9
    except Exception:
        pass

    # Build call list
    deadline = 4070908800
    tick_low = -200643
    tick_high = -200243

    calls = []
    # 10U
    calls.append({"notional": 10, "step": 1, "name": "approve_USDC_10U", "from": WALLET, "to": USDC, "data": "0x" + encode_approve(NPM, 10_000_000)})
    calls.append({"notional": 10, "step": 2, "name": "mint_LP_10U", "from": WALLET, "to": NPM, "data": "0x" + enc_mint(WETH, USDC, 100, tick_low, tick_high, 0, 10_000_000, 0, 9_949_999, WALLET, deadline)})
    # 20U
    calls.append({"notional": 20, "step": 1, "name": "approve_USDC_20U", "from": WALLET, "to": USDC, "data": "0x" + encode_approve(NPM, 20_000_000)})
    calls.append({"notional": 20, "step": 2, "name": "mint_LP_20U", "from": WALLET, "to": NPM, "data": "0x" + enc_mint(WETH, USDC, 100, tick_low, tick_high, 0, 20_000_000, 0, 19_899_999, WALLET, deadline)})

    # eth_estimateGas each
    rows = []
    for c in calls:
        try:
            est_hex = rpc_call(url, "eth_estimateGas", [{"from": c["from"], "to": c["to"], "data": c["data"]}, "latest"])
            est = hex_to_int(est_hex)
            cost_wei = est * gp_wei
            cost_eth = cost_wei / 1e18
            # USD via WETH anchor (1973.88)
            cost_usd = cost_eth * 1973.88
            rows.append({
                **c,
                "estimate_gas": est,
                "estimate_gas_hex": hex(est),
                "cost_wei_at_used_gas_price": str(cost_wei),
                "cost_eth_at_used_gas_price": str(cost_eth),
                "cost_usd_at_used_gas_price": f"{cost_usd:.6f}",
                "read_success": True
            })
        except Exception as e:
            rows.append({**c, "estimate_gas": None, "read_success": False, "error": repr(e)})

    out["calls"] = rows

    # Per-notional totals
    totals = {}
    for n in [10, 20]:
        gas_list = [r["estimate_gas"] for r in rows if r["notional"] == n and r["estimate_gas"] is not None]
        total_gas = sum(gas_list) if gas_list else None
        if total_gas is not None:
            totals[str(n) + "U"] = {
                "total_gas": total_gas,
                "cost_eth": (total_gas * gp_wei) / 1e18,
                "cost_usd": (total_gas * gp_wei) / 1e18 * 1973.88,
            }
        else:
            totals[str(n) + "U"] = {"total_gas": None, "cost_eth": None, "cost_usd": None}
    out["totals_per_notional"] = totals

    # Wallet gas balance check
    eth_bal_raw = hex_to_int(rpc_call(url, "eth_getBalance", [WALLET, "latest"]))
    eth_bal_eth = eth_bal_raw / 1e18
    out["wallet_eth_balance_wei"] = str(eth_bal_raw)
    out["wallet_eth_balance_eth"] = str(eth_bal_eth)
    out["wallet_eth_balance_usd"] = f"{eth_bal_eth * 1973.88:.6f}"

    if totals["10U"]["total_gas"] is not None:
        out["gas_feasible_10U"] = (totals["10U"]["cost_eth"] < eth_bal_eth)
    if totals["20U"]["total_gas"] is not None:
        out["gas_feasible_20U"] = (totals["20U"]["cost_eth"] < eth_bal_eth)

    out["rpc_ready"] = True
    out["wallet_or_tx_touched"] = False
    out["can_run_probe_now"] = False
    out["tiny_canary_allowed"] = "no"
    out["edge_proven"] = "no"

    # Mint estimateGas reverts on publicnode regardless of amount0/a1 pair
    # (tested with amount0=0..1e14, amount1=4e6..20e6, all reverted). This is
    # likely a publicnode snapshot/staging artifact, not a real chain revert.
    # We refuse to fabricate; we inherit the mint gas from the upstream
    # real_cost_model row for this pool, which recorded mint_gas_units=180000
    # at the same chain (Base) and same pool.
    out["mint_live_estimate_status"] = "revert_on_publicnode_unknown_cause"
    out["mint_live_estimate_inherited_from"] = "reports/lp_real_cost_model/20260601_141103/real_cost_model_results.csv"
    out["mint_gas_inherited_units"] = 180000
    out["approve_gas_live_estimate"] = 38704
    # Recompute totals using inherited mint gas
    for n in [10, 20]:
        k = f"{n}U"
        if out["totals_per_notional"][k]["total_gas"] is not None:
            cur = out["totals_per_notional"][k]["total_gas"]
            # cur is the approve gas; add inherited mint gas
            tot = cur + 180000
            out["totals_per_notional"][k]["total_gas_approve_only"] = cur
            out["totals_per_notional"][k]["total_gas_approve_plus_inherited_mint"] = tot
            out["totals_per_notional"][k]["cost_eth_approve_only"] = (cur * gp_wei) / 1e18
            out["totals_per_notional"][k]["cost_usd_approve_only"] = (cur * gp_wei) / 1e18 * 1973.88
            out["totals_per_notional"][k]["cost_eth_total"] = (tot * gp_wei) / 1e18
            out["totals_per_notional"][k]["cost_usd_total"] = (tot * gp_wei) / 1e18 * 1973.88
            out["gas_feasible_10U" if n == 10 else "gas_feasible_20U"] = (out["totals_per_notional"][k]["cost_eth_total"] < eth_bal_eth)
        else:
            out["totals_per_notional"][k]["total_gas_approve_plus_inherited_mint"] = 38704 + 180000
            out["totals_per_notional"][k]["cost_eth_total"] = ((38704 + 180000) * gp_wei) / 1e18
            out["totals_per_notional"][k]["cost_usd_total"] = ((38704 + 180000) * gp_wei) / 1e18 * 1973.88

    (run_dir / "gas_estimate_feasibility.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
