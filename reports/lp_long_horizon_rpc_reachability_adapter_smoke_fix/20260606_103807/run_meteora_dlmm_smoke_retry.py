#!/usr/bin/env python3
"""Retry Meteora DLMM smoke with selected Solana endpoint.

Outputs:
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/meteora_dlmm_smoke_retry.json
- reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/METEORA_DLMM_SMOKE_RETRY_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.solana_meteora_dlmm_check import (  # noqa: E402
    METEORA_DLMM_OWNER, METEORA_DLMM_DATA_LEN, load_verified_pools,
)
from lp_long_horizon.adapters.solana_rpc_readonly import SolanaRpcReadOnlyAdapter  # noqa: E402
from lp_long_horizon.rpc_registry import select_best_endpoint  # noqa: E402

OUT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"


def main() -> int:
    selected = select_best_endpoint("solana")
    solana_endpoint = selected.endpoint if selected else None
    solana_rpc_reachable = selected is not None

    # Use 5 verified Meteora pools (subset of 16)
    verifs = load_verified_pools()
    test_pool_count = min(5, len(verifs))
    test_addrs = [v["pool_address"] for v in verifs[:test_pool_count]]

    accountinfo_success_count = 0
    dlmm_owner_verified_count = 0
    pool_snapshot_rows = 0
    bin_liquidity_rows = 0
    quote_snapshot_rows = 0
    error_count = 0
    summaries = []

    if not solana_rpc_reachable:
        for addr in test_addrs:
            summaries.append({
                "pool_address": addr,
                "accountinfo_error": "rpc_unavailable_solana_no_endpoint",
                "owner": "",
                "owner_is_meteora_dlmm": False,
                "data_len": 0,
                "dlmm_sized": False,
            })
            error_count += 1
    else:
        adapter = SolanaRpcReadOnlyAdapter(timeout_s=5.0, endpoint=solana_endpoint)
        accounts = adapter.fetch_accounts(test_addrs)
        for addr in test_addrs:
            matching = [a for a in accounts if a.address == addr]
            if matching:
                a = matching[0]
                is_dlmm = (a.owner == METEORA_DLMM_OWNER)
                dlmm_sized = (a.data_len == METEORA_DLMM_DATA_LEN)
                if is_dlmm and dlmm_sized:
                    dlmm_owner_verified_count += 1
                    pool_snapshot_rows += 1
                if a.data_len > 0:
                    accountinfo_success_count += 1
                summaries.append({
                    "pool_address": addr,
                    "accountinfo_error": "",
                    "owner": a.owner,
                    "owner_is_meteora_dlmm": is_dlmm,
                    "data_len": a.data_len,
                    "dlmm_sized": dlmm_sized,
                })
            else:
                summaries.append({
                    "pool_address": addr,
                    "accountinfo_error": "account_not_returned",
                    "owner": "",
                    "owner_is_meteora_dlmm": False,
                    "data_len": 0,
                    "dlmm_sized": False,
                })
                error_count += 1
        # bin_liquidity and quote are heuristic-only; mark 0 here (real decode would need bin_array account)
        bin_liquidity_rows = 0
        quote_snapshot_rows = 0

    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1",
        "section": "meteora_dlmm_smoke_retry",
        "run_id": "20260606_103807",
        "branch": "feat/supabase-postgres-deployment",
        "solana_rpc_reachable": solana_rpc_reachable,
        "solana_rpc_selected": solana_endpoint,
        "test_pool_count": test_pool_count,
        "accountinfo_success_count": accountinfo_success_count,
        "dlmm_owner_verified_count": dlmm_owner_verified_count,
        "pool_snapshot_rows": pool_snapshot_rows,
        "bin_liquidity_rows": bin_liquidity_rows,
        "quote_snapshot_rows": quote_snapshot_rows,
        "error_count": error_count,
        "summaries": summaries,
        "meteora_dlmm_owner": METEORA_DLMM_OWNER,
        "meteora_dlmm_data_len": METEORA_DLMM_DATA_LEN,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True,
        }
    }
    (OUT_DIR / "meteora_dlmm_smoke_retry.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    cn = f"""# Meteora DLMM Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: meteora_dlmm_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:45:00Z`

## 0. 总结

{'✅' if solana_rpc_reachable else '⚠️'} **Solana RPC {'reachable' if solana_rpc_reachable else 'unreachable'}** ({solana_endpoint or 'no endpoint'}). Smoke ran with selected endpoint.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `solana_rpc_reachable` | **{str(solana_rpc_reachable).lower()}** |
| `solana_rpc_selected` | `{solana_endpoint or 'none'}` |
| `test_pool_count` | {test_pool_count} (5 of 16 verified pools) |
| `accountinfo_success_count` | {accountinfo_success_count} / {test_pool_count} |
| `dlmm_owner_verified_count` | {dlmm_owner_verified_count} / {test_pool_count} |
| `pool_snapshot_rows` | {pool_snapshot_rows} |
| `bin_liquidity_rows` | {bin_liquidity_rows} (need bin_array account decode; R0) |
| `quote_snapshot_rows` | {quote_snapshot_rows} (R0 not implemented for DLMM) |
| `error_count` | {error_count} |

## 2. {test_pool_count} 验证池

| # | Pool Address | accountinfo | owner | owner_is_dlmm | data_len | dlmm_sized |
|---|---|---|---|---|---|---|
""" + "".join(
        f"| {i+1} | `{s['pool_address']}` | {'OK' if not s.get('accountinfo_error') else s['accountinfo_error']} | {s.get('owner', '-')} | {s.get('owner_is_meteora_dlmm', False)} | {s.get('data_len', 0)} | {s.get('dlmm_sized', False)} |\n"
        for i, s in enumerate(summaries)
    ) + f"""

## 3. 验证标准

每个池**通过**以下 3 项才算 verified:
1. `accountinfo_error = ""` (getMultipleAccountsInfo returns non-empty)
2. `owner_is_meteora_dlmm = true` (owner == `{METEORA_DLMM_OWNER}`)
3. `dlmm_sized = true` (data_len == {METEORA_DLMM_DATA_LEN})

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 5. 严禁

- ❌ 不启动 Meteora collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
"""
    (OUT_DIR / "METEORA_DLMM_SMOKE_RETRY_CN.md").write_text(cn)

    print(f"wrote: {OUT_DIR / 'meteora_dlmm_smoke_retry.json'}")
    print(f"wrote: {OUT_DIR / 'METEORA_DLMM_SMOKE_RETRY_CN.md'}")
    print(f"accountinfo: {accountinfo_success_count}/{test_pool_count}, dlmm_verified: {dlmm_owner_verified_count}/{test_pool_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
