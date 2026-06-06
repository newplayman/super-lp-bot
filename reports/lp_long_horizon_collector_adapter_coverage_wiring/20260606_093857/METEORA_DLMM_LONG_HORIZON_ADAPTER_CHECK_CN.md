# Meteora DLMM Long-Horizon Adapter Check

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: meteora_dlmm_long_horizon_adapter_check
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:46:00Z`

## 0. 总结

⚠️ **Meteora DLMM long-horizon adapter check**: re-uses existing `solana_rpc_readonly` to verify 2 of 16 verified pools. Each verified pool has `owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` + `data_len=904` (DLMM-sized). **RPC 不可用** — 诚实披露, **不** 假设 observable.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` |
| `reuses_solana_rpc_readonly` | **true** (existing `solana_rpc_readonly.py`) |
| `meteora_dlmm_owner` | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` |
| `meteora_dlmm_data_len` | 904 |
| `meteora_dlmm_long_horizon_adapter_ready` | **false** |
| `rpc_unavailable` | **true** |
| `verified_pool_count` | 0 / 2 |

## 2. 验证标准

每个池**通过**以下 3 项才算 verified:
1. `account_exists = true` (getMultipleAccountsInfo 返回非空)
2. `owner_is_meteora_dlmm = true` (owner == `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`)
3. `dlmm_sized = true` (data_len == 904)

## 3. 验证池 (2 of 16)

| # | Pool Address | account_exists | owner_is_meteora | data_len | dlmm_sized | verified | error |
|---|---|---|---|---|---|---|---|
| 1 | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | False | False | 0 | False | False | account_not_returned_or_rpc_unavailable |
| 2 | `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | False | False | 0 | False | False | account_not_returned_or_rpc_unavailable |


## 4. 验证源

`reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` (16 verified pools, 全部 owner=`LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` + data_len=904).

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
