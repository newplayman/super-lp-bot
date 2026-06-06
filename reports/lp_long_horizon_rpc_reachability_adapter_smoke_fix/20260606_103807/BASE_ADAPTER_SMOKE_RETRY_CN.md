# Base Adapter Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: base_adapter_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:43:00Z`

## 0. 总结

⚠️ **Base RPC unreachable** (no endpoint). Honest 记录: 4 个 Base public endpoint 全部 403 Forbidden / Connection reset, 不能 reach Base 链. Smoke 跳到 honest 状态.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `base_rpc_reachable` | **false** |
| `base_rpc_selected` | `none` |
| `uniswap_v3_smoke_success_count` | 0 / 2 |
| `aerodrome_classic_smoke_success_count` | 0 / 1 |
| `aerodrome_slipstream_supported` | **false** (per spec, marked unsupported) |
| `slipstream_supported` | **false** |
| `pool_snapshot_rows` | 0 |
| `quote_snapshot_rows` | 0 |
| `error_count` | 4 |

## 2. 4 个测试池

| # | Adapter | Subtype | Pool Address | Status |
|---|---|---|---|---|
| 1 | BaseUniV3 | (default) | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (verified WETH/USDC 0.01%) | rpc_unavailable |
| 2 | BaseUniV3 | (default) | `0x0000000000000000000000000000000000000a01` (placeholder) | rpc_unavailable |
| 3 | Aerodrome | classic | `0x0000000000000000000000000000000000000b01` | rpc_unavailable |
| 4 | Aerodrome | slipstream | `0x0000000000000000000000000000000000000b02` | slipstream_not_supported_in_this_stage (per spec, marked unsupported) |

## 3. Slipstream adapter gap (per spec)

**Slipstream (V3 fork, custom tick math)**: 标记 `slipstream_not_supported_in_this_stage` honestly. **不** 假装 V3 standard layout.

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

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
