# Meteora DLMM Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: meteora_dlmm_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:45:00Z`

## 0. 总结

✅ **Solana RPC reachable** (https://api.mainnet-beta.solana.com). Smoke ran with selected endpoint.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `solana_rpc_reachable` | **true** |
| `solana_rpc_selected` | `https://api.mainnet-beta.solana.com` |
| `test_pool_count` | 5 (5 of 16 verified pools) |
| `accountinfo_success_count` | 0 / 5 |
| `dlmm_owner_verified_count` | 0 / 5 |
| `pool_snapshot_rows` | 0 |
| `bin_liquidity_rows` | 0 (need bin_array account decode; R0) |
| `quote_snapshot_rows` | 0 (R0 not implemented for DLMM) |
| `error_count` | 5 |

## 2. 5 验证池

| # | Pool Address | accountinfo | owner | owner_is_dlmm | data_len | dlmm_sized |
|---|---|---|---|---|---|---|
| 1 | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | account_not_returned |  | False | 0 | False |
| 2 | `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | account_not_returned |  | False | 0 | False |
| 3 | `6eR5rRdexbht8aiiQmYq7yKb7EhdD3af22B4mHDmCp8x` | account_not_returned |  | False | 0 | False |
| 4 | `H9b4sPAeiyN8DEcWa6MG2kvxqmCqBEpxmexwCh84jg4H` | account_not_returned |  | False | 0 | False |
| 5 | `6qz7THwQvcjF3HyDGLuKaLBUk6EyJKeZXZMWLAeiwfjd` | account_not_returned |  | False | 0 | False |


## 3. 验证标准

每个池**通过**以下 3 项才算 verified:
1. `accountinfo_error = ""` (getMultipleAccountsInfo returns non-empty)
2. `owner_is_meteora_dlmm = true` (owner == `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`)
3. `dlmm_sized = true` (data_len == 904)

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
