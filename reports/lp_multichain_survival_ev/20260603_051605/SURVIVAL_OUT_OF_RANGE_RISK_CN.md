# Survival Out-of-Range Risk — Stage G

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- script: `scripts/lp_survival_out_of_range_risk_v1_readonly.py`

## 1. 模型

对每个 (chain, protocol, pool, hold_window)：

- 默认 `range_width = 400` ticks (±200 dynamic range from v2 executor)
- 历史 tick move stddev per hour (per chain, derived from upstream monitor for Base WETH/USDC, heuristic for others)
- `p50 = 0.67 * sd * sqrt(hours)`
- `p90 = 1.65 * sd * sqrt(hours)`
- `p95 = 1.96 * sd * sqrt(hours)`
- `out_of_range_risk = 2 * (1 - Phi(half_width / std))`

Base historical anchor: 47 samples, p95_abs_drift=664, max=722.

## 2. 关键结果

```text
pools_evaluated    = 74
row_count          = 666 (74 × 9 holds)
high_risk_count    = 164
medium_risk_count  = 148
low_risk_count     = 354
```

## 3. Top high-risk (Base WETH/USDC 主导)

| chain | pool | hold | oor | survival |
|---|---|---|---|---|
| Base | PancakeSwap V3 WETH/USDC | 7d | 0.95 | 0.05 |
| Base | PancakeSwap V3 WETH/USDC | 3d | 0.92 | 0.08 |
| Base | PancakeSwap V3 WETH/USDC | 24h | 0.86 | 0.14 |
| Base | PancakeSwap V3 WETH/USDC | 12h | 0.81 | 0.19 |

> 含义：Base WETH/USDC 即使 fee_apr 较好，**7d survival 只有 5%**。这是 upstream monitor NO_GO 的模型化体现。

## 4. 决策含义

- 任何 > 12h 的 hold 在 Base 都不安全（survival < 19%）
- 短 hold (15m - 1h) 在大多数链 + 多数 pair 都有 > 50% survival
- 但 Stage F 显示即使 short hold 净 EV 仍负（cost 主导）
- → 综合 Stage F + G：**多链多 pool 在当前 cost structure 下结构性负 EV**

## 5. 安全断言

```text
this_stage_only_runs_model       = true
wallet_or_tx_touched             = false
signer_created                   = false
can_run_probe_now                = false
```
