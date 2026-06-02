"""Read-only Base wallet balance + allowance refresh for the Base 10/20U probe dry-run builder.

Phase E of LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1.

Scope (read-only):
  - Re-read ERC20.balanceOf and ERC20.allowance for the bound wallet, against the
    frozen Base pool's token0 (WETH), token1 (USDC), and the canonical Base NPM.
  - Re-read eth_getBalance for native ETH (gas).
  - Capture block number and timestamp; refuse to fabricate values on RPC failure.

Strictly read-only. No signing, no transaction, no wallet client.

Usage:
  python -m scripts.lp_base_wallet_balance_allowance_refresh_v1_readonly --run-dir <REPORT_DIR>
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

CHAIN_ID_EXPECTED = 8453

ENV_KEYS = ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL")
FALLBACK = "https://base-rpc.publicnode.com"

# Frozen inputs
WALLET = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
WALLET_MASK = "0xb05b...d835"
POOL = "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
TOKEN0_WETH = "0x4200000000000000000000000000000000000006"
TOKEN1_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"

# Tokens & spenders to check
TOKENS = [
    {"symbol": "WETH", "address": TOKEN0_WETH, "decimals": 18, "spenders": {"uni_v3_npm_base": NPM}},
    {"symbol": "USDC", "address": TOKEN1_USDC, "decimals": 6,  "spenders": {"uni_v3_npm_base": NPM}},
]

# Function selectors
# balanceOf(address) = 0x70a08231
SEL_BALANCE_OF = "0x70a08231"
# allowance(address,address) = 0xdd62ed3e
SEL_ALLOWANCE = "0xdd62ed3e"


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


def addr_padded(a: str) -> str:
    a = a.lower().replace("0x", "")
    return a.rjust(64, "0")


def encode_balance_of(owner: str) -> str:
    return SEL_BALANCE_OF + addr_padded(owner)


def encode_allowance(owner: str, spender: str) -> str:
    return SEL_ALLOWANCE + addr_padded(owner) + addr_padded(spender)


def humanize(raw: int, decimals: int) -> str:
    if decimals == 0:
        return str(raw)
    return f"{raw / (10 ** decimals):.18f}".rstrip("0").rstrip(".") or "0"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=os.environ.get("REPORT_DIR", os.getcwd()))
    args = p.parse_args()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    out: dict = {
        "stage": "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
        "phase": "E_base_wallet_balance_allowance_refresh",
        "ts": int(time.time()),
        "wallet_address_masked": WALLET_MASK,
        "frozen_pool": POOL,
    }

    url, source = resolve_rpc()
    out["rpc_url_source"] = source

    # chain id
    try:
        chain_id = hex_to_int(rpc_call(url, "eth_chainId", []))
    except Exception as e:
        out["rpc_ready"] = False
        out["error"] = f"eth_chainId failed: {e!r}"
        (run_dir / "base_wallet_balance_allowance_refresh.json").write_text(json.dumps(out, indent=2))
        return 1
    out["chain_id_observed"] = chain_id
    if chain_id != CHAIN_ID_EXPECTED:
        out["rpc_ready"] = False
        out["error"] = f"chain_id mismatch: {chain_id} != {CHAIN_ID_EXPECTED}"
        (run_dir / "base_wallet_balance_allowance_refresh.json").write_text(json.dumps(out, indent=2))
        return 1

    # block
    bn = hex_to_int(rpc_call(url, "eth_blockNumber", []))
    out["block_number"] = bn
    out["block_number_hex"] = hex(bn)
    out["block_tag"] = "latest"

    # eth_getBalance (native ETH)
    eth_balance_raw = hex_to_int(rpc_call(url, "eth_getBalance", [WALLET, "latest"]))
    eth_balance_human = f"{eth_balance_raw / 1e18:.18f}"
    out["eth_native"] = {
        "symbol": "ETH",
        "raw": str(eth_balance_raw),
        "human": eth_balance_human,
        "read_success": True,
    }

    # For each token: balanceOf + allowance to each configured spender
    rows = []
    for t in TOKENS:
        bal_hex = rpc_call(url, "eth_call", [{"to": t["address"], "data": encode_balance_of(WALLET)}, "latest"])
        bal_raw = hex_to_int(bal_hex)
        row = {
            "symbol": t["symbol"],
            "address": t["address"],
            "decimals": t["decimals"],
            "balance_raw": str(bal_raw),
            "balance_human": humanize(bal_raw, t["decimals"]),
            "read_success": True,
        }
        # allowances
        allow = {}
        for sname, saddr in t["spenders"].items():
            al_hex = rpc_call(url, "eth_call", [{"to": t["address"], "data": encode_allowance(WALLET, saddr)}, "latest"])
            al_raw = hex_to_int(al_hex)
            allow[sname] = {
                "spender_address": saddr,
                "raw": str(al_raw),
                "human": humanize(al_raw, t["decimals"]),
                "read_success": True,
            }
        row["allowances"] = allow
        rows.append(row)
    out["token_rows"] = rows

    # Aggregate USD proxy (no price anchor onchain in this phase; we will inherit
    # anchors from prior stage, but to be safe we only emit raw balances here).
    # The Phase H amount calc uses slot0-derived price (re-read in Phase F).

    # Gate: do not fabricate. The downstream phases will compute USD via Phase F.
    out["fabrication_blocked"] = True
    out["rpc_ready"] = True
    out["wallet_or_tx_touched"] = False
    out["can_run_probe_now"] = False
    out["tiny_canary_allowed"] = "no"
    out["edge_proven"] = "no"

    (run_dir / "base_wallet_balance_allowance_refresh.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
