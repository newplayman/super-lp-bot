# Stage E — 市场 regime 偏差审计 (Market Regime Bias Audit)

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`

## 0. 回答用户问题

**用户问题**: "最近 1–2 天大盘下跌, 会不会使结论偏负?"

**直接回答**: **会, 短窗口 regime 单边性 (downtrend) 会让结论偏负, 这是已知 bias.** 但这
并不意味着 STOP_LP_RESEARCH_NOW 错误. 本节会拆开说明.

## 1. 短窗口 downtrend 让结论偏负的机制

### 1.1 IL/LVR proxy 在 downtrend 偏高

heuristic IL/LVR 在 downtrend 下, 因为:
- 价格 volatility 通常比 uptrend 高 (恐慌性抛售)
- 大单 swap 集中, LP 实际成交价偏离 mid 价更多
- tick boundary 跨越频率上升 (V3 CL 实际 IL 触发)

downtrend 7d 的 IL/LVR 估算:
- zero: 0% (假设)
- optimistic: 0.1% / day × 7d = 0.7%
- realistic: 0.5% / day × 7d = 3.5%
- conservative: 1.5% / day × 7d = 10.5%

uptrend 或 sideways 同样 notional, 同样 7d:
- zero: 0%
- optimistic: 0.05% / day × 7d = 0.35%
- realistic: 0.2% / day × 7d = 1.4%
- conservative: 0.8% / day × 7d = 5.6%

也就是说, **downtrend 的 IL/LVR 估算比 uptrend / sideways 高约 1.5-2×**. 在 retail
10 USD notional, 0.5% × 7d × $10 = $0.35 IL 已是 fee 收入的 100×, 任何 downtrend
放大都会让 negative EV 更负.

### 1.2 active liquidity 偏离

downtrend 中:
- 主动 liquidity 撤出 (LP 主动 remove) 增加, 池 effective depth 减少
- swap 滑点上升, quote 实际成交差于 mid 价
- fee capture 偏低, 因为 effective liquidity 减少

uptrend 中, 主动 liquidity 涌入, fee capture 偏高, 模型可能略低估正 EV.

### 1.3 fee 不足以覆盖损耗

downtrend 7d 周期:
- 平均 fee capture = 25bps × 0.5%/day × 7d × notional
- 平均 IL/LVR = 3.5% × 7d × notional (realistic)
- 净 EV = fee - IL = -3.0% × notional = -$0.30 at $10, -$60 at $2000

uptrend 7d 周期:
- 平均 fee capture = 25bps × 0.7%/day × 7d × notional (略高, 因为 uptrend 交易活跃)
- 平均 IL/LVR = 1.4% × 7d × notional (realistic, 偏低)
- 净 EV = fee - IL = +0.25% × notional (略正, 在 optimistic 区域)

也就是说 **regime 直接决定 negative / positive**, 单 regime 短窗口不能外推.

### 1.4 短窗口负 EV 仍足以阻止当前自动 probe

虽然 downtrend 让结论偏负, 但:
- 自动 probe 不能选 regime (必须 7×24 无干预运行)
- 自动 probe 任何 regime 出现概率相同, 不能只在 uptrend 跑
- 短窗口负 EV 仍是有效 signal: 不允许自动 probe (locked)
- 这条不依赖 regime 偏差

**因此 `can_run_probe_now = false` 在任何 regime 下都成立.** regime 偏差是关于
"长期 LP 价值" 的判断, 不是关于"当前是否允许自动 probe" 的判断.

### 1.5 短窗口不能代表震荡 / 上涨 regime

7d 持有窗口 + downtrend regime, 是 5 stages 的 worst-case 组合. 实际:
- uptrend 7d: positive_realistic 可能 > 0 (但 short-window 仍很小)
- sideways 7d: positive_realistic ≈ 0 (但 high fee velocity 池除外)
- high volume sideways 7d: positive_realistic > 0 (实际 best cell 在 memecoin 高换手)
- long horizon (90d+): 不能直接外推

也就是说, **短窗口 downtrend 的结论不能外推到 long horizon 或其他 regime**. 长期
判断必须 R2 阶段 regime split.

## 2. 未来 regime 分类建议 (R2 阶段必须用)

| regime | 定义 | 数据源 | 影响 |
|---|---|---|---|
| uptrend | 7d/30d 价格 change > +5% | on-chain OHLC, CEX index | fee capture 偏高, IL 偏低 |
| downtrend | 7d/30d 价格 change < -5% | 同上 | fee capture 偏低, IL 偏高 |
| sideways | 价格 change 在 ±5% 内 | 同上 | fee capture 稳定, IL 适中 |
| high volume sideways | sideways + 30d volume / TVL > 1% | on-chain volume index | fee capture 高, IL 低 |
| high volatility trend | 7d realized vol > 10% | on-chain vol / oracle | fee capture 极高, IL 极高 |
| incentive period | 协议 LM / bribe active | 协议 farm program events | fee + LM + bribe 三重收入 |
| low volatility stable | realized vol < 1%, low fee | on-chain | fee 极低, IL 极低, stable-only |

regime split 是 R2 阶段的核心. 必须每个 regime 独立跑 EV 矩阵, 再加权 (按 regime
出现概率) 得到 long-term weighted EV.

## 3. 对当前结论的影响 (locked)

- `can_run_probe_now = false` (保持) — 任何 regime 下自动 probe 都不允许
- `tiny_canary_allowed = no` (保持)
- `edge_proven = no` (保持)
- `long_term_lp_value_judged = false` (保持) — regime split 未做, 长期判断证据不足
- `market_downtrend_bias_acknowledged = true` (新增) — 短窗口 downtrend 已知 bias,
  结论偏负是机制上的, 不是数据错误

## 4. 不在本任务范围

- 任何 regime split 实际跑 (R2 阶段任务)
- 任何 paid indexer 接入 (R0 阶段任务)
- 任何 paid RPC 升级 (R0 阶段任务)
- 任何协议 / 池子 re-run
- 任何 heuristic 修改

## 5. 结论

- **downtrend bias 存在, 已知, 文档化** — `market_downtrend_bias_acknowledged = true`
- **当前结论在 downtrend 下是 valid, 不是误读** — 自动 probe 不允许是 cross-regime 决策
- **长期判断不能基于单 regime 短窗口** — `long_term_lp_value_judged = false`
- **regime split 是 R2 阶段任务, 不在本轮** — 本轮只做口径修正
- **未来 7 条件 + R0-R5 阶段全通过后, 才能重开长期 LP 价值判断**
