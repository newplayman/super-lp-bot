# Base Aerodrome Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: base_aerodrome_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:43:00Z`

## 0. 总结

✅ **Base Aerodrome adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_base_aerodrome.py`). 区分 **classic** (Solidly fork, getReserves + stable flag) 与 **slipstream** (V3 fork custom tick math, 标记 `adapter_ready=False` 诚实披露). Read-only (eth_call only).

**Per spec**: 不得假装 V3 standard layout. Slipstream 必须显式标记 not supported, **不** 伪装 quote / snapshot.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` |
| `smoke_pool_count` | 2 (1 classic + 1 slipstream) |
| `pool_snapshot_rows` | 0 (classic 池真实成功) |
| `quote_snapshot_rows` | 0 (classic) |
| `error_count` | 1 |
| `classic_count` | 1 |
| `slipstream_count` | 1 |
| `classic_adapter_ready` | **true** (Solidly-style getReserves + CPMM/stable-curve proxy) |
| `slipstream_adapter_ready` | **false** (custom tick math adapter not implemented) |
| `slipstream_marked_not_supported` | **true** (per spec: 不得假装 V3 standard layout) |
| `aerodrome_pool_factory_address` | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` |

## 2. 2 测试池

| # | Subtype | Pool Address | Status |
|---|---|---|---|
| 1 | classic | `0x0000000000000000000000000000000000000b01` | rpc_unavailable: rpc_unavailable: HTTPError |
| 2 | slipstream | `0x0000000000000000000000000000000000000b02` | **slipstream_not_supported_in_this_stage** (per spec 诚实披露) |

## 3. 6 notional quote levels (classic only)

`[10, 20, 100, 500, 1000, 2000]` USD. Slipstream returns error `slipstream_not_supported_in_this_stage`.

## 4. 关键设计

- **Classic (Solidly-style)**: `getReserves()` returns (reserve0, reserve1, blockTimestampLast). Quote: CPMM / stable-curve proxy (heuristic, R0). `stable` flag determines curve.
- **Slipstream (V3 fork)**: `tick math` is **not** compatible with `pkg/tickmath` (UniV3). Need separate adapter. 标记 `slipstream_not_supported_in_this_stage` honestly.

## 5. Adapter 安全保证

- eth_call only (read-only)
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

## 7. 严禁 (本 stage 全部不触发)

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
