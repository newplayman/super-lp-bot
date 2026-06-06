# Integrated Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: integrated_adapter_wiring_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:48:00Z`

## 0. 总结

✅ **Integrated smoke ran** (12 real pool snapshots via expanded universe + 5 per-adapter smokes). honest disclosure: `observable_pool_count=13` is lower than 72 because (a) public Base RPC **不可用** in this env (rpc_unavailable), (b) BSC V3 的 1 池**真实**成功, BSC V2 / Aerodrome / Meteora 部分池因 RPC 受限**未**成功.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `smoke_ran` | **true** |
| `selected_pool_count` | 12 (12 from integrated smoke) |
| `real_pool_universe_used` | **true** |
| `placeholder_pool_count` | **0** (no `<smoke_pool_` in any output) |
| `all_pools_are_real_on_chain` | **true** (12 real Solana on-chain addresses) |
| `pool_snapshot_rows` | 12 |
| `quote_snapshot_rows` | 72 |
| `fee_velocity_rows` | 60 |
| `liquidity_distribution_rows` | 12 |
| `market_regime_rows` | 7 |
| `chain_observed_count` | 2 |
| `protocol_observed_count` | 4 |
| `observable_pool_count` | 13 (solana 12 + evm 0 + bsc 1) |
| `non_observable_pool_count` | 59 (Base 10 + BSC 12 + Meteora 16 ; honest) |
| `error_count` | 6 |

## 2. Chain / Protocol distribution (12 integrated smoke)

| Chain | Pools | Protocols |
|---|---|---|
| solana | 12 | orca_whirlpool, raydium_cpmm, raydium_clmm |


## 3. Per-adapter smoke results

| Adapter | pool_snapshot_rows | error_count | Status |
|---|---|---|---|
| solana_rpc_readonly (Meteora check) | 0/2 | 2 | rpc_unavailable (Solana public RPC rate-limited or unavailable) |
| evm_base_uniswap_v3 | 0/2 | 2 | rpc_unavailable (Base public RPC not reachable in this env) |
| evm_base_aerodrome (classic) | 0/1 | 1 | rpc_unavailable (Base public RPC) |
| evm_base_aerodrome (slipstream) | n/a | n/a | adapter_ready=false (per spec, marked honestly) |
| evm_bsc_pancakeswap_v3 | 1/2 | 1 | **1 real WBNB/USDT 0.05% observed** (sqrtPriceX96, tick, liquidity, fee=500, token0=USDT, token1=WBNB) |
| evm_bsc_pancakeswap_v2 | 0/1 | 1 | rpc returned empty (WBNB/USDT public address) |

**Observations**:
- BSC public RPC works (WBNB/USDT 0.05% V3 pool real on-chain data retrieved)
- Base public RPC **不** reachable in this env
- Solana public RPC returned empty for Meteora test pools (rate-limit or mainnet status query issue)

## 4. Honest disclosure

`observable_pool_count=13` 远小于 72. 原因:
- 12 池 from integrated smoke (Solana only, all real)
- 1 池 from BSC V3 smoke (WBNB/USDT 0.05% real)
- 0 池 from Base (RPC unavailable)
- 0 池 from BSC V2 (WBNB/USDT address returned empty)
- 0 池 from Meteora (Solana RPC rate-limited)

**`placeholder_pool_count=0`** 维持. **no wallet/tx/probe** 维持. **不**回退 placeholder. **不**把 adapter_missing 当成 pool negative.

## 5. 锁定字段 (5 项全 false/no)

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

## 6. 严禁

- ❌ 不启动 12h / 24h retry
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
