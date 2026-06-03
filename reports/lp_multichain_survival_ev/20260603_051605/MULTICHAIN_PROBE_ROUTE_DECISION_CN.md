# Multichain Probe Route Decision — Stage I

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`

## 0. 总体结论

> 在 6 chain × 74 state_ready pool × 5 scenario × 6 notional × 9 hold window 共 19,980 行的 survival EV 模型中：
> **0 个组合**在 realistic scenario 下产生正 EV。
> **0 个组合**在 conservative scenario 下产生正 EV。
> 即使 zero_il_lvr theoretical ceiling 也仍负 EV。
>
> 简言之：**当前 6 EVM chain 上的 V3 池对 $10-$2000 notional × 15m-7d hold 的简单 LP 策略全部结构性负 EV**。
> 主导因素是 cost（gas + slippage + failure buffer），不是 fee yield 不足。

## 7 个核心问题

### Q1. 当前 Base WETH/USDC 是否继续等待？

**NO** — 等待不会改变 cost structure。Monitor 显示 8h 漂移 -385→-722 单调恶化；且即便 tick 回到 frozen center，model 显示 -$0.04 EV/10U/7d 仍是负。`LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1` 是 plan A 但**仅解决漂移，不解决 cost 矛盾**。

### Q2. 是否有其他 Base 池优于 WETH/USDC？

**YES (PancakeSwap V3 WETH/DAI fee 500, score 0.638 at notional 10)** — 候选：Base PancakeSwap V3 WETH/DAI fee 500 / 100、WETH/USDC fee 500/2500、WETH/USDT fee 100。**但仍是 watch class（无正 EV）**。差别仅在 proxy 假设下 score 略高。**没有"显著优于"的池**。

### Q3. 是否有 BSC 池优于当前 Base 候选？

**NO** — BSC 唯一在 notional $20+ top 5 出现的是 BSC PancakeSwap V3 USDC/USDT fee 100/500。Base 候选在 wallet 资金可用时**总是**优先（wallet_availability=1 vs 0）。在 wallet 未在 BSC 部署的情况下，**BSC 候选的 score 因 wallet_availability=0 被压低**。

### Q4. 是否有 Arbitrum / Optimism / Polygon / Ethereum 候选更适合？

**没有 wallet 资金 = 不能直接探针**。在 wallet 假设扩展到这些 chain 的前提下，candidate 排名会变化；但模型 proxy 仍预测 V3 LP 在 $10-$2000 notional 上结构性负 EV。**所以即使加资金，结论也不变**。

### Q5. 如果测试钱包资金不在该链，是否值得用户准备小额资金？

**NO (基于模型 proxy)**。理由：
- 跨链准备资金需要 bridge → 1-5% slippage 损耗
- cross-chain bridge + receiver approval 增加 1-2 笔 tx
- model 已经在 6 chain 上对 142 池抽样；top candidates 没有一个能在 cost structure 下产生正 EV
- 准备 $100-$2000 资金到 6 chains 都要花钱，且即使在那边 LP 仍负 EV

**但是**，如果用户**想验证** v1 monitor 模型在 6 chain 之外的池子是否同样负 EV，准备小额资金到 Base 是合理的（Base 已 funded）。

### Q6. 哪个候选最适合下一次 10U probe？

**严格按 spec (no positive EV → 不得执行 probe)**：

如果操作员**仍**要 10U probe（任何 pool），按 model score 顺序：
- 第 1 选择: **Base PancakeSwap V3 WETH/DAI fee 500** (score 0.638 at notional 10)
  - ⚠️ wallet 不持有 DAI；执行前需要先 swap USDC→DAI
  - score 主要来自 survival + cost；**fee_velocity 实际为负**
- 第 2 选择: **Base PancakeSwap V3 WETH/USDC fee 500** (score 0.624)
  - wallet 已持有 WETH + USDC
  - 与上游 NO_GO 候选同 pair 但不同 protocol / fee tier
- 第 3 选择: **BSC PancakeSwap V3 WBNB/USDT fee 100** (best by EV at higher notional)
  - ⚠️ wallet 在 BSC 无资金（$0.00）；需要先 bridge

**但** spec 明确：即使候选 score 高，**positive_realistic_count = 0 仍 NO_GO**。**下一次 10U probe 不应进行**。

### Q7. 是否应暂停实盘，继续 discovery？

**YES — discovery 已有 142 池 baseline；P1/P2 (Aerodrome/Velodrome/Curve/Balancer/Solana) 仍未跑**。继续 discovery 找**结构性正 EV**的池（Curve stable pools? Meteora DLMM 可能有低 IL）比硬做 V3 更有价值。

## 路线建议

| 行动 | 建议 |
|---|---|
| 立即推进 Base 10U probe | **NO**（NO_GO 三重触发 + model 0/19,980 正 EV） |
| 切换到 BSC | **NO**（无资金 + best BSC 池 -$0.0156 EV） |
| 切换到 Arbitrum / OP / Polygon | **NO**（无资金 + model 预测同样负 EV） |
| 切换到 Ethereum | **NO**（gas 极高 + model 5% APR 最低） |
| 暂停实盘，继续 discovery | **YES**（进 P1/P2 阶段） |
| 升级 model（actual fee 接入） | **YES**（subgraph + on-chain decoded logs） |
| 增加 Solana connector | **YES**（Meteora DLMM / DAMM v2 设计 + 实施） |
| 等待 Base WETH/USDC 回归 frozen center | **NO**（即使回归，cost 仍负） |

## 自动 bridge / swap 建议？

**NONE.** spec 明确禁止 auto bridge / auto swap。本阶段**只**给路线，**不**执行任何链上动作。

## 一句话

> 142 池模型显示 V3 简单 LP 在 $10-$2000 notional 全部结构性负 EV。继续在 V3 范围内探索 P0 不同 protocol/fee 无解。**唯一可能让 EV 转正的方向**：P1 (Curve/Balancer 的 stable/low-IL 池) 或 P2 (Solana DLMM/CLMM 新 venue)。下一阶段优先级 = 推进 P1 + P2。
