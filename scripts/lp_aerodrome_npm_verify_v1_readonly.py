#!/usr/bin/env python3
"""Verify the three official Aerodrome Slipstream NPMs without wallet access."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.base_m1_executor_v1 import JsonRpc, verify_aerodrome_npm_deployments


def build_report(rpc_url: str) -> dict:
    rpc = JsonRpc(rpc_url)
    chain_id = int(rpc.call("eth_chainId", []), 16)
    if chain_id != 8453:
        raise RuntimeError(f"expected Base mainnet chain id 8453, observed {chain_id}")
    deployments = verify_aerodrome_npm_deployments(rpc)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS",
        "chain_id": chain_id,
        "rpc_url": rpc_url,
        "read_only": True,
        "wallet_access": False,
        "signed": False,
        "broadcast_count": 0,
        "hash_algorithm": "sha256",
        "official_source": "https://github.com/aerodrome-finance/slipstream#deployments",
        "deployments": deployments,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Aerodrome Slipstream NPM 链上核验",
        "",
        f"结论：**{report['verdict']}**。Base chain id={report['chain_id']}；签名 0、广播 0、钱包访问 0。",
        "",
        "官方地址来源：<https://github.com/aerodrome-finance/slipstream#deployments>",
        "",
        "| deployment | NPM | code bytes | SHA-256 | factory() | WETH9() |",
        "|---|---|---:|---|---|---|",
    ]
    for row in report["deployments"]:
        lines.append(
            f"| {row['official_deployment']} | `{row['address']}` | {row['code_bytes']} | "
            f"`{row['code_sha256']}` | `{row['factory']}` | `{row['weth9']}` |"
        )
    lines += [
        "",
        "核验逻辑已经固化进 Base mainnet 执行器构造阶段：任一地址无代码、字节码长度/哈希不符，"
        "或 `factory()` / `WETH9()` 返回不符，启动立即失败，签名与广播路径不可达。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default="https://base-rpc.publicnode.com")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.rpc_url)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "npm_verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.out_dir / "NPM_VERIFICATION.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "deployments": len(report["deployments"]), "broadcast_count": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
