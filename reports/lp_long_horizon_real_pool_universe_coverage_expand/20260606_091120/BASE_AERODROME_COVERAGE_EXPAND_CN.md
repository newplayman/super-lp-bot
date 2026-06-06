# Base Aerodrome Coverage Expand

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: Base Aerodrome
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:16:00Z`

## 0. 总结

✅ **Base Aerodrome coverage 已扩** (4 classic + 1 slipstream = 5 candidate pools). 全部 `selected_for_12h_retry=true` 但 `collector_observable=false` (EVM collector 未接通). **Slipstream** 子类型标记 `adapter_ready=false` (custom tick math 与 Uniswap V3 不兼容, 需单独 adapter).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `chain` | base |
| `protocol` | aerodrome |
| `candidate_count` | 5 |
| `classic_count` | **4** (Solidly-style, no tick math) |
| `slipstream_count` | **1** (V3-style, custom tick math) |
| `verified_rpc_validated_count` | **0** (本 stage 没 RPC-validate, 用 PoolFactory.getPool 推断) |
| `inferred_not_rpc_validated_count` | **5** |
| `selected_for_12h_retry_count` | **5** |
| `aerodrome_pool_factory_address` | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` (well-known on-chain) |
| `adapter_ready_classic` | **true** (Go adapter 概念上可 reuse Solidly/Pool pattern, 但**未** 在本 stage 验证) |
| `adapter_ready_slipstream` | **false** (custom tick math adapter not implemented) |
| `collector_observable` | **false** |
| `placeholder_pool_count` | **0** (no `<smoke_pool_`) |

## 2. 5 candidate pools (4 classic + 1 slipstream)

| # | Subtype | Token Pair | Stable | Validation Status | Adapter Ready | Layout Kind |
|---|---|---|---|---|---|---|
| 1 | classic | WETH/USDC | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 2 | classic | WETH/USDT | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 3 | classic | USDC/USDT | true  | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 4 | classic | WETH/AERO | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | true | solidly_fork |
| 5 | slipstream | WETH/USDC | false | inferred_mainnet_well_known_not_rpc_validated_this_stage | **false** | v3_fork_custom_tick_math |

**关键区别**:
- **Aerodrome classic** (Solidly fork): 没有 tick math, 不用 Uniswap V3 layout. Pool reserves_x / reserves_y + LP token supply 直接读. Adapter 概念上可 reuse existing Solidly pattern.
- **Aerodrome Slipstream** (V3 fork): 有 tick math, 但**与 Uniswap V3 不兼容** (Aerodrome 自定义 tick spacing, fee 计算). 需单独 adapter (类似 UniV3 但 tick 公式不同). `adapter_ready=false`.

## 3. Token Addresses (Base mainnet, public)

| Symbol | Address |
|---|---|
| WETH | `0x4200000000000000000000000000000000000006` |
| USDC | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| USDT | `0xfde4c96c8593536e31f229ea8f37b2ada2699bb2` |
| DAI  | `0x50c5725949a6f0c72e6c4a641f24049a917db0cb` |
| AERO | `0x940181a94a35a4569e4529a3cdfb74e38fd98631` |

## 4. Aerodrome Adapter Status

| Component | Status |
|---|---|
| Go pool adapter (aerodrome) | ❌ **not** implemented in `internal/adapters/pool/` |
| EVM collector wiring to long-horizon pipeline | ❌ not wired |
| Base RPC connectivity | ✅ public Base mainnet RPC works |
| Aerodrome PoolFactory address | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` (public mainnet) |

**诚实披露**: `adapter_ready_classic=true` 是**乐观** 标记. 实际 Aerodrome Go adapter 还未实现. 仅当 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` 完成后才能确认.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 6. 严禁 (本节全部不触发)

- ❌ 不启动 Aerodrome collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer

## 7. 下游

进入 Stage E (BSC PancakeSwap V3/V2) → 合并到 expanded universe (Stage F) → coverage gap decision (Stage G).
