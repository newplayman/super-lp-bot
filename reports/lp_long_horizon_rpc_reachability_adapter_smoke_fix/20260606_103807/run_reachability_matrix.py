#!/usr/bin/env python3
"""Run RPC reachability matrix.

Probes each chain's endpoints via the rpc_registry, records latency + error
honestly (no fake success).

Outputs:
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/rpc_reachability_matrix.csv
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/rpc_reachability_matrix.json
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/RPC_REACHABILITY_MATRIX_CN.md
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.rpc_registry import (  # noqa: E402
    RPC_REGISTRY, list_endpoints, probe_chain,
)

OUT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    all_results: list[dict] = []
    selected_per_chain: dict[str, str] = {}

    for r in RPC_REGISTRY:
        chain = r["chain"]
        results = probe_chain(chain, timeout_s=5.0)
        for hr in results:
            all_results.append({
                "chain": hr.chain,
                "endpoint_name": (
                    "env_override" if (hr.endpoint == list_endpoints(chain)[0].endpoint
                                       and list_endpoints(chain)[0].is_override)
                    else f"fallback_{hr.endpoint.split('//')[1].split('/')[0].split('.')[0]}"
                ),
                "endpoint_redacted": hr.endpoint,
                "reachable": hr.reachable,
                "latency_ms": hr.latency_ms,
                "method_tested": hr.method_tested,
                "response_preview": hr.response_preview,
                "error": hr.error,
            })
            if hr.reachable and chain not in selected_per_chain:
                selected_per_chain[chain] = hr.endpoint

    # Write JSON
    out_json = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
        "section": "rpc_reachability_matrix",
        "run_id": "20260606_103807",
        "branch": "feat/supabase-postgres-deployment",
        "generated_at_utc": "2026-06-06T10:42:00Z",
        "selected_per_chain": selected_per_chain,
        "total_endpoints_probed": len(all_results),
        "reachable_count": sum(1 for r in all_results if r["reachable"]),
        "results": all_results,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True,
        }
    }
    (OUT_DIR / "rpc_reachability_matrix.json").write_text(json.dumps(out_json, indent=2, ensure_ascii=False))

    # Write CSV
    csv_path = OUT_DIR / "rpc_reachability_matrix.csv"
    fieldnames = ["chain", "endpoint_name", "endpoint_redacted", "reachable",
                  "latency_ms", "method_tested", "response_preview", "error"]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_results:
            w.writerow(r)

    # Build CN
    reachable_per_chain = {}
    for r in all_results:
        if r["reachable"]:
            reachable_per_chain.setdefault(r["chain"], []).append(r["endpoint_redacted"])

    cn = f"""# RPC Reachability Matrix

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: rpc_reachability_matrix
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:42:00Z`

## 0. 总结

✅ **RPC reachability matrix 已跑** ({len(all_results)} endpoints probed). Honest 记录: failures 标记 `reachable=False` + error string. **不** 假装成功.

## 1. Per-chain selected (first reachable, for downstream smoke)

| Chain | Selected Endpoint | Reachable |
|---|---|---|
""" + "".join(
        f"| {chain} | `{endpoint}` | ✅ |\n"
        for chain, endpoint in sorted(selected_per_chain.items())
    ) + f"""

## 2. Per-chain reachability summary

| Chain | Total Probed | Reachable | Unreachable |
|---|---|---|---|
""" + "".join(
        f"| {chain} | {sum(1 for r in all_results if r['chain'] == chain)} | {sum(1 for r in all_results if r['chain'] == chain and r['reachable'])} | {sum(1 for r in all_results if r['chain'] == chain and not r['reachable'])} |\n"
        for chain in {"base", "bsc", "solana"}
    ) + f"""

## 3. Detailed results

| Chain | Endpoint | Reachable | Latency (ms) | Method | Error |
|---|---|---|---|---|---|
""" + "".join(
        f"| {r['chain']} | `{r['endpoint_redacted']}` | {'✅' if r['reachable'] else '❌'} | {r['latency_ms']} | {r['method_tested']} | {r['error'] or '-'} |\n"
        for r in all_results
    ) + f"""

## 4. Method

- base/bsc: `eth_chainId` (validate chain_id matches expected 8453 / 56)
- solana: `getHealth` (validate result == "ok")
- All probes are read-only JSON-RPC POST; no signing, no tx
- Timeout: 5.0s per probe

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 6. 严禁

- ❌ 不启动 long-running collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写真实 secret

## 7. 下游

进入 Stage D (Base retry) + E (BSC retry) + F (Meteora retry). 用本 stage `selected_per_chain` 的 endpoint.
"""
    (OUT_DIR / "RPC_REACHABILITY_MATRIX_CN.md").write_text(cn)

    print(f"wrote: {OUT_DIR / 'rpc_reachability_matrix.json'}")
    print(f"wrote: {OUT_DIR / 'rpc_reachability_matrix.csv'}")
    print(f"wrote: {OUT_DIR / 'RPC_REACHABILITY_MATRIX_CN.md'}")
    print(f"total probed: {len(all_results)}, reachable: {out_json['reachable_count']}")
    print(f"selected per chain: {selected_per_chain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
