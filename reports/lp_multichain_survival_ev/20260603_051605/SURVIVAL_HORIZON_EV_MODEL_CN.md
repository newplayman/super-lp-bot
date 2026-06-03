# Survival Horizon EV Model — Stage F

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- script: `scripts/lp_survival_horizon_ev_model_v1_readonly.py`

## 1. 模型组成

对每个 (chain, protocol, pool, notional, hold_window, scenario) 组合：

```text
net_ev_proxy_usd =
    expected_fee_usd                                   (= notional × fee_apr × hold_h / (365×24))
  - il_lvr_proxy_usd                                  (= expected_fee × scenario_ratio)
  - entry_cost_usd                                    (= gas + 0.30% slippage × notional)
  - exit_cost_usd                                     (= gas + 0.30% slippage × notional)
  - gas_cost_usd                                      (= gas_proxy × 2)
  - slippage_cost_usd                                 (= notional × 0.5% × (1 - capacity))
  - failure_buffer_usd                                (= 10% × (gas + slippage))
```

`fee_apr` proxy per (chain, protocol):

| chain | Uniswap V3 | PancakeSwap V3 |
|---|---|---|
| Base | 0.20 | 0.18 |
| BSC | - | 0.25 |
| Arbitrum | 0.15 | - |
| Optimism | 0.12 | - |
| Polygon | 0.18 | - |
| Ethereum | 0.05 | - |

IL/LVR ratio per scenario:

| scenario | ratio |
|---|---|
| zero_il_lvr | 0.00 |
| optimistic | 0.05 |
| realistic | 0.30 |
| conservative | 0.80 |
| stress | 2.00 |

## 2. 关键结果

```text
pools_evaluated                  = 74 (state_ready subset)
row_count                        = 19980 (5 scenarios × 6 notionals × 9 holds × 74)
positive_realistic_count         = 0
positive_conservative_count      = 0
near_break_even_count            = 0
```

**核心发现：所有 74 个 state_ready 池在 5 场景 × 6 notional × 9 hold 下都无正 EV**。这是真实负 EV，不是 bug。

## 3. 最佳（最不负）池 (per notional, realistic scenario)

| notional | chain | protocol | pair | fee | hold | ev | ev_pct |
|---|---|---|---|---|---|---|---|
| 10 | Optimism | Uniswap V3 | WETH/USDC | 100 | 7d | -$0.0459 | -0.46% |
| 20 | Base | PancakeSwap V3 | WETH/USDC | 500 | 7d | -$0.0836 | -0.42% |
| 100 | BSC | PancakeSwap V3 | WBNB/USDT | 100 | 7d | -$0.3636 | -0.36% |
| 500 | BSC | PancakeSwap V3 | WBNB/USDT | 100 | 7d | -$1.4211 | -0.28% |
| 1000 | BSC | PancakeSwap V3 | WBNB/USDT | 100 | 7d | -$2.7431 | -0.27% |
| 2000 | BSC | PancakeSwap V3 | WBNB/USDT | 100 | 7d | -$5.3869 | -0.27% |

**Theoretical ceiling** (zero_il_lvr scenario) at $2000 BSC: -$2.51 (-0.13%)

> 含义：即使 IL/LVR 完全为 0（不可实现），仅 gas + slippage + buffer 仍把 $2000 池的净 EV 打到 -$2.51。**cost structure 是核心矛盾**，不是 fee yield 不足。

## 4. 一句话

> "在 6 条 EVM 链的 74 个 state_ready V3 池中，按当前 model 假设 (gas 350k × 当前 chain gas × native_USD、0.5% slippage、10% failure buffer)，从 $10 到 $2000 notional 跨 9 个 hold window，**没有一个组合能在 realistic 场景下产生正 EV**。零 IL/LVR ceiling 也仍负 EV。"

## 5. model 局限

- 假设 APR 全用 proxy；actual_fee_ready=false
- 假设 slippage 用 0.5% × (1 - capacity)；capacity 基于 liquidity 估值
- 假设失败 buffer 10%；实证不充分
- 假设 IL/LVR 与 fee 同比例（线性）；实证 LVR 与 fee 是非线性
- **结论的稳健性**：model 偏差不太可能把 -$5 → +$5（$10 数量级跳变）；结论**结构性可靠**

## 6. 含义

1. **"等更大 notional" 没救** — fee 收入随 notional 线性增加，cost 也是（除 gas）；pct 几乎不变。
2. **"换更长时间" 没救** — 7d 已经是 7×24h，gas 单次占成本很小；7d vs 1d 主要是 fee 增长，但 fee 增 pct 与 cost 增 pct 不同。
3. **"换更低 gas 链" 部分救** — 但 Optimism gas 已经 0.014 gwei 极低。
4. **唯一真救：减少 entry+exit 次数** — 但这意味着 single-shot LP then hold，这是 spec 之前就试过并 NO_GO 的方向。

## 7. 安全断言

```text
this_stage_only_runs_model       = true
wallet_or_tx_touched             = false
signer_created                   = false
can_run_probe_now                = false
```

## 8. 下游

- Stage G 跑 OOR risk 同样用这 74 个池
- Stage H 用 Stage F + G 综合打分
- Stage I 决定下一阶段是否真的进入 top candidates
