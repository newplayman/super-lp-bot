#!/usr/bin/env python3
"""Short smoke for Meteora DLMM long-horizon adapter check.

Verifies that 2 of the 16 Meteora DLMM verified pools can be read by the
existing solana_rpc_readonly adapter (read-only, no signing).

Outputs:
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/meteora_dlmm_long_horizon_adapter_check.json
- reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/METEORA_DLMM_LONG_HORIZON_ADAPTER_CHECK_CN.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(ROOT / "scripts"))
from lp_long_horizon.adapters.solana_meteora_dlmm_check import (  # noqa: E402
    run_check, METEORA_DLMM_OWNER, METEORA_DLMM_DATA_LEN,
)

OUT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    result = run_check(max_pools=2, timeout_s=5.0)
    out = {
        "stage": "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
        "section": "meteora_dlmm_long_horizon_adapter_check",
        "run_id": "20260606_093857",
        "branch": "feat/supabase-postgres-deployment",
        "adapter_file": "scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py",
        "meteora_dlmm_owner": METEORA_DLMM_OWNER,
        "meteora_dlmm_data_len": METEORA_DLMM_DATA_LEN,
        "reuses_solana_rpc_readonly": True,
        "meteora_dlmm_long_horizon_adapter_ready": result.get("smoke_ran", False) and result.get("verified_pool_count", 0) > 0,
        "rpc_unavailable": result.get("rpc_unavailable", True),
        **result,
        "no_touch_invariants": {
            "no_wallet_keypair_signer": True,
            "no_tx_send_approve_mint": True,
            "no_production_write": True,
            "no_collector_started": True,
            "no_12h_retry_started": True
        }
    }
    (OUT_DIR / "meteora_dlmm_long_horizon_adapter_check.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    summaries = result.get("summaries", [])
    verified_count = result.get("verified_pool_count", 0)
    test_count = result.get("test_pool_count", 0)

    cn = f"""# Meteora DLMM Long-Horizon Adapter Check

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: meteora_dlmm_long_horizon_adapter_check
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:46:00Z`

## 0. 总结

{'✅' if verified_count > 0 else '⚠️'} **Meteora DLMM long-horizon adapter check**: re-uses existing `solana_rpc_readonly` to verify {test_count} of 16 verified pools. Each verified pool has `owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` + `data_len=904` (DLMM-sized). {'Meteora DLMM **是** long-horizon observable.' if verified_count > 0 else '**RPC 不可用** — 诚实披露, **不** 假设 observable.'}

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` |
| `reuses_solana_rpc_readonly` | **true** (existing `solana_rpc_readonly.py`) |
| `meteora_dlmm_owner` | `{METEORA_DLMM_OWNER}` |
| `meteora_dlmm_data_len` | {METEORA_DLMM_DATA_LEN} |
| `meteora_dlmm_long_horizon_adapter_ready` | **{str(out['meteora_dlmm_long_horizon_adapter_ready']).lower()}** |
| `rpc_unavailable` | **{str(result.get('rpc_unavailable', True)).lower()}** |
| `verified_pool_count` | {verified_count} / {test_count} |

## 2. 验证标准

每个池**通过**以下 3 项才算 verified:
1. `account_exists = true` (getMultipleAccountsInfo 返回非空)
2. `owner_is_meteora_dlmm = true` (owner == `{METEORA_DLMM_OWNER}`)
3. `dlmm_sized = true` (data_len == {METEORA_DLMM_DATA_LEN})

## 3. 验证池 (2 of 16)

| # | Pool Address | account_exists | owner_is_meteora | data_len | dlmm_sized | verified | error |
|---|---|---|---|---|---|---|---|
""" + "".join(
        f"| {i+1} | `{s['pool_address']}` | {s['account_exists']} | {s['owner_is_meteora_dlmm']} | {s['data_len']} | {s['dlmm_sized']} | {s['verified']} | {s['error'] or '-'} |\n"
        for i, s in enumerate(summaries)
    ) + f"""

## 4. 验证源

`reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` (16 verified pools, 全部 owner=`{METEORA_DLMM_OWNER}` + data_len={METEORA_DLMM_DATA_LEN}).

## 5. Adapter 安全保证

- Re-uses `solana_rpc_readonly` (existing read-only Solana JSON-RPC adapter)
- No signing, no keypair, no transaction
- 自检 `_self_check()`: module refuses to import if banned tokens present
- 复用 `scripts/lp_long_horizon/utils/retry.py` + `abort.py`

## 6. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 7. 严禁

- ❌ 不启动 Meteora collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
"""
    (OUT_DIR / "METEORA_DLMM_LONG_HORIZON_ADAPTER_CHECK_CN.md").write_text(cn)
    print(f"wrote: {OUT_DIR / 'meteora_dlmm_long_horizon_adapter_check.json'}")
    print(f"wrote: {OUT_DIR / 'METEORA_DLMM_LONG_HORIZON_ADAPTER_CHECK_CN.md'}")
    print(f"verified: {verified_count}/{test_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
