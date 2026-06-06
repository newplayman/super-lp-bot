# Integrated Observable Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: integrated_observable_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:47:00Z`

## 0. 总结

✅ **Integrated smoke ran** (45 real pool snapshots, 0 placeholder). observable_pool_count = **49** (solana 45 + evm 0 + bsc 4).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `smoke_ran` | **true** |
| `selected_pool_count` | 45 (45 from integrated) |
| `real_pool_universe_used` | **true** |
| `placeholder_pool_count` | **0** |
| `all_pools_are_real_on_chain` | **true** |
| `pool_snapshot_rows` | 45 |
| `quote_snapshot_rows` | 270 (45 × 6 notional) |
| `fee_velocity_rows` | 225 (45 × 5 windows) |
| `market_regime_rows` | 7 |
| `chain_observed_count` | 2 |
| `protocol_observed_count` | 5 |
| `observable_pool_count` | **49** (solana 45 + evm 0 + bsc 4) |
| `non_observable_pool_count` | 23 |

## 2. Chain / Protocol distribution (45 integrated)

| Chain | Pools | Protocols |
|---|---|---|
| solana | 45 | orca_whirlpool, raydium_cpmm, raydium_clmm, meteora_dlmm |


## 3. Unobservable reasons (honest disclosure)

| Chain | Reason |
|---|---|
| base | rpc_unavailable_all_endpoints_403_or_connection_reset |
| meteora_solana | solana_public_rpc_returned_empty_for_5_test_pools |


## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 5. 严禁

- ❌ 不启动 12h / 24h retry
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
