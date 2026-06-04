# Model Limitation Audit — Stage D

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`

## 0. 6 大模型限制 (per spec)

5 stages 累计 28560 EV cells 全部基于 heuristic model. 任何结论的 confidence 受这些限制约束. 本文档审计 6 大限制, 给出 conclusion_confidence 和 what_must_be_verified_next.

## 1. 6 大限制 (with impact + verification plan)

### 1.1 限制 1: 数据窗口 (HIGH impact)

**问题**:
- 5 stages 全部 heuristic 0.5%/day turnover, 实际是单窗口 proxy
- **未覆盖 7d 短窗口之外的周期** (14d / 30d / 90d / 365d backtest 缺失)
- **未覆盖不同 market regime** (uptrend / downtrend / sideways / high volatility)
- 5 stages 时间窗: Meteora 2026-06-04, Orca 2026-06-04, Raydium CLMM 2026-06-04, Raydium CPMM 2026-06-04, Stable 2026-06-04, **全部是同日 snapshot**
- 大盘**最近 1–2 天明显下跌** (BTC/ETH/SOL 都跌 5–10%): 短窗口 snapshot 在下跌环境下 IL/LVR proxy 被压高
- 下跌环境 fee velocity 可能也低 (投机 fee 减少, 套利 fee 减少)

**impact**: HIGH. 不同 regime 下结论可能完全不同. 当前结论仅适用**短窗口 + 当前特定 market state**.

**verification plan**:
- 7d / 14d / 30d / 90d / 365d 历史 backtest
- regime split: uptrend / downtrend / sideways
- regime-specific IL/LVR 模型
- cross-regime 比较

### 1.2 限制 2: fee 数据 (HIGH impact)

**问题**:
- 5 stages 全部 heuristic fee model, **不是 actual fee accrual**
- 真实 LP position tokenId (NFT for Orca, mint for Raydium) 缺失
- 实际 collect fee 真实数据 缺失
- 只能 heuristic proxy 推算 fee capture

**impact**: HIGH. Heuristic fee model 可能与 actual fee accrual 有 system bias. 例如:
- Heuristic 0.5%/day turnover × 25bps fee = $1.25/day on $1000 notional
- 实际 0.05%/day turnover × 25bps = $0.125/day (10× less)
- 或 实际 1.5%/day turnover × 25bps = $3.75/day (3× more)
- 没有实际 data 验证 direction / magnitude of bias

**verification plan**:
- user 提供具体 LP position tokenId
- 历史 collect fee 数据 from chain
- 实际 LP lifetime + fee capture ratio
- paid RPC / indexer for historical query

### 1.3 限制 3: 成本数据 (MEDIUM impact)

**问题**:
- 5 stages 全部用 fixed cost assumption ($0.003-0.006 per round-trip)
- **未真实 add/remove/collect** on chain
- **未真实 slippage** (用 quote-derived price impact 近似)
- **未真实 priority fee** (用 10k microlamports = 0.00001 SOL 假设)
- AMM v4 cost = $0.003, CLMM cost = $0.006, stable cost = $0.008 全部 heuristic

**impact**: MEDIUM. Cost 是 1 次交易 (open + close) 的关键 cost 项. Heuristic cost 可能高估或低估 1.5-2×. 但 cost 在 2000 USD notional 上 = 0.0015%, 影响 < 0.5% EV.

**verification plan**:
- actual tx cost data from past LP operations
- 实际 priority fee paid (from on-chain tx logs)
- 实际 slippage vs quote impact 比较

### 1.4 限制 4: IL/LVR (HIGH impact)

**问题**:
- 5 stages 全部 heuristic IL/LVR (0% / 0.1% / 0.5% / 2% per day)
- **未真实 LP 回放** (no actual position historical)
- IL/LVR 是 proxy, 不是 measured
- **可能对下跌行情偏保守** (downturn → higher IL/LVR → more conservative net_ev)
- V3 CL 的 IL/LVR 在 price range 跨过时更严重
- Constant product 100% IL on any price change
- LST-stable 也有 LST depeg 0.01-0.1%/day

**impact**: HIGH. IL/LVR 是 net EV 主要 negative component. Heuristic 假设可能:
- 实际 worse (downturn + low fee)
- 实际 better (upturn + high fee velocity)

**verification plan**:
- 实际 LP position 回放 (with user tokenId)
- historical IL/LVR simulation with real price paths
- regime-specific IL/LVR 模型

### 1.5 限制 5: 池选择 (MEDIUM impact)

**问题**:
- 5 stages 全部用公开 API (Orca, GeckoTerminal, DexScreener) 找池
- **未覆盖激励池** (incentive LM 池, 通常 hidden from public API)
- **未覆盖 vault / managed LP** (e.g. Kamino, Tulip vaults)
- **未覆盖 bribe 池** (veRAMM-style bribe marketplaces)
- **未覆盖 IDO / launch pool** (new pool high fee transient)
- 实际 LP research 候选池数是公开池的 2-5× (估计)

**impact**: MEDIUM. 公开池 ≠ 全池. 一些 incentive-heavy pool 可能 positive EV 但本研究未覆盖. 但公开池 negative 已足够说明"vanilla LP 不可行".

**verification plan**:
- 邀请 LP 池 (Kamino, Marinade, Tulip vaults) 数据
- bribe marketplace 集成
- IDO / launch pool tracker
- 实际激励池 candidate list

### 1.6 限制 6: 资金规模 (MEDIUM impact)

**问题**:
- 5 stages 全部用 retail 10/20U 2000 USD 模型
- **未覆盖大资金专业 LP** ($100K+ / $1M+ TVL)
- 大资金 LP cost basis 更低 (无 rent, 折扣 fee tier)
- 大资金 LP 有 MEV 收入 / rebate / incentive 收入
- 大资金 LP 可 hire quant team 设计 strategy

**impact**: MEDIUM. retail 模型 negative, 不代表大资金 negative. 但本研究目标是 retail 模型, 大资金模型 out of scope.

**verification plan**:
- 大资金 EV model (different cost basis + MEV + rebate)
- institutional LP case study
- 资金 vs cost sensitivity analysis

## 2. 综合 assessment

| 限制 | Impact | verification_difficulty |
|---|---|---|
| 1. 数据窗口 | HIGH | MEDIUM (paid RPC + indexer) |
| 2. fee 数据 | HIGH | HIGH (需要 user LP tokenId + 历史 data) |
| 3. 成本数据 | MEDIUM | LOW (on-chain tx logs) |
| 4. IL/LVR | HIGH | MEDIUM (需要 user LP + 历史 price) |
| 5. 池选择 | MEDIUM | MEDIUM (需要 incentive 池数据) |
| 6. 资金规模 | MEDIUM | LOW (simulate 不同 capital) |

limitation_count = 6
high_impact_limitations = 3 (数据窗口, fee 数据, IL/LVR)

## 3. conclusion_confidence

- **不适用** 所有 6 大限制的 LP 模型 confidence = LOW
- **不适用** 大资金 / professional LP 的 confidence = NONE (out of scope)
- **不适用** 长期 (>30d) 验证的 confidence = NONE
- **不适用** 不同 market regime 的 confidence = LOW (only current regime tested)
- **适用** 当前短窗口 + retail 模型 + heuristic proxies 的 confidence = MEDIUM (5 stages converge)

**recommendation**: 在以上限制下, "5/5 reject" 结论的 confidence = MEDIUM. 重开 LP research 必须**先** 解决 6 大限制, **再** 跑新 EV model.

## 4. what_must_be_verified_next

按 priority 排序:

### P0 (必须)
- (1) 数据窗口: 7d/14d/30d/90d/365d historical backtest with regime split
- (2) IL/LVR: 实际 LP position 回放 (with user tokenId) + historical price paths
- (4) fee 数据: actual fee claim history (with user LP tokenId)

### P1 (重要)
- (3) 成本数据: actual on-chain tx cost from past LP operations
- (5) 池选择: 激励池 / vault / bribe pool 覆盖

### P2 (nice to have)
- (6) 资金规模: simulate 不同 capital (100K / 1M) with different cost basis

## 5. 重要 caveat

- 6 大限制**不否定** 5/5 reject 结论. 即使 confidence 是 MEDIUM, 仍支持 "vanilla LP 在 retail 10/20U 2000 USD 不可行".
- 6 大限制**不打开** 立即重启 LP research 的门. 重开必须**先** 解决所有 HIGH impact 限制.
- 任何 "lower the limit → see positive" 的尝试**不通过** 此 audit. 限制是结构性的, 不是参数问题.
