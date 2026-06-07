# 12h 未证明什么 (What 12h Did Not Prove) — 12h Node Report Review

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

12h 跑通**不**证明 LP 有正 EV / 实际 fee 数据 / range-tick-bin fee capture / 53 池都值得参与 / full chain coverage. 12h 仍 r0 phase, **不** 等于 r1, **不** 等于 edge proven, **不** 等于可进入 probe. 任何 LP 决策仍 blocked by freeze + r0 → r1 upgrade.

## 1. 12h 未证明 (8 项 critical)

### 1.1 ❌ 不证明 LP 有正 EV

**为什么**: r0 phase 数据无 actual fee accrual, 无 IL realized vs IL actual, 无 tokenId 位置信息. EV = (fee + reward) - (IL + gas + rebalance + opportunity cost), 这 4 个 component 在 r0 都是 0 / placeholder.

**证据**:
- fee_capture_proxy_usd 全 0 (smoke_placeholder)
- il_realized_pct / il_actual_pct 全 null
- actual_pnl_usd 全 null
- preflight_candidate_count = 0
- ev_ready_pool_count = 0

**结论**: LP edge **未** proven (`edge_proven="no"`).

### 1.2 ❌ 不证明 LP 没肉 (low fee / 负 IL / LVR 主导)

**为什么**: 反向同样, r0 phase 数据**不**能证明 LP 亏或赚. 12h 跑通只证明 pipeline 跑通, **不** 是 backtest. 反向证明需要 actual fee data + actual IL data + 真实 on-position tokenId.

**证据**:
- 所有 fee_velocity 行 sample_count=0
- 所有 quote_snapshots 行 amount_in_raw=0, amount_out_raw=0
- 所有 liquidity_distribution 行 active_range_liquidity=0
- 所有 market_regime 行 price_change_pct=0, realized_vol_pct=0

**结论**: "LP 没肉" 同样**未** proven. **不** 可下"LP 不会亏"的结论.

### 1.3 ❌ 不证明可进入 probe

**为什么**: probe 需要 actual fee data + tier classification + preflight candidate list + freeze reopen. 12h 跑通仅证明 pipeline, **不** 证明 data layer.

**证据**:
- can_run_probe_now = false (LOCKED)
- preflight_candidate_count = 0
- tier_classifier_output = DEFERRED_TO_R1
- freeze active

**结论**: **不** 可进入 probe (LPBOT_PROBE / TINY_CANARY / LIVE / PAPER 全 blocked).

### 1.4 ❌ 不证明 actual fee accrual

**为什么**: actual fee accrual 需要 on-position tokenId (user 实际 mint 的 LP NFT / position) + entry snapshot + exit snapshot + tokenId-based feeGrowthInside 跨 ckpt diff. r0 phase **不** mint 任何 position (因 freeze), **不** 拿任何 tokenId, **不** 算 actual fee.

**证据**:
- actual_fee_accrual_placeholder.json 12 ckpt × 1 placeholder
- 全部字段 entry_fee_growth_global=null, exit_fee_growth_global=null, tokens_owed_a_raw=null, tokens_owed_b_raw=null, actual_collected_a_raw=null
- r0_phase_status: "schema only, no records; r1 requires user-provided tokenId"

**结论**: actual fee accrual **未** proven, **不** 是 LP 决策 input.

### 1.5 ❌ 不证明真实 range / tick / bin fee capture

**为什么**: 真实 V3 range fee capture 需要 (a) on-position tokenId, (b) tickLower/tickUpper, (c) feeGrowthInside0/1 跨 snapshot diff. 真实 DLMM bin fee capture 需要 (a) on-position tokenId, (b) bin_id 范围, (c) DLMM indexer 实时数据. 真实 CPMM fee share 需要 (a) on-position tokenId, (b) reserve0/reserve1 实时数据.

**证据**:
- pool_snapshots.jsonl active_tick=null, active_bin=null
- liquidity_distribution.jsonl active_range_liquidity=0, tick_spacing=null, bin_step=null
- 12h 跑通只跑 quote_snapshots 模拟 (smoke_placeholder), **不** 跑真实 QuoterV2 staticcall (因 no live RPC)

**结论**: V3/CLMM range fee / DLMM bin fee / CPMM fee share **未** proven, **不** 是 LP 决策 input.

### 1.6 ❌ 不证明 53 个池都值得参与

**为什么**: 池值得参与需要:
- actual fee > IL + gas + rebalance + opportunity cost (EV > 0)
- tier classification 满足 (a/b/c)
- 池不在 hard rejection list (e.g. tier_c_hard_rejection_policy)
- 历史 fee velocity > 阈值
- 实际 TVL 趋势 stable / growing

12h r0 phase **不** 验证任何一条.

**证据**:
- 53 池全部 smoke_placeholder, preflight_candidate_count=0
- 53 池全部 r0_candidate_ready=false
- tier_classifier_output = DEFERRED_TO_R1
- tier_c_hard_rejection_policy **不** applied (因 r0)

**结论**: 53 池**未** proven 值得参与. 53 池**也未** proven 不值得参与. **不** 是 LP 决策 input.

### 1.7 ❌ 不证明 full chain coverage

**为什么**: full coverage 需 5 chains (Base / Solana / BSC / Ethereum / Arbitrum) × ≥3 DEX per chain × ≥10 pool per DEX. 12h 仅 2 chains (Solana + BSC) + 5 DEX + 53 pool, Base 0 池 (RPC 403), Ethereum / Arbitrum **不** 在本 stage.

**证据**:
- coverage_scope = partial_solana_bsc_real_universe
- do_not_treat_as_full_universe = true
- chain_distribution: {solana: 49, bsc: 4}
- missing_chains: [base, ethereum, arbitrum] (ethereum/arbitrum not in this stage)

**结论**: 12h **不** 是 full coverage, **不** 当 full coverage 用.

### 1.8 ❌ 不证明 market regime-aware sizing

**为什么**: market regime-aware sizing 需要 real-time price feed (Pyth / CoinGecko) + realized vol 跨 7d/30d window + volume-to-tvl ratio. r0 phase price_change_pct=0, realized_vol_pct=0, volume_to_tvl_pct=0.

**证据**:
- market_regime.jsonl smoke_placeholder=true, price_change_pct=0, realized_vol_pct=0
- volume_to_tvl_pct=0
- regime 标签是**静态**分配 (per token_pair), **不** 是 real-time market data

**结论**: market regime-aware sizing **未** proven, **不** 是 LP 决策 input.

## 2. 12h 未证明的"反面" (8 项反向, 同样 blocked)

为了对称起见, 反向也**不**证明:
- ❌ 不证明 53 池都不值得参与 (同样 blocked by r0)
- ❌ 不证明 LP 必然亏 (同样 blocked by r0)
- ❌ 不证明 Solana 比 BSC 好 (proxy 数据无效)
- ❌ 不证明 orca_whirlpool 比 raydium_clmm 好 (proxy 数据无效)
- ❌ 不证明 fee tier 0.01% 比 0.05% 适合 LP (proxy 数据无效)
- ❌ 不证明 stable pair (USDC/USDT) 比 volatile pair (SOL/USDC) 稳定 (proxy 数据无效)
- ❌ 不证明 12h 内任何 regime 切换发生过 (regime 静态分配)
- ❌ 不证明任何"此刻 LP 是否好" (proxy 数据无效)

## 3. critical gap 总结

| Gap | 阻塞原因 | R1 修复需要 |
|---|---|---|
| actual fee accrual | 无 on-position tokenId | user mint 实际 LP position (需 freeze reopen) |
| actual IL | 无 entry/exit price snapshot | 历史 Pyth/CoinGecko 集成 + 跨 snapshot diff |
| actual range/tick/bin fee | 无 on-position tokenId | 同上 |
| actual quote | 无 live RPC | Base RPC 修复 or paid RPC (freeze blocks) |
| actual reserve/liquidity | 无 live RPC | 同上 |
| actual market regime | 无 real-time price feed | Pyth/CoinGecko 集成 (not yet wired) |
| actual fee velocity | 无 on-position tokenId + 无 live volume | 跨 ckpt tokenId-based diff + volume proxy 集成 |
| full chain coverage | Base 不可达 (env) + eth/arb 未集成 | env change or paid RPC + 跨 chain adapter 集成 |

## 4. 重要 disclaimer

12h 跑通**不**等于:
- ❌ 不等于 LP 决策可有 (无 actual fee, 无 preflight candidate)
- ❌ 不等于"再跑 24h 就有数据" (24h 仍是 r0 proxy, 同样无 actual data)
- ❌ 不等于 48h / 72h / 7d 可破 (time 不解决 r0 → r1 升级)
- ❌ 不等于"先做 backtest 即可" (backtest 需 historical fee/IL data, 同样 blocked by r0)

**唯一** 推进路径: R0 → R1 real data upgrade (具体见 `R0_TO_R1_DATA_UPGRADE_PLAN_CN.md`).

## 5. 锁定字段 (LOCKED, 12h 后仍不翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | r0 + freeze |
| `tiny_canary_allowed` | `"no"` | r0 + freeze |
| `edge_proven` | `"no"` | r0 phase |
| `global_lp_rejected` | `false` | 12h 跑通 ≠ 拒绝 LP, 仍 r0 不够数据 |
| `actual_fee_data_available` | `false` | r0 placeholder |
| `fee_proxy_only` | `true` | r0 proxy only |
| `candidate_decision_reliable` | `false` | preflight=0, data_insufficient=53 |
| `preflight_candidate_count` | 0 | r0 |
| `watchlist_count` | 0 | r0 |
| `data_insufficient_count` | 53 | r0 |
| `r1_upgrade_required` | `true` | r0 → r1 mandatory before any LP decision |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
