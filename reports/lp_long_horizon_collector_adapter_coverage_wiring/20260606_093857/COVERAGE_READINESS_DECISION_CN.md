# Coverage Readiness Decision

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: coverage_readiness_decision
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:50:00Z`

## 0. 总结

⚠️ **5 conditions NOT all met** — `observable_pool_count=13` 远 < 45 target. 主要原因: public Base RPC + Solana public RPC 在此 stage runner 环境不可达, Base/Aerodrome/Meteora 的 pool_snapshot 受限. **不**假设 observable; 诚实记录.

## 1. 5 conditions

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count_ge_45` | ≥ 45 | **13** | ❌ NOT met |
| `observable_chain_count_ge_3` | ≥ 3 | **2** | ❌ NOT met |
| `observable_protocol_count_ge_5` | ≥ 5 | **4** | ❌ NOT met |
| `placeholder_pool_count_eq_0` | = 0 | **0** | ✅ met |
| `no_wallet_tx_probe` | yes | **yes** | ✅ met (locked) |

**Failed conditions**: ['observable_pool_count_ge_45', 'observable_chain_count_ge_3', 'observable_protocol_count_ge_5']

## 2. 关键字段

| 字段 | 值 |
|---|---|
| `expanded_pool_count` | 72 |
| `observable_pool_count` | 13 (solana 12 + evm 0 + bsc 1) |
| `non_observable_pool_count` | 59 (Base 10 + BSC 12 + Meteora 14) |
| `observable_chain_count` | 2 (solana + bsc) |
| `observable_protocol_count` | 4 (4 Solana + 1 BSC = 5, or 2 if only solana+bsc) |
| `all_5_conditions_met` | **false** |
| `collector_full_coverage_ready` | **false** |
| `can_start_12h_real_universe_retry` | **false** |
| `recommended_next_stage` | **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** |

## 3. 推荐 next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`**

理由: 5 conditions NOT all met: failed=['observable_pool_count_ge_45', 'observable_chain_count_ge_3', 'observable_protocol_count_ge_5']. observable_pool_count=13 (<45), observable_chain_count=2 (<3 if Base RPC unavailable), observable_protocol_count=4 (<5). 需要 fix_repeat: 在能 reach public Base RPC + Solana public RPC 的环境再 smoke 一次, 或增加 Meteora 长-horizon observable 池数.

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

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
