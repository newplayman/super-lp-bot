# LPBOT 研究状态

> **2026-06-04 UPDATE — LP Research Conclusion Scope Audit (口径修正)**
>
> 当前状态: **`STOP_LP_RESEARCH_NOW`** (LP research 主线收口)
>
> - **can_run_probe_now = `false`**
> - **tiny_canary_allowed = `no`**
> - **edge_proven = `no`**
>
> **重要: 结论口径** (per `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`, 2026-06-04 060659)
>
> 当前结论 **不等于 global LP rejected**:
>
> - **`global_lp_rejected = false`** — 没有任何结论说"所有 LP 永久没价值"
> - **`long_term_lp_value_judged = false`** — 长期价值本任务没判定
> - **`conclusion_scope = current_data_current_model_short_window`** — 结论的精确范围
> - **结论只表示**: 在当前短窗口数据 + 当前模型 + 当前 regime (downtrend 1-2 天) +
>   retail 10/20U 2000 USD 条件下, 5/5 Solana AMM protocols 全部 negative EV
>
> 当前数据 / 模型 / regime **不足以**判断:
>
> - 大资金 / 专业 LP / institutional
> - 激励 LP / reward farming / LM / bribe
> - Hedge / vault / JIT / active management / covered call
> - 长期 (>30d) 跨 regime 验证
> - 真实 fee accrual vs heuristic proxy
> - EVM V3 LP (Base / Arbitrum / BSC) / 新上线 protocol
>
> 重开 LP research 需满足 (按顺序, 详见 `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md`):
>
> - 7-reopen-condition 全部满足 (Stage F 7 类)
> - 6 阶段 R0-R5 全部 PASS (任一 STOP → 不再继续)
> - **`needs_longer_horizon_validation = true`**
> - **`needs_actual_fee_accrual = true`**
> - **`needs_market_regime_split = true`**
> - **`market_downtrend_bias_acknowledged = true`**
>
> Current Status Documents:
>
> - Final Freeze date: 2026-06-04
> - Final Freeze run_id: `20260604_051254`
> - Final Freeze report: `reports/lp_research_final_freeze/20260604_051254/`
> - Conclusion Scope Audit run_id: `20260604_060659`
> - Conclusion Scope Audit report: `reports/lp_research_conclusion_scope_audit/20260604_060659/`
> - **5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP** (cumulative 28560 EV cells, best $0.544 in zero_il_lvr only)

历史状态: `LP strategy research frozen` (2026-05-31 final freeze)

- final freeze report path: `reports/final_freeze/20260531_124000/FINAL_VERDICT.json`
- edge_proven = `no`
- tiny_canary_allowed = `no`
- current_full_strategy = `FAIL`
- fixed_horizon = `STOP`
- intent_lifecycle = `STOP`
- Tier B = `PAUSE`
- Tier C = `BATCH_REJECTED`
- risk-aware short-hold = `STOP`
- pool-regime-aware = `STOP`
- fee-velocity / exit-depth = `STOP`
- next recommended action = `STOP_LP_RESEARCH_NOW`

---

## 2026-06-04 LP Research Final Freeze 总结

### 累计 5 LP research stages (5/5 reject)

| Stage | RUN_ID | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | 20260604_021913 | +$0.544 | 0 | DLMM (V3-class), 25-100bps dynamic fee |
| Orca Whirlpools V1 | 20260604_025414 | +$0.106 | 0 | V3 CL, lazy tick array |
| Raydium CLMM V1 | 20260604_034503 | +$0.167 | 0 | V3 CL, lazy tick array |
| Raydium CPMM V1 (AMM v4) | 20260604_040952 | +$0.172 | 0 | constant product, 25bps |
| Solana stable V1 | 20260604_044118 | +$0.204 | 0 | LST-stable, 1-30bps |

**共同结论**: 5/5 Solana AMM protocols 全部 reject retail 10-20U 2000 USD LP. 累计 28560 EV cells, 0 in optimistic/realistic/conservative scenarios, only 1898 in zero_il_lvr heuristic.

### Final Freeze Artifacts (关键路径)

- `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` (LP research final freeze verdict)
- `reports/lp_research_final_freeze/20260604_051254/ONEPAGE_CN.md` (LP research final freeze one-pager)
- `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_FINAL_FREEZE_MATRIX_CN.md` (7 protocols 累计矩阵)
- `reports/lp_research_final_freeze/20260604_051254/WHY_STOP_LP_RESEARCH_NOW_CN.md` (大白话 9 reasons)
- `reports/lp_research_final_freeze/20260604_051254/WHAT_THIS_DOES_NOT_MEAN_CN.md` (6 常见误解)
- `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md` (7 条件重开钥匙)
- `reports/lp_research_final_freeze/20260604_051254/REUSABLE_ARTIFACTS_AND_MODULES_CN.md` (12 复用模块)
- `reports/lp_research_final_freeze/20260604_051254/NEXT_PROJECT_DIRECTION_CN.md` (后续方向)

### Conclusion Scope Audit Artifacts (本阶段新增, 060659)

- `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json` (口径修正 verdict)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/ONEPAGE_CN.md` (口径修正 one-pager)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/CURRENT_CONCLUSION_SCOPE_CN.md` (结论适用范围)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/MODEL_LIMITATION_AUDIT_CN.md` (模型边界 6 维度)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/MARKET_REGIME_BIAS_AUDIT_CN.md` (regime 偏差)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md` (R0-R5 6 阶段)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/INPUT_EVIDENCE_AUDIT_CN.md` (输入证据)

### Reopen Conditions (摘要)

重开 LP research 需满足 7 大类条件 (详细见 Final Freeze):
1. 真实 fee accrual / actual position tokenId 数据
2. 协议激励 / external rewards / bribe
3. 稳定高 fee velocity 池
4. 更低成本链路
5. paid RPC / indexer 支撑更完整数据
6. 用户主动提供具体池 / 资金 / 策略假设
7. 非普通 LP 的结构性策略 (incentive farming, delta-hedged, JIT, etc.)

即使 7 条件满足, 仍需走 R0 → R1 → R2 → R3 → R4 → R5 6 阶段 read-only 路径 + manual approval 全流程。

### 警示

- 当前不得运行 live / canary / paper。
- 当前不得把任何研究结论转成 micro-live。
- 当前只允许阅读历史报告、补文档、做工程清理。
- `docs/runbooks/base-canary-ops.md`、`docs/runbooks/vps-shadow-deployment.md`、`scripts/canary_cycle.sh` 等历史入口仅作归档保留，不代表当前允许执行。
- `internal/core/execution/hard-disable` 仍 active, 不释放。
- 任何重开 LP research 必须先读 R0-R5 6 阶段计划, 任一阶段失败 → STOP, 不允许跳过。

如果未来重启 LP research, 先读:
- `reports/lp_research_conclusion_scope_audit/20260604_060659/ONEPAGE_CN.md`
- `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md`
- `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md`
- `reports/lp_research_final_freeze/20260604_051254/NEXT_PROJECT_DIRECTION_CN.md`

历史 reopen 文档:
- `/Users/bendu/lp/bot/v3/reports/final_freeze/20260531_124000/LPBOT_FINAL_ONEPAGE_CN.md`
- `/Users/bendu/lp/bot/v3/reports/final_freeze/20260531_124000/REOPEN_CONDITIONS_CN.md`
- `/Users/bendu/lp/bot/v3/reports/final_freeze/20260531_124000/NEXT_PROJECT_OPTIONS_CN.md`

## LP Scale Economics Addendum

- scale economics 重开题已完成，且已走完整条只读验证链。
