# Next Project Direction — Stage I

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`

## 0. 背景

LP research 当前主线已 `STOP_LP_RESEARCH_NOW` (5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP)。

本文档给出 LP research 收口后 operator 可选的 4 个方向, 帮助决定后续项目走向。

## 1. 4 大方向

### 方向 A: 继续交易系统 (但不做普通 LP)

**前提**: 假设 operator 仍想做 trading。

**A.1 Event-driven / catalyst-driven**
- 监听具体事件 (protocol launch, governance vote, oracle update, large swap, hack)
- 不是被动 LP 持有, 而是主动事件反应
- 短窗口 (分钟 ~ 小时), 不是 days
- 数据源: protocol announcement, twitter, on-chain event listener
- risk: 事件延迟 / 误判; mitigation: 多源 cross-check, paper trade first

**A.2 Spread capture / arbitrage (CEX/DEX)**
- CEX-DEX 价差套利
- cross-DEX 套利 (e.g. Raydium vs Orca)
- triangular 套利 (A → B → C → A)
- 数据源: order book + AMM quotes
- risk: MEV 抢跑, gas fee, slippage; mitigation: private mempool, batch tx, profit > cost check

**A.3 Perps / options 低风险结构**
- 持有 perps 短仓 delta hedge LP
- options 卖 covered call 收 premium + LP
- structured products (Ribbon, Friktion, Friktion-style)
- 数据源: perps dex (Drift, Mango), options (Zeta, Lyra)
- risk: 复杂策略失败模式, liquidation; mitigation: backtest, paper trade, 严格 size limit

**A.4 Incentive / reward farming**
- LP + claim LM rewards (实际 yield 5-10× fee)
- LP + vote-escrow bribe (veRAMM, etc.)
- LP + 协议 emissions
- 数据源: LM contract, bribe marketplace
- risk: emissions 不可持续, bribe 战; mitigation: 历史 emission analysis, 假设 bribe 衰减

**建议优先级**: A.2 (CEX-DEX arb) > A.1 (event-driven) > A.4 (incentive farming) > A.3 (perps/options)

**风险提示**: 任何 trading system 都有 capital risk, 必须从 simulator 起步。

### 方向 B: 继续链上 (但不做交易)

**前提**: 假设 operator 想做链上 infrastructure / tooling。

**B.1 Scanner / dashboard**
- 实时监控 Solana AMM pools
- 报警: high fee pool, low liquidity, suspicious volume
- 数据源: Orca API, Raydium API, GeckoTerminal, Birdeye
- 风险: 数据成本, false alarm
- 价值: 为 trader / researcher 提供工具, 不直接交易

**B.2 Data pipeline**
- 历史 on-chain data 收集 + 清洗
- 标准化: pool 状态, fee accrual, IL realization
- 存储: postgres + timescaledb
- 价值: 任何后续 LP research 的 data foundation

**B.3 Vault / LP monitoring tool**
- 用户指定 LP position, 实时监控
- IL 报警, fee 收集提示
- 收益聚合: 显示总 APY = fee + LM + bribe
- 价值: 帮 LP 用户理解自己 position

**B.4 链上 analytics 报告**
- 周报 / 月报: Solana AMM 趋势
- 公开给 community
- 价值: 建立 thought leadership, 潜在 follow-on project

**建议优先级**: B.2 (data pipeline) > B.1 (scanner) > B.3 (vault monitor) > B.4 (analytics)

**风险提示**: 链上 tooling 是慢 business, 需长期投入, ROI 不直接。

### 方向 C: 回到 Polymarket / 预测市场

**前提**: 假设 operator 想做 prediction market 研究。

**C.1 Polymarket 趋势跟踪**
- 监听 specific event markets
- 收集 historical pricing
- EV model 应用
- 数据源: Polymarket API, UMA oracle

**C.2 预测市场 arbitrage**
- cross-platform prediction market 价差
- polymarket vs 其他市场

**C.3 严格执行研究流程**
- 复用 LP research 的 verdict discipline, artifact index, safety gates
- 避免 LP research 同样的无正 EV live 风险

**建议优先级**: C.3 (复用 LP research 流程) > C.1 (Polymarket 跟踪)

**风险提示**: 预测市场有法律不确定性 (US), LP research 的 safety gates 必须 re-verify

### 方向 D: 停止本仓库

**前提**: 假设 operator 想归档当前项目。

**D.1 归档当前分支**
- 不删除数据
- 保留所有 reports/, tests/, docs/, scripts/
- 标 final tag: e.g. `v3-lp-research-final-20260604`

**D.2 转入其他项目**
- 用 lpbot 的工程 discipline (verdict, safety gates, artifact index) 应用到新项目
- 保留 reusable 模块 (12 个) 作为 reference

**D.3 公开学习材料**
- 发布 LP research 报告到 community
- 让其他 researcher 避免重复 5/5 reject
- 价值: 防止 wasted effort

**建议优先级**: D.1 (归档) > D.3 (公开)

## 2. 决策矩阵

| 方向 | 时间投入 | ROI 周期 | 风险等级 | LP 研究复用度 |
|---|---|---|---|---|
| A. 继续交易 | 中等 | 短-中 | 高 (capital risk) | 中 (复用部分 EV 模型) |
| B. 链上 tooling | 高 | 长 | 低 | 高 (复用 12 个模块) |
| C. 预测市场 | 中等 | 中 | 中 | 中 (复用 verdict discipline) |
| D. 停止归档 | 低 | 立即 | 0 | 0 (archive only) |

## 3. 推荐方向 (per current operator context)

**如果 operator 想保留 active development**:
- **首选**: 方向 B (chain tooling), 具体 B.2 (data pipeline) → B.1 (scanner)
- 理由: 复用 LP research 12 个模块, 投入产出比高, 风险低

**如果 operator 想短期出活**:
- **首选**: 方向 D (archive + public learning material)
- 理由: 立即完成, 0 风险, 公开贡献

**如果 operator 想高风险高回报**:
- **首选**: 方向 A.2 (CEX-DEX arbitrage)
- 理由: 短 ROI, 但需要 capital + MEV 经验

## 4. 严禁的"假重启"

任何方向都必须**禁用**:
- ❌ 直接重启 LP research without 7 重开条件
- ❌ 假设 "改了参数就正 EV"
- ❌ "换个池就 work"
- ❌ "等市场变化就 work"
- ❌ manual operator discretionary "this time different"

LP research 收口是 stable 结论. 5/5 reject 是结构性的, 不是参数问题. 重开必须满足 7 条件 + 完整 read-only → preflight → dry-run → manual approval 流程.

## 5. 重要 caveat

本方向建议**不影响** LP research 收口状态. 即使 operator 选择 D (archive), LP research 仍然 STOP_LP_RESEARCH_NOW. 不会自动重启.

如果 operator 选 B 或 C, lpbot 代码 + 12 个 reusable 模块可用于新方向, 但 LP research 主线仍然 closed.
