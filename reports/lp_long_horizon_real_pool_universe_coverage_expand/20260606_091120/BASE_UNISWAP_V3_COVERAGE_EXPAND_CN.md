# Base Uniswap V3 Coverage Expand

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: Base Uniswap V3
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:15:00Z`

## 0. 总结

✅ **Base Uniswap V3 coverage 已扩** (1 verified + 4 inferred). 5 个池全部 `selected_for_12h_retry=true` 但全部 `collector_observable=false` (EVM collector 未接通). 本 stage 没有 RPC-validate 4 个 inferred pool 的 pool_address (使用 `PENDING_BASE_UNIV3_RPC_VALIDATION` placeholder until 下一 stage EVM wiring 后再 getPool).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `chain` | base |
| `protocol` | uniswap_v3 |
| `pool_type` | v3 |
| `candidate_count` | 5 |
| `verified_rpc_validated_count` | **1** (WETH/USDC 0.01% from prior authorization_package) |
| `inferred_not_rpc_validated_count` | **4** |
| `selected_for_12h_retry_count` | **5** |
| `adapter_ready` | **true** (Go adapter `internal/adapters/pool/uniswap_v3` exists) |
| `collector_observable` | **false** (EVM collector not wired to long-horizon pipeline) |
| `evm_collector_status` | `evm_collector_not_wired_into_smoke_mode_yet` |
| `placeholder_pool_count` | **0** (no `<smoke_pool_`, all entries have explicit validation_status) |
| `tvl_hint` | None (R0 不量化) |
| `volume_hint` | None (R0 不量化) |

## 2. 5 candidate pools (1 verified + 4 inferred)

| # | Token Pair | Fee | Validation Status | Pool Address | Source |
|---|---|---|---|---|---|
| 1 | WETH/USDC | 0.01% (100) | **verified_in_authorization_package** | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | reports/lp_base_10u_probe_execution_authorization_package/20260602_184806/FINAL_VERDICT.json |
| 2 | WETH/USDC | 0.05% (500) | inferred_mainnet_well_known_not_rpc_validated_this_stage | `PENDING_BASE_UNIV3_RPC_VALIDATION` | public_base_mainnet_uniswap_v3_factory_pool_listing |
| 3 | WETH/USDT | 0.05% (500) | inferred_mainnet_well_known_not_rpc_validated_this_stage | `PENDING_BASE_UNIV3_RPC_VALIDATION` | public_base_mainnet_uniswap_v3_factory_pool_listing |
| 4 | USDC/USDT | 0.01% (100) | inferred_mainnet_well_known_not_rpc_validated_this_stage | `PENDING_BASE_UNIV3_RPC_VALIDATION` | public_base_mainnet_uniswap_v3_factory_pool_listing |
| 5 | WETH/DAI  | 0.05% (500) | inferred_mainnet_well_known_not_rpc_validated_this_stage | `PENDING_BASE_UNIV3_RPC_VALIDATION` | public_base_mainnet_uniswap_v3_factory_pool_listing |

**诚实披露**: 4 个 inferred pool 的 `pool_address` 是 placeholder (`PENDING_BASE_UNIV3_RPC_VALIDATION`), 不是真实地址. 它们的 `validation_status=inferred_mainnet_well_known_not_rpc_validated_this_stage`. 下一 stage `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` 需先 RPC-validate 4 个 inferred pool 的真实 address (via `eth_call` to UniswapV3Factory.getPool), 然后再加入 effective 12h universe.

## 3. Token Addresses (Base mainnet, public)

| Symbol | Address |
|---|---|
| WETH | `0x4200000000000000000000000000000000000006` |
| USDC | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| USDT | `0xfde4c96c8593536e31f229ea8f37b2ada2699bb2` |
| DAI  | `0x50c5725949a6f0c72e6c4a641f24049a917db0cb` |

## 4. Base Adapter Status

| Component | Status |
|---|---|
| Go pool adapter (uniswap_v3) | ✅ exists (`internal/adapters/pool/uniswap_v3`) |
| EVM collector wiring to long-horizon pipeline | ❌ not wired |
| Base RPC connectivity | ✅ public Base mainnet RPC works |
| Public endpoint | `https://mainnet.base.org` |

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

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer (使用 public Base mainnet RPC if needed)

## 7. 下游

进入 Stage D (Base Aerodrome) + Stage E (BSC PancakeSwap) → 合并到 expanded universe (Stage F) → coverage gap decision (Stage G).
