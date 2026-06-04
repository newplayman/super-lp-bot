# Stage D — 模型边界审计 (Model Limitation Audit)

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`

## 0. 目的

把 final freeze 用的 heuristic EV 模型与"实际 LP 收益" 之间的 6 大差距 (gap) 系统化
列出来, 每条都标 high / medium / low 影响, 给出下一阶段必须验证的项.
不重跑任何 protocol, 不修改 heuristic, 不开新数据采集. 本节是只读 audit.

## 1. 6 大边界维度

### 1.1 数据窗口

- **当前覆盖**: 7d 持有窗口是主, 1d / 3d / 14d / 30d 有部分次级
- **缺失覆盖**:
  - 90d / 180d / 365d 长周期数据未跑
  - 跨 regime 数据未拉 (短窗口全部在当前 downtrend 1-2 天)
  - 历史 fee 增长趋势 (TVL 增长 → fee 加速) 没拟合
- **影响评级**: **HIGH** — 短窗口负 EV 不能外推为长周期负 EV
- **下一阶段必须验证**: 7d / 14d / 30d read-only baseline (R0 阶段), 90d / 180d / 365d
  paid indexer (R0 阶段 paid)

### 1.2 fee 数据

- **当前覆盖**: pool.fee_rate (静态, 25bps / 100bps), heuristic 0.5%/day turnover
- **缺失覆盖**:
  - 实际 position-level fee accrual 缺失 (无 tokenId, 无 collect fee 数据)
  - 实际 fee growth inside / outside 当前 tick 范围未拉
  - 动态 fee (Meteora DLMM V8 100bps base + 1000bps max) 实际激活率未观察
  - 7d 中 fee 分布 (前 / 中 / 后) 未拟合
- **影响评级**: **HIGH** — fee 是 LP 唯一收入源, 实际数据缺失导致模型用 100× 上限 proxy,
  实际 fee 可能是 1× 到 0.01× 之间任何值
- **下一阶段必须验证**: actual position tokenId (R1 阶段), 实际 collect fee 数据 (R1),
  dynamic fee activation rate (R1)

### 1.3 成本数据

- **当前覆盖**: fixed_cost = $0.003-0.006 per round-trip, 包含 priority fee + rent + Jito tip
- **缺失覆盖**:
  - 真实 add / remove / collect 操作 cost 拆分 (rent 占比 vs priority fee 占比)
  - 真实 slippage 表现 (10/20U 在低流动性池的滑点)
  - 实际 priority fee (microlamport) 在拥堵期 vs 闲期差异
  - NFT mint / position account close rent (V3 CL) 是否能 skip
  - Tick array init 是否已有 PDA
- **影响评级**: **MEDIUM** — fixed cost 占比 0.06% at $10 notional, 10× 优化空间存在
  (条件 4), 但 retail 10/20U 本质上 cost 占比都偏大
- **下一阶段必须验证**: precise cost breakdown (R0 阶段, R5 阶段 preflight), batch
  transaction design (R0 阶段)

### 1.4 IL / LVR

- **当前覆盖**: heuristic IL/LVR scenarios (zero / optimistic / realistic / conservative)
  4 档
- **缺失覆盖**:
  - 真实 LP 回放 (实际 on-chain position) 缺失, 全部是 model
  - proxy 用 volatility / 7d price change 估算, 不是 on-chain IL
  - LVR (loss-vs-rebalancing) 用 model 估算, 实际 maker/taker flow 拆解未做
  - 下跌行情下 IL/LVR proxy 偏高 (regime bias, 见 Stage E)
  - V3 CL tick boundary IL 实际触发频率未观察
- **影响评级**: **HIGH** — IL/LVR 是 negative EV 的主因, 真实 vs proxy 差距未量化
- **下一阶段必须验证**: 实际 LP 回放 (R1 阶段), regime split (R2 阶段), volatility
  regime 影响 (R2 阶段)

### 1.5 池选择

- **当前覆盖**: GeckoTerminal + DexScreener + Orca official + Meteora UI top
- **缺失覆盖**:
  - 激励池 (LM / LM-bonus / IFO reward) 未纳入
  - vault / managed LP (Meteora DAMM v2 vault, Orca farm vault) 未纳入
  - 私有池 / permissioned LP / OTC LP 全部不在
  - 新上线池 (< 7d) 没历史 fee 数据, 当前 feeder 默认 exclude
  - bribe marketplace 池 (veRAMM 等) 未纳入
- **影响评级**: **HIGH** — pool selection bias 是结构性 gap, 因为"高 yield 池"通常带
  激励 / vault 包装, 公开 feeder 看不到
- **下一阶段必须验证**: incentive / reward / bribe capture (R3 阶段), vault / managed LP
  list (R3 阶段)

### 1.6 资金规模

- **当前覆盖**: 10 / 20 / 100 / 500 / 1000 / 2000 USD notional
- **缺失覆盖**:
  - $10K - $1M 资金规模未跑 (超出模型)
  - 大资金 LP cost 占比 (priority fee / rent) 接近 0, 实际 EV 可能完全不同
  - 专业 MM rebate tier (fee tier 0 / -1 / -2) 未应用
  - 资金规模放大后的 market impact (cap on entry / exit) 未量化
- **影响评级**: **MEDIUM** — 资金规模 1000× 放大后, 0.5%/day turnover 模型可能高估 fee
  capture (因为流动性 depth cap), 也可能低估 (因为 cost 占比趋近 0)
- **下一阶段必须验证**: $10K / $100K / $1M notional sensitivity (R3 阶段, manual), 但**不
  重跑当前 model**

## 2. 边界字段化总结

```json
{
  "limitation_count": 6,
  "high_impact_limitations": [
    "data_window",
    "fee_data",
    "il_lvr",
    "pool_selection"
  ],
  "medium_impact_limitations": [
    "cost_data",
    "capital_scale"
  ],
  "low_impact_limitations": [],
  "conclusion_confidence": "high for current model under current data; low for extrapolation"
}
```

## 3. 下一阶段必须验证 (汇总)

- **R0 阶段** (7d / 14d / 30d read-only baseline): 数据窗口 + cost breakdown + batch tx
- **R1 阶段** (real fee accrual design): position tokenId + collect fee + dynamic fee
  activation rate
- **R2 阶段** (market regime split): regime 分类 (uptrend / downtrend / sideways / 激励
  期 / 低波稳态) + IL/LVR 真实回放
- **R3 阶段** (reopen candidate review): 激励池 / vault / managed LP / 私有池 / bribe
  marketplace 池 list
- **R4 阶段** (10U tokenId probe preflight): 在 R0-R3 全部通过后才能设计 10U tokenId probe
- **R5 阶段** (manual probe only): 不允许自动 probe, 必须 manual operator approval

## 4. 不在本任务范围 (且不会做)

- 任何 protocol 重跑
- 任何 heuristic 改动
- 任何 cost 优化实施
- 任何 paid RPC 接入
- 任何 私有池 / vault 数据采集
- 任何 bribe marketplace 集成
- 任何 backtest 在 90d+ 数据上 (paid indexer 必需)
- 任何 实际 fee accrual 抓取 (需 tokenId, 而 tokenId 需 user 提供)

## 5. 结论

- 6 大边界中 4 个 HIGH (data_window, fee_data, il_lvr, pool_selection)
- 2 个 MEDIUM (cost_data, capital_scale)
- 0 个 LOW
- 当前结论在"current data + current model + short window" 范围内 confidence = high
- 当前结论在"长期 / 大资金 / 激励 / hedge / 长周期" 范围内 confidence = low
- 这正是为什么 `long_term_lp_value_judged = false`
- 任何长期判断必须先通过 R0-R5 6 阶段 (Stage F)
