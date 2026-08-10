#!/usr/bin/env python3
"""Base Sepolia smoke preparation: RPC reads and eth_call only, never send."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.base_m1_executor_v1 import (  # noqa: E402
    BASE_SEPOLIA_CHAIN_ID,
    ExecutionNetwork,
    assert_executor_chain_id,
    encode_approve,
)


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ALLOWED_METHODS = frozenset({"eth_chainId", "eth_blockNumber", "eth_getCode", "eth_call"})


def _post(url: str, method: str, params: Sequence[Any], timeout: float = 20.0) -> Any:
    if method not in ALLOWED_METHODS:
        raise ValueError(f"forbidden non-read RPC method: {method}")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}).encode()
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "lpbot-base-sepolia-smoke/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if "error" in payload:
        raise RuntimeError(json.dumps(payload["error"], sort_keys=True))
    return payload["result"]


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("network") != ExecutionNetwork.BASE_SEPOLIA.value:
        raise ValueError("network must be base_sepolia")
    if int(config.get("expected_chain_id") or 0) != BASE_SEPOLIA_CHAIN_ID:
        raise ValueError("expected_chain_id must be 84532")
    unsafe = {
        "dry_run_only": config.get("dry_run_only") is not True,
        "signing_enabled": config.get("signing_enabled") is not False,
        "broadcast_enabled": config.get("broadcast_enabled") is not False,
        "live_trading": config.get("live_trading") is not False,
    }
    if any(unsafe.values()):
        raise ValueError("unsafe smoke flags: " + ",".join(key for key, bad in unsafe.items() if bad))


def dry_run(
    config: Mapping[str, Any],
    *,
    rpc_call: Callable[[str, str, Sequence[Any]], Any] = _post,
) -> dict[str, Any]:
    validate_config(config)
    url = str(config["rpc_url"])
    observed = int(rpc_call(url, "eth_chainId", []), 16)
    assert_executor_chain_id(ExecutionNetwork.BASE_SEPOLIA, observed)
    block = int(rpc_call(url, "eth_blockNumber", []), 16)
    weth = str(config["contracts"]["weth9"])
    code = str(rpc_call(url, "eth_getCode", [weth, "latest"]))
    if code in {"", "0x", "0x0"}:
        raise RuntimeError("configured Base Sepolia WETH9 has no code")

    # Read-only simulation of a state-changing approve.  eth_call discards all
    # state and cannot broadcast.  A placeholder spender is sufficient to
    # verify calldata and RPC simulation plumbing without a wallet.
    spender = str(config["contracts"].get("position_manager") or "0x1111111111111111111111111111111111111111")
    approve_data = encode_approve(spender, 1)
    approve_result = rpc_call(url, "eth_call", [{
        "from": ZERO_ADDRESS, "to": weth, "data": approve_data, "value": "0x0"
    }, "latest"])
    contracts_complete = all(config["contracts"].get(key) for key in ("position_manager", "token0", "token1", "pool"))
    stages = [
        {"stage": "chain_id_assert", "status": "PASS", "expected": BASE_SEPOLIA_CHAIN_ID, "observed": observed},
        {"stage": "rpc_read_health", "status": "PASS", "block_number": block, "weth_code_bytes": max(0, (len(code) - 2) // 2)},
        {"stage": "approve_exact_eth_call", "status": "PASS", "result": approve_result, "amount_raw": 1},
        {"stage": "mint_decrease_collect_revoke_eth_call", "status": "READY_FOR_CONFIG" if contracts_complete else "BLOCKED_CONTRACTS_NOT_CONFIGURED"},
        {"stage": "sign_broadcast_receipt_ledger", "status": "NOT_EXECUTED_REQUIRES_COMMANDER_APPROVAL"},
    ]
    return {
        "schema": "base_sepolia_smoke_dry_run_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network": ExecutionNetwork.BASE_SEPOLIA.value,
        "chain_id": observed,
        "rpc_url": url,
        "stages": stages,
        "full_contract_simulation_ready": contracts_complete,
        "safety": {
            "allowed_rpc_methods": sorted(ALLOWED_METHODS),
            "signed": False,
            "broadcast_count": 0,
            "wallet_access": 0,
            "keystore_reads": 0,
            "eth_send_raw_transaction_calls": 0,
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Base Sepolia smoke dry-run（只读）",
        "",
        f"chainId={report['chain_id']}；full_contract_simulation_ready={report['full_contract_simulation_ready']}。",
        "",
        "| stage | status |",
        "|---|---|",
    ]
    lines.extend(f"| {row['stage']} | {row['status']} |" for row in report["stages"])
    lines.extend([
        "",
        "本轮仅 eth_chainId / eth_blockNumber / eth_getCode / eth_call；signed=false，broadcast_count=0。",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Base Sepolia read-only smoke preparation")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = dry_run(config)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "dry_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "dry_run.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        f"Base Sepolia dry-run chain_id={report['chain_id']} "
        f"contract_ready={report['full_contract_simulation_ready']} broadcast=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
