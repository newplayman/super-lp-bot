# Current Conclusion Scope — Stage C

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`

## 0. 核心审计字段 (per spec)

```text
global_lp_rejected = false
current_model_rejects_auto_probe = true
conclusion_scope = "current_data_current_model_short_window"
long_term_lp_value_judged = false
```

**关键**: `global_lp_rejected = false`, **不是** "所有 LP 永远没价值"。

## 1. 当前结论**能**证明什么 (CAN prove)

### 1.1 当前自动 LP probe 不应启动

- 5/5 Solana AMM protocols 验证 positive_realistic=0
- 任何 LP research 自动 probe runner 不应启动
- 包括 canary / live / paper / dry-run (auto)
- **manual operator** discretionary trades 仍是可选 (但 out of scope)

### 1.2 当前 10/20U 小资金探针没有足够 EV 支撑

- 5 stages cumulative 28560 EV cells
- 10 USD notional at 25bps × 0.5%/day × 7d = $0.00875 gross
- minus cost $0.006 = $0.00275
- minus IL 0.5% × 7d × $10 = $0.35
- **net = -$0.35** at 7d realistic (heavily negative)

small capital = fee capture 太小, fixed cost 占太大比例. 这是结构性的, 不是 fee 费率问题.

### 1.3 当前模型下 5 类 Solana AMM 都没有 realistic positive

| 协议 | best cell (zero_il_lvr) | positive_realistic |
|---|---|---|
| Meteora DLMM V8 | +$0.544 | 0 |
| Orca Whirlpools V1 | +$0.106 | 0 |
| Raydium CLMM V1 | +$0.167 | 0 |
| Raydium CPMM V1 (AMM v4) | +$0.172 | 0 |
| Solana stable V1 | +$0.204 | 0 |

all 5: 28560 cells, 0 in optimistic/realistic/conservative.

### 1.4 当前 connector 成果可保留

- 12 个 reusable 模块 preserved (EVM V3, BSC, Base, 4 Solana AMM connectors, EV framework, etc.)
- 5 个 LP connector (Meteora DLMM / Orca / Raydium CLMM / Raydium CPMM / stable) 100% SDK decode 走通
- 4 个 mainnet Solana program ids on-chain verified
- safety gates + hard-disable executor 持续 active
- docs / artifacts / tests 全部 preserved

### 1.5 当前需要暂停自动扩协议

- 边际信息价值低 (5/5 AMM 已覆盖)
- 任何 auto protocol switching 立即触发 STOP
- 需满足 7 reopen 条件 (real fee accrual / incentives / etc.) 才能重开
- 重开 ≠ 直接实盘, 仍需 read-only → preflight → dry-run → manual approval

## 2. 当前结论**不能**证明什么 (CANNOT prove)

### 2.1 ❌ 不能证明所有 LP 永久没价值

**为什么不能**:
- 本研究只覆盖 retail 10/20U 2000 USD 范围
- 大资金 (e.g. $1M+ TVL) + professional 做市 + hedging 工具可能仍有正 EV
- 私募 deal / token incentives / bribes (本研究未覆盖) 可能改变 EV
- 新 protocol (e.g. Orca Whirlpools v2) 上线可能改变格局
- EVM (Base, Arbitrum) V3 在不同条件下可能正 EV (本 phase 未跑)

**重要**: `long_term_lp_value_judged = false` (本研究不判断长期 LP 价值).

### 2.2 ❌ 不能证明大资金专业 LP 没价值

**为什么不能**:
- retail 10/20U 2000 USD LP 与 institutional LP 是**不同市场**
- Institutional LP 有 MEV 收入 / bribe / incentive farming 收入
- Institutional LP 有 hedging 工具 (delta-neutral, options, perps)
- Institutional LP 有更低 cost basis (无 rent cost, 折扣 fee tier)
- 5/5 reject 是 retail 模型, 不是 institutional 模型

### 2.3 ❌ 不能证明激励 LP / reward farming 没价值

**为什么不能**:
- 5 stages 全部用 pool.fee_rate 单一收入源
- 协议 LM (liquidity mining) + bribes + IFO rewards 都没纳入
- 一些 protocol 的 LM 实际 yield 是 fee 的 5-10×
- 不同 protocol 的 incentive 模型完全不同
- 需要 separate 7-reopen-condition 验证

### 2.4 ❌ 不能证明 hedge / vault / JIT / active management 没价值

**为什么不能**:
- 5 stages 全部 vanilla LP (持有 → 收 fee → IL)
- 实际专业 LP 用结构性策略: incentive farming, delta-hedged, JIT, single-sided vault, options hedge, MM rebate
- 这些策略的 EV model 完全不同
- 需要 separate 7-reopen-condition 验证

### 2.5 ❌ 不能证明更长周期或不同 market regime 下仍负

**为什么不能**:
- 5 stages 全部 heuristic 0.5%/day turnover (短窗口 proxy)
- 实际 long-horizon (90d / 365d) backtest 缺失
- 不同 market regime (uptrend / downtrend / sideways) 下 fee velocity 差异大
- 下跌环境会提高 IL/LVR proxy (但同时 fee 也可能下降)
- 需要 separate regime split 验证

### 2.6 ❌ 不能证明真实 fee accrual 一定低于 proxy

**为什么不能**:
- 5 stages 全部 heuristic fee model
- 真实 LP position tokenId + actual fee claim history 缺失
- paid RPC / indexer 缺失
- 真实 fee accrual vs proxy 的 bias 未量化
- 需要 actual position-level data 验证

## 3. 结论适用范围的精确 wording

```
本研究的精确结论:

  "在当前短窗口数据 (heuristic 0.5%/day turnover, 4 IL/LVR scenarios),
   当前模型假设 (heuristic fee/cost/IL proxies, no actual position data),
   当前没有真实 LP tokenId / actual fee accrual 的前提下,
   5 类 Solana AMM protocols 全部 negative EV for retail 10/20U 2000 USD LP."

NOT:

  "所有 LP 长期没价值" (NOT proven)
  "大资金专业 LP 没价值" (NOT proven)
  "incentive LP / reward farming 没价值" (NOT proven)
  "hedge / vault / JIT / active management 没价值" (NOT proven)
  "更长周期或不同 regime 下仍负" (NOT proven)
  "真实 fee accrual 一定低于 proxy" (NOT proven)
```

## 4. 关键 audit 字段 (per spec)

```json
{
  "global_lp_rejected": false,
  "current_model_rejects_auto_probe": true,
  "current_probe_allowed": false,
  "conclusion_scope": "current_data_current_model_short_window",
  "long_term_lp_value_judged": false,
  "needs_longer_horizon_validation": true,
  "needs_actual_fee_accrual": true,
  "needs_market_regime_split": true,
  "market_downtrend_bias_acknowledged": true
}
```

## 5. 重要 caveat

本审计**不影响** final freeze 的 5/5 reject 结论. 最终建议仍 `STOP_LP_RESEARCH_NOW` (主 LP research 主线). 但**精确化了**:
- "STOP" 的精确范围 (auto probe only, not all LP forever)
- 7 reopen 条件**包括** longer horizon + actual fee + regime split
- 重开 LP research 必须**先** 满足这些条件, **然后** 再走完整 read-only → preflight → dry-run → manual approval 流程
