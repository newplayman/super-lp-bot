# Long Horizon Reopen Plan — Stage F

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`

## 0. 6 阶段 (R0-R5) reopen plan

如果未来要重开 LP research, 必须按顺序走完 6 阶段. 任何阶段失败 → 停止 + 重新评估.

**关键**: 重开 ≠ 直接实盘. 重开 = 重新启动 LP research 的**前提**, 不是终点.

## 1. PHASE_R0_LONG_READONLY_DATA (基础数据收集)

**目标**: 收集 7d / 14d / 30d / 90d / 365d 历史 read-only data, 解决 Stage D 限制 1 (数据窗口).

**任务**:
- 7d / 14d / 30d / 90d / 365d 时间窗
- 收集 5 个 Solana AMM protocols 的 池 metadata + 历史 fee 数据
- 历史 regime 分类 (uptrend / downtrend / sideways / high_vol_sideways / high_vol_trend / incentive / low_vol_stable)
- 真实 volume + TVL 历史

**数据源**:
- paid RPC (Helius / Triton / QuickNode) for historical queries
- Birdeye / DexScreener API for 历史 metadata
- 历史 indexer (Shyft, helloMoon) for backtest
- GeckoTerminal 历史 pool data

**outcome**:
- 5 AMM × 7 regime × 5 timeframe = **175 cells of data**
- 每个 cell: pool_address, tvl, vol, fee, il_realized
- 数据集 >= 1 GB, postgres / timescaledb

**success criteria**:
- 5/5 protocols 数据覆盖率 >= 80%
- 5/5 regime 全部有 30d+ 数据
- 任何 regime 缺失 → 重新收集

**failure handling**:
- 数据缺失 → 回到 Phase R0 重新设计
- 不应跳过到下一阶段

## 2. PHASE_R1_REAL_FEE_ACCRUAL_DESIGN (真实 fee 数据)

**目标**: 获取 actual LP position tokenId + 历史 fee claim data, 解决 Stage D 限制 2 (fee 数据).

**任务**:
- 找 user-held LP position (Orca NFT, Raydium position mint)
- 获取 position 历史 fee claim data
- 实际 fee vs heuristic fee 比较
- 不同 regime 下 fee capture ratio

**数据源**:
- user-held LP tokenId
- paid RPC for historical position queries
- 历史 fee claim events (Orca `collectFees`, Raydium `decreaseLiquidity` 部分)
- 第三方 fee tracker (Bifrost, Step Finance)

**outcome**:
- 实际 fee capture / heuristic fee 比例 (per regime)
- 真实 LP lifetime fee 数据
- 5 AMM × 7 regime 的 actual fee proxy

**success criteria**:
- 至少 50 个 user LP position 分析
- actual fee vs heuristic fee 比 ratio 量化
- regime-specific fee capture 量化

**failure handling**:
- user 不提供 LP tokenId → 重新 invite user
- paid RPC 数据缺失 → 重新设计 data pipeline

## 3. PHASE_R2_MARKET_REGIME_SPLIT (regime split)

**目标**: 把 R0 + R1 数据按 regime 分类, 解决 Stage E 用户问题.

**任务**:
- 90d / 365d 历史 regime 分类 (用 price + volume data)
- 7 regime × 5 AMM × 5 timeframe EV 重新跑
- regime-specific best cell 重新计算
- regime 4 (high volume sideways) + regime 6 (incentive period) 重点

**数据源**:
- R0 收集的 historical pool data
- R1 收集的 actual fee data
- BTC/ETH/SOL 价格 + volume 历史 (CoinGecko, CoinMarketCap)

**outcome**:
- 5 AMM × 7 regime × 5 timeframe = **175 EV cells per regime scenario**
- regime-specific best cell
- regime-specific positive_realistic count
- regime-specific verdict

**success criteria**:
- 5 AMM × 7 regime 全部有 EV data
- 至少 1 regime 出现 positive_realistic > 0 → continue to R3
- 全部 0 positive_realistic → STOP again, return to STOP_LP_RESEARCH_NOW

**failure handling**:
- 全部 0 → 重新审视 heuristic, 考虑**永久 STOP**

## 4. PHASE_R3_REOPEN_CANDIDATE_REVIEW (重开候选评审)

**目标**: 评审 R2 发现的 positive candidate, 决定是否继续重开 LP research.

**任务**:
- R2 发现的 positive_realistic > 0 candidate 详细分析
- 候选池 incentive 数据 (LM + bribe) 调查
- 候选池用户 specific 假设 (capital, risk, time horizon)
- 非 vanilla LP 策略考虑 (incentive farming, delta-hedged, JIT)

**决策**:
- 候选 pools 都 invalid → STOP again, return to STOP_LP_RESEARCH_NOW
- 候选 pools 有效 → continue to R4

**success criteria**:
- 至少 1 pool 通过 7-reopen-condition 验证
- 候选 pool 的 incentive data 真实 (不是 heuristic)
- 候选 pool 的 cost / benefit 实际计算

**failure handling**:
- 全部 invalid → STOP, 不重开
- 部分 valid → 设计新 LP research phase 验证

## 5. PHASE_R4_10U_TOKENID_PROBE_PREFLIGHT (10U tokenId probe preflight)

**目标**: 为重开 LP research 设计 10U tokenId probe, 仅 read-only, 不发.

**任务**:
- 选择具体 tokenId (user LP position)
- 设计 probe 时间窗 (e.g. 1d / 7d / 30d)
- 实际 fee / IL 测量 protocol
- cost / benefit 实际计算
- dry-run tx 仿真 (read-only)

**数据源**:
- R3 候选 pool + user LP position
- paid RPC for simulation
- simulateTransaction (无实际 send)

**outcome**:
- 10U probe design (read-only dry-run)
- 实际 cost 估算
- 实际 expected fee 估算
- 实际 expected IL 估算
- 实际 net EV 估算 (含 actual fee + actual cost + actual IL)

**success criteria**:
- design 通过 review (manual operator approval)
- expected net EV > 0 in actual model
- cost 占比 < 1% of notional

**failure handling**:
- expected net EV < 0 → 回到 R3 调整
- cost 占比 > 5% → 重新设计

## 6. PHASE_R5_MANUAL_PROBE_ONLY (manual probe only)

**目标**: 在 R4 通过的 candidate 上, 真正做 manual probe (operator discretionary, not auto).

**任务**:
- operator 手动操作 (不是 auto runner)
- 严格 7-reopen-condition 验证
- 严格 read-only → preflight → dry-run → manual approval 流程
- 1 tx at a time, manual sign
- 实时监控 + manual stop

**outcome**:
- 第一次 manual probe 实际数据
- 实际 fee / IL / cost 对比 R4 design
- 风险实时跟踪

**success criteria**:
- 第一次 probe net EV > 0
- cost / benefit 实际符合 R4 design
- 风险指标 (IL, slippage) 在预期范围

**failure handling**:
- 第一次 probe < 0 → STOP manual probe, 回到 R3 重新评估
- 多次失败 → 考虑**永久 STOP**, 整个 LP research 收口

## 7. 流程时间估算

- PHASE_R0: 2-4 周
- PHASE_R1: 1-2 周
- PHASE_R2: 2-4 周
- PHASE_R3: 1-2 周
- PHASE_R4: 1 周
- PHASE_R5: 持续

**总时间**: 7-13 周 to reach first manual probe, 不保证正 EV.

## 8. 重要 caveat

- 这只是 reopen plan, **不是 reopen decision**. 即使按 6 阶段走完, 仍可能 STOP 多次.
- 6 阶段任何一个失败 → 回到 STOP, 不强行继续.
- 重开 ≠ 直接实盘, 仍需 read-only → preflight → dry-run → manual approval.
- 6 阶段不能跳过, 不能并联, 不能 modify.
- 任何 "let me skip to R5 with 10 USD probe" 的尝试**不通过** 此 plan.
- 重开累计成本: 7-13 周 + paid RPC + 历史 data, 估算 $500-$5000 USD 级别.

## 9. 与 7-reopen-conditions 的关系

6 阶段 = 7-reopen-conditions 的**操作化**:
- 7-reopen-condition #1 (real fee accrual) → PHASE_R0 + R1
- 7-reopen-condition #2 (incentives) → PHASE_R0 + R1 + R3
- 7-reopen-condition #3 (high fee velocity pool) → PHASE_R0 + R2
- 7-reopen-condition #4 (lower cost link) → PHASE_R0 + R4
- 7-reopen-condition #5 (paid RPC) → PHASE_R0
- 7-reopen-condition #6 (user-specific) → PHASE_R3 + R4
- 7-reopen-condition #7 (non-standard strategy) → PHASE_R3 + R4
