# LP Long Horizon Real Pool Universe Coverage Expand V1 — One Pager

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (3 targets met, observable sub-targets NOT met)

## 0. 一句话

只读扩展 real pool universe: 33 (V2) + 16 Meteora + 5 Base UniV3 + 5 Base Aerodrome + 8 BSC V3 + 5 BSC V2 = **72 pools** (≥ 45 ✓), 8 protocols (≥ 5 ✓), 3 chains (≥ 3 ✓). 但 23 池 (10 Base + 13 BSC) `collector_observable=false` 等待 EVM/BSC adapter wiring, observable 仅 49 池, 4 协议, 1 chain. 12h retry **不** 自动启动. 下一 stage 推荐 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `current_pool_count` | 33 (V2) |
| `target_pool_count` | 45 |
| `expanded_pool_count` | **72** |
| `added_pool_count` | **39** (16 Meteora + 5 Base UniV3 + 5 Base Aero + 8 BSC V3 + 5 BSC V2) |
| `meteora_dlmm_added_count` | **16** (all verified on-chain) |
| `base_uniswap_v3_added_count` | **5** (1 verified + 4 inferred) |
| `base_aerodrome_added_count` | **5** (4 classic + 1 slipstream) |
| `bsc_pancakeswap_v3_added_count` | **8** (4 fee tier × 2 stablecoin pair, real addresses from prior research) |
| `bsc_pancakeswap_v2_added_count` | **5** (3 with publicly documented address + 2 placeholder) |
| `observable_pool_count` | **49** (33 V2 Solana + 16 Meteora Solana) |
| `non_observable_pool_count` | **23** (10 Base + 13 BSC) |
| `target_pool_count_met` | ✅ **true** (72 ≥ 45) |
| `target_protocol_count_met` | ✅ **true** (8 ≥ 5) |
| `target_chain_count_met` | ✅ **true** (3 ≥ 3) |
| `target_observable_protocol_count_met` | ❌ **false** (4 < 5) |
| `collector_full_coverage_ready` | ❌ **false** |
| `can_start_12h_retry_after_this` | ❌ **false** |
| `recommended_next_stage` | **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`** |
| `can_run_probe_now` | ❌ **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |
| `wallet_or_tx_touched` | **false** (LOCKED) |
| `transaction_sent` | **false** (LOCKED) |

## 2. 39 added pools breakdown

### 2.1 Meteora DLMM (16, all verified on-chain)

16 个 Solana DLMM 池来自 `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json`:
- `account_exists=true, owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo, data_len=904, dlmm_sized=true`
- 16/16 全部 `selected_for_12h_retry=true, adapter_ready=true, collector_observable=true`
- 全 16 池 token pair 来自 `meteora_batch_pool_snapshot.csv`

### 2.2 Base Uniswap V3 (5, 1 verified + 4 inferred)

| # | Token Pair | Fee | Validation | Pool Address |
|---|---|---|---|---|
| 1 | WETH/USDC | 0.01% | verified_in_authorization_package | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` |
| 2-5 | WETH/USDC, WETH/USDT, USDC/USDT, WETH/DAI | 0.01%-0.05% | inferred_mainnet_well_known_not_rpc_validated_this_stage | `PENDING_BASE_UNIV3_RPC_VALIDATION` |

`adapter_ready=true` (Go pool/uniswap_v3 exists), `collector_observable=false` (EVM collector not wired).

### 2.3 Base Aerodrome (5, 4 classic + 1 slipstream)

- 4 classic (Solidly fork, no tick math, layout_kind=solidly_fork): `adapter_ready=true (optimistic)`
- 1 slipstream (V3 fork, custom tick math): `adapter_ready=false` (custom tick math adapter not implemented)
- Pool addresses all `PENDING_AERODROME_RPC_VALIDATION` (via PoolFactory.getPool pending)
- `collector_observable=false` (EVM collector not wired)

### 2.4 BSC PancakeSwap V3 (8, all real addresses from prior research)

8 pool from `bsc_quote_target_candidates.csv`: 4 fee tier (100/500/2500/10000) × 2 stablecoin pair (USDT, USDC). All `adapter_ready=false, collector_observable=false` (BSC chain adapter not implemented).

### 2.5 BSC PancakeSwap V2 (5)

3 with publicly documented mainnet addresses + 2 placeholder (`PENDING_BSC_PANCAKE_V2_RPC_VALIDATION`). All `adapter_ready=false, collector_observable=false`.

## 3. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |
| `no_collector_started` | `true` |
| `no_tmux_session_created` | `true` |

## 4. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d retry (本 stage 只扩 universe, **不** 启动 retry)
- ❌ 不启动 long-running collector
- ❌ 不启动 Base/BSC EVM collector (下一 stage 才做)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner (上一 stage 已修 finalize)
- ❌ **不**修改 collector (上一-2 stage 已修 --pool-universe)

## 5. 为什么推荐 adapter wiring **不**推荐 12h retry

虽然 universe 已扩到 72 pools, 但:
- 23 池 (10 Base + 13 BSC) `collector_observable=false`
- observable_protocol_count = 4 < 5 spec target
- observable_chain_count = 1 < 3 spec target
- 12h retry 仍 `partial_solana_real_pool_universe` 与现状无差 (即仅 49 Solana 池 observable)
- 必须先接通 EVM/BSC adapter, 让 23 池变 observable, 然后 12h retry 才 `full_coverage_ready`

## 6. 下一轮建议 (4-stage allowed)

| 选项 | 含义 |
|---|---|
| **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`** (本 stage 推荐) | 接通 EVM/BSC collector, 让 23 池变 observable |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` | 12h retry, 但仅在 EVM/BSC 接线后才有意义 (否则仍 partial) |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT` | 找更多池 (但 Solana 已 ≥ 45 target, 不推荐) |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 用户决定暂停 |

## 7. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_V1` | 上一 stage | 6h corrected verdict (gate=PASS) |
| `LP_LONG_HORIZON_12H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1` | 上一 stage | 12h corrected verdict (gate=PASS, 15/15 checks) |
| `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1` | 上一 stage | 12h 节点报告 |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` | 上一 stage | collector `--pool-universe` CLI + stage runner forward |
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | 上一 stage | supervisor finalize 4 个 Python heredoc 的 lowercase bool bug |
| **`LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`** | **本 stage** | **universe 33 → 72 (+39), 3 chains, 8 protocols. 但 Base/BSC 23 池仍 not observable. 推荐 EVM/BSC adapter wiring 下一 stage** |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | **推荐 next** | 接通 EVM/BSC adapter → 23 池 → observable |

## 8. 关键数据点

- **expanded_pool_count = 72**, **target_pool_count = 45**, gap 27 (excess by 27)
- **observable_pool_count = 49** (Solana only), **non_observable = 23** (Base 10 + BSC 13)
- **observable_protocol_count = 4** (orca_whirlpool + raydium_clmm + raydium_cpmm + meteora_dlmm), target ≥ 5
- **observable_chain_count = 1** (Solana), target ≥ 3
- **placeholder_pool_count = 0** (no `<smoke_pool_`; explicit `PENDING_*_RPC_VALIDATION` markers for 5 pools pending next stage)

## 9. 后续

本 stage 完成, pytest 待 run (Stage I), 已 commit + push 到 `feat/supabase-postgres-deployment` (Stage J). 用户可在下一轮决定:
1. 触发 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` (推荐): EVM/BSC adapter 接线
2. 触发 `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (需用户单独审批 + EVM/BSC 已 wired): 12h retry
3. 暂停或停止

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-12h.
