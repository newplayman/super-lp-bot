# LP Research Conclusion Scope Audit — One-Page Summary

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_053626`
- branch: `feat/supabase-postgres-deployment`
- head_before: `7940cff`

## 关键状态 (user feedback 修正)

```text
status                                = WARN
current_probe_allowed                 = False
global_lp_rejected                     = False  ← 关键: 不等于所有 LP 永久没价值
current_model_rejects_auto_probe      = True
conclusion_scope                      = current_data_current_model_short_window
long_term_lp_value_judged             = False  ← 关键: 长期 LP 价值未判断
needs_longer_horizon_validation       = True
needs_actual_fee_accrual              = True
needs_market_regime_split             = True
market_downtrend_bias_acknowledged   = True
can_run_probe_now                     = False
tiny_canary_allowed                  = no
edge_proven                           = no
recommended_next_stage                = PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA
```

## 重要: 精确结论口径 (per user concern)

```
本研究 CAN prove:
  1. 当前自动 LP probe 不应启动
  2. 当前 10/20U 小资金探针没有足够 EV 支撑
  3. 当前模型下 5 类 Solana AMM 都没有 realistic positive
  4. 当前 connector 成果可保留
  5. 当前需要暂停自动扩协议

本研究 CANNOT prove:
  ❌ 所有 LP 永久没价值
  ❌ 大资金专业 LP 没价值
  ❌ 激励 LP / reward farming 没价值
  ❌ Hedge / vault / JIT / active management 没价值
  ❌ 更长周期或不同 market regime 下仍负
  ❌ 真实 fee accrual 一定低于 proxy

精确 wording:
  "在当前短窗口数据 (heuristic 0.5%/day turnover, 4 IL/LVR scenarios),
   当前模型假设 (heuristic fee/cost/IL proxies, no actual position data),
   当前没有真实 LP tokenId / actual fee accrual 的前提下,
   5 类 Solana AMM protocols 全部 negative EV for retail 10/20U 2000 USD LP."
```

## Market regime 偏差审计 (per user question)

**用户问题**: "最近 1–2 天大盘下跌, 会不会使结论偏负?"

**答案**: **会 (部分)**.
- 短窗口 snapshot (2026-06-04) 在 downtrend 环境下, IL/LVR proxy 偏高, fee velocity 可能偏低
- 短窗口负 EV **仍足以阻止当前自动 probe** (因为正 EV 路径需要 zero_il_lvr + 高 fee, 而 zero_il_lvr 不现实)
- **长期判断需要 regime split**, 不能在单一 regime snapshot 下结论

**7 regime 分类**:
- uptrend: HIGH (上行 + fee velocity = 可能正 EV)
- downtrend: LOW (本次 snapshot, 结论已 reject)
- sideways: MEDIUM
- **high_volume_sideways: HIGH (best case for LP)**
- high_volatility_trend: MEDIUM
- **incentive_period: HIGH (active LM 时)**
- low_volatility_stable: LOW (本研究 stable V1 已 reject)

## Model 限制审计 (6 大限制, 3 HIGH impact)

| # | 限制 | Impact | verification plan |
|---|---|---|---|
| 1 | 数据窗口 (短窗口, 无 regime split) | **HIGH** | 7d/14d/30d/90d/365d backtest + regime split |
| 2 | fee 数据 (heuristic, no actual) | **HIGH** | user LP tokenId + 历史 fee claim |
| 3 | 成本数据 (fixed assumption) | MEDIUM | on-chain tx cost from past LP |
| 4 | IL/LVR (heuristic, proxy) | **HIGH** | actual LP replay + historical price |
| 5 | 池选择 (public only) | MEDIUM | 激励池 / vault / bribe coverage |
| 6 | 资金规模 (retail only) | MEDIUM | simulate 不同 capital |

**conclusion_confidence**:
- applicable_to_current_short_window_retail_model: **MEDIUM** (5 stages converge)
- applicable_to_long_horizon: **NONE** (out of scope)
- applicable_to_different_market_regime: **LOW** (only current regime tested)

## Long Horizon Reopen Plan (6 阶段 R0-R5)

```
PHASE_R0_LONG_READONLY_DATA            (2-4 weeks)
PHASE_R1_REAL_FEE_ACCRUAL_DESIGN       (1-2 weeks)
PHASE_R2_MARKET_REGIME_SPLIT           (2-4 weeks)
PHASE_R3_REOPEN_CANDIDATE_REVIEW       (1-2 weeks)
PHASE_R4_10U_TOKENID_PROBE_PREFLIGHT   (1 week)
PHASE_R5_MANUAL_PROBE_ONLY             (持续)

总时间: 7-13 周 to reach first manual probe
总成本: $500-$5000 USD 级别
```

**重要**: 即使按 6 阶段走完, 仍可能 STOP 多次. 6 阶段不能跳过, 不能并联, 不能 modify.

## Safety 继承

- can_run_probe_now = **false** (locked)
- tiny_canary_allowed = **no** (locked)
- edge_proven = **no** (locked)
- send_hard_disable_still_active = **true**
- wallet_or_tx_touched = **false**
- solana_wallet_or_keypair_touched = **false**
- transaction_sent = **false**
- v2_line_count = 992 (unchanged)

## 关键 artifact paths

- `reports/lp_research_conclusion_scope_audit/20260604_053626/FINAL_VERDICT.json` (本 verdict)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/ONEPAGE_CN.md` (本页)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/ARTIFACT_INDEX.md` (artifact 索引)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/CURRENT_CONCLUSION_SCOPE_CN.md` (Stage C)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/MODEL_LIMITATION_AUDIT_CN.md` (Stage D)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/MARKET_REGIME_BIAS_AUDIT_CN.md` (Stage E)
- `reports/lp_research_conclusion_scope_audit/20260604_053626/LONG_HORIZON_REOPEN_PLAN_CN.md` (Stage F)
- `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` (历史 final freeze)
- `docs/LPBOT_RESEARCH_STATUS_CN.md` (updated with scope)
- `README.md` (updated with scope)

## 重要 caveat

- 本审计**不改变** final freeze 的 5/5 reject 结论. STOP_LP_RESEARCH_NOW 仍 valid (auto probe only).
- 本审计**精确化** 结论范围: "short window + current model + current regime + retail 10/20U" 而非 "all LP forever".
- 长期 LP 价值判断需要 regime split + actual fee data, 本研究**不** 判断.
- 6 阶段 reopen plan 是**操作化** 7-reopen-conditions, 不是 reopen decision. 即使走完, 仍可能 STOP.
