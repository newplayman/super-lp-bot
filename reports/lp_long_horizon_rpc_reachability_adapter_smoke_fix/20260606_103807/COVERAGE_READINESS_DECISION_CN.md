# Coverage Readiness Decision

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: coverage_readiness_decision
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:48:00Z`

## 0. 总结

⚠️ **5 conditions NOT all met** — observable_pool_count=49 / chain=2. 主要因 Base public RPC 在此 env 不可达.

## 1. 5 conditions

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count_ge_45` | ≥ 45 | **49** | ✅ met |
| `observable_chain_count_ge_3` | ≥ 3 | **2** | ❌ NOT met |
| `observable_protocol_count_ge_5` | ≥ 5 | **5** | ✅ met |
| `placeholder_pool_count_eq_0` | = 0 | **0** | ✅ met |
| `no_wallet_tx_probe` | yes | **yes** | ✅ met (locked) |

**Failed conditions**: ['observable_chain_count_ge_3']

## 2. RPC Reachability

| Chain | Reachable | Selected Endpoint |
|---|---|---|
| base | ❌ | `none` |
| bsc | ✅ | `https://bsc-dataseed.binance.org` |
| solana | ✅ | `https://api.mainnet-beta.solana.com` |

## 3. 关键字段

| 字段 | 值 |
|---|---|
| `expanded_pool_count` | 72 |
| `observable_pool_count` | 49 |
| `non_observable_pool_count` | 23 |
| `observable_chain_count` | 2 |
| `observable_protocol_count` | 5 |
| `all_5_conditions_met` | **false** |
| `collector_full_coverage_ready` | **false** |
| `can_start_12h_real_universe_retry` | **false** |
| `recommended_next_stage` | **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** |

## 4. 推荐 next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`**

理由: 5 conditions NOT all met: failed=['observable_chain_count_ge_3']. Base public RPC **unreachable** in this env (4 endpoints 全部 403 Forbidden / Connection reset). observable_chain_count=2 < 3. 需要 fix_repeat: 在能 reach public Base RPC 的 env 再 smoke, 或等 RPC 改善.

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

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
