# Market Regime Bias Audit — Stage E

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`

## 0. 用户的核心问题

> "最近 1–2 天大盘下跌, 会不会使结论偏负?"

**简短答案**: **会**, **部分**. 短窗口 (snapshot at 2026-06-04) 在下跌环境下, IL/LVR proxy 被压高, fee velocity 也可能低. 但**短窗口负 EV 仍足以阻止当前自动 probe** (因为正 EV 路径需要 zero_il_lvr + 高 fee, 而 zero_il_lvr 不现实).

**长期判断**: **不能** 在单一 regime snapshot 下结论. 需要 regime split 才能重开长期判断.

## 1. 下跌环境的具体影响 (5 方面)

### 1.1 IL/LVR proxy 被压高

- 下跌 → pool 内部 price 偏离 active tick → V3 CL position 跨 tick boundary → IL 上升
- 下跌 → 实际无常损失 > heuristic 0.5%/day assumption
- 下跌 → LST (mSOL, jitoSOL) 相对 SOL depeg, LST-stable 池 IL 上升

**impact**: net_ev 更负. heuristic 可能**低估** IL.

### 1.2 Active liquidity 偏离

- 下跌 → active LP 减少 (恐慌 LP 撤资)
- 下跌 → active liquidity 偏低 → quote 滑点 higher
- 下跌 → tick array (V3 CL) / bin array (Meteora DLMM) initialization 受影响

**impact**: 实际 quote 比 heuristic 估计**更差**.

### 1.3 Fee velocity 可能下降

- 下跌 → trader 减少 (套利减少, 投机减少)
- 下跌 → volume 降低 → fee capture 减少
- 下跌 → meme 池 fee 急剧下降 (meme holders 离场)

**impact**: gross fee 减少, net_ev 更负. heuristic 0.5%/day turnover 可能**高估** fee.

### 1.4 下跌环境 ≠ 全市场 regime

- 本研究 snapshot 是**1 天 (2026-06-04)**
- 大盘过去 1-2 天下跌 ≠ 长期趋势
- **震荡** / **上涨** regime 下 fee velocity 完全不同
- 必须 regime split 才能全面判断

**impact**: 单一 regime 结论**外推困难**.

### 1.5 短窗口负 EV 仍足以阻止自动 probe

- 即便下跌环境使结论偏负, 仍**支持 STOP 决策**
- 原因: zero_il_lvr 微正 ($0.10–$0.55) 不代表真实正 EV
- 任何 IL > 0 → 全负
- 下跌环境使 IL > 0 更可能, 所以 STOP 决策**仍 valid**

**impact**: 短窗口结论对"是否继续自动 probe"是**充分**的. 但对"是否长期 negative"是**不充分**的.

## 2. 短窗口负 EV 的 boundary 含义

| 短窗口结论 | 含义 |
|---|---|
| 当前数据 + 当前模型 + 当前 regime 下, retail 10/20U 2000 USD LP 不可行 | ✅ 充分 (支持 STOP) |
| 长期 (90d/365d) 不同 regime 下, retail 10/20U 2000 USD LP 不可行 | ❌ 不充分 (需 regime split) |
| 大资金 / 专业 LP / incentive LP 不可行 | ❌ 不充分 (out of scope) |
| 所有 LP 长期没价值 | ❌ 完全不充分 (out of scope) |

## 3. 未来 regime 分类 (per spec)

按市场行为分类, 给出 7 种典型 regime:

### 3.1 regime 1: uptrend (上涨趋势)
- 特征: 持续 positive price action, volume 上升
- LP 影响: 池 active liquidity 上升, fee velocity 上升, IL 也上升
- 假设: 适合 fee-heavy 高 velocity 池, 不适合低 fee 稳定池
- 重开 LP research 优先级: HIGH (上行 + fee velocity = 可能正 EV)

### 3.2 regime 2: downtrend (下跌趋势)
- 特征: 持续 negative price action, volume 略低
- LP 影响: 池 active liquidity 下降, fee velocity 可能下降, IL 高
- 假设: 不适合 LP 持有 (IL + fee 不够), 适合 delta-hedge 策略
- 重开 LP research 优先级: LOW (本次 snapshot 就是 downtrend, 结论已 reject)

### 3.3 regime 3: sideways (震荡)
- 特征: 价格区间, 无明显 trend
- LP 影响: 池 active liquidity 稳定, fee velocity 取决于 volume
- 假设: 适合 market-making 池, 适合 IL 小的 stable pair
- 重开 LP research 优先级: MEDIUM (sideways 是 LP 最 common regime)

### 3.4 regime 4: high volume sideways (高量震荡)
- 特征: 震荡 + 大量交易
- LP 影响: fee velocity 最高, IL 低 (sideways), **最适合 LP**
- 假设: fee capture 高, IL 接近 0, 应是正 EV 的最佳 regime
- 重开 LP research 优先级: HIGH (如果该 regime 持续, LP EV 可能正)

### 3.5 regime 5: high volatility trend (高波动趋势)
- 特征: 强 trend + 大波动
- LP 影响: fee velocity 高 (volume 高), IL 也高 (price range 跨过)
- 假设: fee/IL 平衡取决于 fee tier
- 重开 LP research 优先级: MEDIUM (fee-heavy 池可能正)

### 3.6 regime 6: incentive period (协议激励期)
- 特征: 协议有 LM 奖励, bribe, IFO 等待
- LP 影响: real yield = fee + LM + bribe, 可能 fee 的 5-10×
- 假设: 必须 actual incentive data, 不是 heuristic fee
- 重开 LP research 优先级: HIGH (如果协议有 active LM, LP 可能正)

### 3.7 regime 7: low volatility stable (低波动稳定)
- 特征: 价格几乎不动 (如 stablecoin pair)
- LP 影响: fee velocity 极低, IL 极低
- 假设: 适合 stable pair 池, 但 fee 必须 > cost (通常不)
- 重开 LP research 优先级: LOW (本研究 stable V1 已 reject)

## 4. regime split 重开 LP research 流程

如果重开 LP research, 必须做 regime split:

```
1. 收集历史 regime 数据 (90d / 365d)
2. 分类每个 regime 的 5 AMM protocols
3. 在每个 regime 下跑 EV model
4. regime 4 (high volume sideways) + regime 6 (incentive period) 是 best case
5. regime 2 (downtrend) + regime 7 (low vol stable) 是 worst case
6. 只有在 best case regime 下 positive_realistic > 0, 才考虑重开
7. worst case regime 必须 re-verify 5/5 reject 仍然 valid
```

## 5. market_downtrend_bias_acknowledged

```text
market_downtrend_bias_acknowledged = True
reason: 本研究 snapshot (2026-06-04) 在 downtrend 环境下, IL/LVR proxy 偏高, fee velocity 可能偏低
implication: 短窗口结论对 "current regime auto probe" 充分, 对 "long-term LP value" 不充分
next_action: regime split 验证 (Stage F long_horizon_reopen_plan)
```

## 6. 重要 caveat

- 下跌 bias **不是** 5/5 reject 结论的弱点. STOP 决策在 downtrend 下**仍 valid**.
- 下跌 bias **是** 长期 LP 价值判断的不充分理由. 重开必须 regime split.
- "市场环境不好 → LP 不行" 是常见误读. 实际上: fee velocity 在 downtrend 可能下降, 但 active liquidity 也在变, 不能简单外推.
- regime split 验证是 Stage F long_horizon_reopen_plan 的核心.

## 7. 结论范围重述

```
本研究的结论, 在 "current data + current model + current regime (downtrend 1-2 天) + retail 10/20U 2000 USD"
条件下, 5/5 Solana AMM 全部 negative EV.

NOT "长期所有 LP 都没价值". 长期判断需要 regime split + actual fee data + larger capital + different strategy.
```
