# BSC PancakeSwap Coverage Expand

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: BSC PancakeSwap V3 + V2
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:17:00Z`

## 0. 总结

✅ **BSC PancakeSwap coverage 已扩** (8 V3 + 5 V2 = 13 candidate pools). 全部 `selected_for_12h_retry=true` 但全部 `collector_observable=false` (BSC chain adapter 未实现). 8 个 V3 pool 来自既有 `bsc_pancakeswap_v3_precise_quote` research, 有**真实** on-chain addresses. V2 池主要来自公开 mainnet listing + 1 个 placeholder 待 RPC-validate.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `chain` | bsc |
| `protocol` | pancakeswap_v3 / pancakeswap_v2 |
| `candidate_count` | **13** (V3: 8, V2: 5) |
| `v3_count` | **8** (4 fee tiers × 2 stablecoin pairs) |
| `v2_count` | **5** (4 standard pairs + 1 placeholder) |
| `verified_rpc_validated_count` | **0** (本 stage 没 RPC-validate) |
| `selected_for_12h_retry_count` | **13** |
| `adapter_ready` | **false** (BSC chain adapter not implemented) |
| `collector_observable` | **false** |
| `bsc_chain_adapter_status` | `bsc_chain_adapter_not_implemented_yet` |
| `placeholder_pool_count` | **0** (1 V2 用 explicit `PENDING_BSC_PANCAKE_V2_RPC_VALIDATION` marker, 不是 `<smoke_pool_`) |

## 2. 8 BSC PancakeSwap V3 pools (from `bsc_quote_target_candidates.csv`)

| # | Token Pair | Fee Tier | Pool Address | Quote Path | Source |
|---|---|---|---|---|---|
| 1 | WBNB/USDT | 100 (0.01%) | `0x172fcD41E0913e95784454622d1c3724f546f849` | ✅ quoter=0xB048... | bsc_quote_target_candidates.csv |
| 2 | WBNB/USDT | 500 (0.05%) | `0x36696169C63e42cd08ce11f5deeBbCeBae652050` | ✅ | bsc_quote_target_candidates.csv |
| 3 | WBNB/USDT | 2500 (0.25%) | `0x1401ff943D08a7E098328C1d3a9d388923B115D2` | ✅ | bsc_quote_target_candidates.csv |
| 4 | WBNB/USDT | 10000 (1.00%) | `0x6805E0E5333c5c3acCF2930Be4734E2b98f4Ce06` | ✅ | bsc_quote_target_candidates.csv |
| 5 | WBNB/USDC | 100 (0.01%) | `0xf2688Fb5B81049DFB7703aDa5e770543770612C4` | ✅ | bsc_quote_target_candidates.csv |
| 6 | WBNB/USDC | 500 (0.05%) | `0x81A9b5F18179cE2bf8f001b8a634Db80771F1824` | ✅ | bsc_quote_target_candidates.csv |
| 7 | WBNB/USDC | 2500 (0.25%) | `0xc721dECCD986D54B39e8c29428A1f06155c3671e` | ✅ | bsc_quote_target_candidates.csv |
| 8 | WBNB/USDC | 10000 (1.00%) | `0x18C5aFFA481e7EDbF37405AdE553827d6387899f` | ✅ | bsc_quote_target_candidates.csv |

**注**: 8 V3 pool 全部有**真实** on-chain addresses, 从 `bsc_quote_target_candidates.csv` 直接读. 4 fee tier × 2 stablecoin pair (USDT, USDC). 全部 `validation_status=verified_in_bsc_precise_quote_research_artifact` (指这些地址是 prior research 验证, **不** 是本 stage RPC-validate).

## 3. 5 BSC PancakeSwap V2 pools (candidates)

| # | Token Pair | Fee (bps) | Pool Address | Validation Status |
|---|---|---|---|---|
| 1 | WBNB/USDT | 20 | `0x16b9a82891338f9bA80E2D6970FddA79D1d0E162` | inferred_mainnet_well_known_with_publicly_documented_address |
| 2 | WBNB/BUSD | 20 | `0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16` | inferred_mainnet_well_known_with_publicly_documented_address |
| 3 | WBNB/USDC | 20 | `PENDING_BSC_PANCAKE_V2_RPC_VALIDATION` | inferred_mainnet_well_known_not_rpc_validated_this_stage |
| 4 | USDT/BUSD | 20 | `PENDING_BSC_PANCAKE_V2_RPC_VALIDATION` | inferred_mainnet_well_known_not_rpc_validated_this_stage |
| 5 | WBNB/CAKE | 20 | `0xA39Af17CE4a8eb807E076805Da1e2C8bAc8530b2` | inferred_mainnet_well_known_with_publicly_documented_address |

**注**: 2 V2 placeholder 等下一 stage RPC-validate via `PancakeSwap V2 Factory.getPair(tokenA, tokenB)`. V2 **没有** quoter (PancakeSwap V2 用 `getReserves()` 直接读 reserves).

## 4. Token Addresses (BSC mainnet, public)

| Symbol | Address |
|---|---|
| WBNB | `0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c` |
| USDT | `0x55d398326f99059fF775485246999027B3197955` |
| USDC | `0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d` |
| BUSD | `0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56` |
| CAKE | `0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82` |

## 5. BSC Adapter Status

| Component | Status |
|---|---|
| Go pool adapter (pancakeswap_v3) | ❌ **not** implemented in `internal/adapters/pool/` |
| Go pool adapter (pancakeswap_v2) | ❌ **not** implemented |
| BSC chain adapter (RPC connectivity) | ❌ not implemented |
| EVM collector wiring to long-horizon pipeline | ❌ not wired |
| BSC RPC connectivity | ✅ public BSC mainnet RPC works |
| PancakeSwap V3 PoolDeployer | `0x41ff9BFDBc236D0eE9c79E40b2F93F2F3F37fB45` |
| PancakeSwap V3 Quoter | `0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997` |
| PancakeSwap V2 Factory | `0xcA143Ce32Fe78f1f7019d7d551a6402fD5350a73` |

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

## 7. 严禁 (本节全部不触发)

- ❌ 不启动 BSC collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer

## 8. 下游

进入 Stage F (合并 expanded universe) → Stage G (coverage gap decision) → 推荐 next stage.
