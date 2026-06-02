"""Read-only Base RPC + contract readiness check for the Base 10/20U probe dry-run builder.

Phase D of LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1.

Scope:
  - Resolve Base RPC (env first, publicnode fallback)
  - Verify eth_chainId == 8453
  - Verify getCode() non-empty for: pool, NPM, QuoterV2, WETH, USDC, Factory
  - Capture latest block number

Strictly read-only. No signing, no transaction, no wallet client. No on-disk writes outside
the configured REPORT_DIR.

Usage:
  python -m scripts.lp_base_rpc_and_contract_readiness_v1_readonly --run-dir <REPORT_DIR>

If --run-dir is omitted, it falls back to $REPORT_DIR or cwd.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

CHAIN_ID_EXPECTED = 8453

# Contracts to check via eth_getCode (read-only).
CONTRACTS = {
    "pool_0x72ab388e": "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
    "uni_v3_npm_base": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
    "uni_v3_factory_base": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    "uni_v3_quoter_v2_base": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
    "weth_base": "0x4200000000000000000000000000000000000006",
    "usdc_base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
}

ENV_KEYS = ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL")
FALLBACK = "https://base-rpc.publicnode.com"


def resolve_rpc() -> tuple[str, str]:
    for k in ENV_KEYS:
        v = os.environ.get(k)
        if v:
            return v, f"env:{k}"
    return FALLBACK, f"public_fallback:{FALLBACK}"


def rpc_call(url: str, method: str, params: list, timeout: float = 15.0):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
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


def hex_to_int(h: str | None) -> int:
    if h is None:
        return 0
    return int(h, 16)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", default=os.environ.get("REPORT_DIR", os.getcwd()))
    args = p.parse_args()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    out: dict = {
        "stage": "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
        "phase": "D_base_rpc_and_contract_readiness",
        "ts": int(time.time()),
    }

    url, source = resolve_rpc()
    out["rpc_url_source"] = source
    # Redact the actual URL host for the artifact; keep only a short hash tag
    try:
        from hashlib import sha256
        host_tag = sha256(url.encode()).hexdigest()[:8]
    except Exception:
        host_tag = "unknown"
    out["rpc_url_host_hash"] = host_tag

    # 1) chainId
    try:
        chain_id_hex = rpc_call(url, "eth_chainId", [])
        chain_id = hex_to_int(chain_id_hex)
    except Exception as e:
        out["rpc_ready"] = False
        out["error"] = f"eth_chainId failed: {e!r}"
        out["wallet_or_tx_touched"] = False
        out["can_run_probe_now"] = False
        (run_dir / "base_rpc_contract_readiness.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return 1
    out["chain_id_observed"] = chain_id
    out["chain_id_expected"] = CHAIN_ID_EXPECTED
    out["chain_id_match"] = chain_id == CHAIN_ID_EXPECTED

    # 2) blockNumber
    try:
        bn = hex_to_int(rpc_call(url, "eth_blockNumber", []))
    except Exception as e:
        bn = None
        out["warn"] = (out.get("warn") or []) + [f"eth_blockNumber failed: {e!r}"]
    out["block_number"] = bn

    # 3) getCode for each contract
    contract_rows = []
    all_ok = True
    for label, addr in CONTRACTS.items():
        try:
            code_hex = rpc_call(url, "eth_getCode", [addr, "latest"])
            code_len = (len(code_hex) - 2) // 2 if code_hex and code_hex != "0x" else 0
            ok = code_len > 0
            contract_rows.append({
                "label": label,
                "address": addr,
                "code_length_bytes": code_len,
                "has_code": ok,
                "read_success": True,
            })
            if not ok:
                all_ok = False
        except Exception as e:
            contract_rows.append({
                "label": label,
                "address": addr,
                "code_length_bytes": 0,
                "has_code": False,
                "read_success": False,
                "error": repr(e),
            })
            all_ok = False
    out["contracts"] = contract_rows
    out["all_contracts_have_code"] = all_ok

    # 4) Top-level gates
    out["rpc_ready"] = bool(out["chain_id_match"]) and bool(all_ok)
    out["wallet_or_tx_touched"] = False
    out["can_run_probe_now"] = False
    out["tiny_canary_allowed"] = "no"
    out["edge_proven"] = "no"
    out["fabrication_blocked"] = True

    (run_dir / "base_rpc_contract_readiness.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if out["rpc_ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
