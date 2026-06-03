# LP Candidate Scoring — Stage H

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- script: `scripts/lp_candidate_scoring_v1_readonly.py`

## 1. 评分维度（10 项 + 1 项 total）

```text
fee_velocity_score                weight=0.15  (realistic scenario net_ev / notional, normalized)
survival_score                   weight=0.20  (1 - oor_risk at 15m)
cost_score                       weight=0.15  (1 - cost / notional, normalized)
capacity_score                   weight=0.15  (capacity_N from Stage E)
liquidity_score                  weight=0.10  (log-scaled liquidity)
data_confidence_score            weight=0.10  (Stage E confidence)
wallet_availability_score        weight=0.05  (1 if Base, 0 otherwise)
actual_probe_feasibility_score   weight=0.05  (state + quote + cost ready)
notional_scalability_score       weight=0.03  (capacity_2000 / capacity_10)
chain_risk_score                 weight=0.02  (heuristic per chain)
```

## 2. 关键结果

```text
pools_scored  = 134
score_count   = 804 (134 × 6 notionals)
```

## 3. Top 5 by notional

### 3.1 notional $10

| chain | protocol | pair | fee | score | class |
|---|---|---|---|---|---|
| Base | PancakeSwap V3 | WETH/DAI | 500 | 0.638 | watch |
| Base | PancakeSwap V3 | WETH/DAI | 100 | 0.630 | watch |
| Base | PancakeSwap V3 | WETH/USDC | 500 | 0.624 | watch |
| Base | PancakeSwap V3 | WETH/USDC | 2500 | 0.616 | watch |
| Base | PancakeSwap V3 | WETH/USDT | 100 | 0.607 | watch |

### 3.2 notional $20

| chain | protocol | pair | fee | score | class |
|---|---|---|---|---|---|
| Base | PancakeSwap V3 | WETH/DAI | 500 | 0.422 | needs_data |
| Base | PancakeSwap V3 | WETH/DAI | 100 | 0.414 | needs_data |
| Base | PancakeSwap V3 | WETH/USDC | 100 | 0.412 | needs_data |
| BSC | PancakeSwap V3 | USDC/USDT | 100 | 0.409 | needs_data |
| BSC | PancakeSwap V3 | USDC/USDT | 500 | 0.409 | needs_data |

### 3.3 notional $100-$2000 (同样 5 池, score 0.40-0.42)

- Base PancakeSwap V3 WETH/DAI fee 500 (top)
- Base PancakeSwap V3 WETH/DAI fee 100
- Base PancakeSwap V3 WETH/USDC fee 100
- BSC PancakeSwap V3 USDC/USDT fee 100
- BSC PancakeSwap V3 USDC/USDT fee 500

## 4. 关键观察

1. **Base PancakeSwap V3 WETH/DAI 是 notional 10/20/100/.../2000 全档位的 top1**。这与上游 universe audit 提示的"current universe 偏窄"一致 — model 对 Base DAI 路径有强偏好。
2. **BSC USDC/USDT 在 $20+ 仍出现** — 上游 BSC best_pool 是 WBNB/USDT 0.01% (fee 100), 但 model 选 USDC/USDT，因为 model 的 fee_apr 表里 BSC=0.25 且 USDC/USDT 是稳定对（IL/LVR proxy 较低）。
3. **无 candidate_now** — model 严守 gate：score < 0.55 → needs_data, wallet_score=0 → watch, EV<=0 → watch。**0 个池**同时满足 wallet_funded AND positive EV AND high score。
4. **wallet_availability 是限制因子** — 除 Base 0 分；其他 5 chain 全 0 分。如果用户准备资金到 Arbitrum/Optimism，top 5 会立即变化。

## 5. 含义

- 当前模型下"无任何池子值得 EV-positive 实盘 10/20U probe"
- 即使外推到 2000U 也不变（cost_structure 主导）
- 4 候选都基于 proxy fee_apr；实际 fee 可能 ±50%；结论**稳健**

## 6. 安全断言

```text
this_stage_only_runs_model       = true
wallet_or_tx_touched             = false
can_run_probe_now                = false
```
