# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `7940cff research: final freeze lp research 20260604_051254`

## 0. 目的

在"修正结论口径"之前, 把上一阶段 final freeze 留下的 7 份权威文档 + 5 个 protocol verdict
逐条 read-back 验证. 任何字段缺失或矛盾, 本阶段就报告并停止. 没有缺失则继续.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | FINAL_VERDICT.json (final freeze) | `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` | ✅ read | status=WARN, research_freeze_complete=true, overall_recommendation=STOP_LP_RESEARCH_NOW, edge_proven=no, can_run_probe_now=false, tiny_canary_allowed=no, positive_realistic_any_protocol=false, positive_optimistic_any_protocol=false, positive_conservative_any_protocol=false, zero_il_lvr_positive_only=true, protocols_frozen=5, reopen_conditions_documented=true, docs_updated=true, wallet_or_tx_touched=false, solana_wallet_or_keypair_touched=false, transaction_sent=false, send_hard_disable_still_active=true, recommended_next_stage=STOP_LP_RESEARCH_NOW |
| 2 | WHY_STOP_LP_RESEARCH_NOW_CN.md | `reports/lp_research_final_freeze/20260604_051254/WHY_STOP_LP_RESEARCH_NOW_CN.md` | ✅ read | 9 大原因, 累计 28560 cells, 5/5 reject 表格, 5 stages 总投入汇总 |
| 3 | LP_RESEARCH_REOPEN_CONDITIONS_CN.md | `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md` | ✅ read | 7 大重开条件 + 11 项 checklist + 重开流程 |
| 4 | WHAT_THIS_DOES_NOT_MEAN_CN.md | `reports/lp_research_final_freeze/20260604_051254/WHAT_THIS_DOES_NOT_MEAN_CN.md` | ✅ read | 6 大常见误解 (NOT means) |
| 5 | docs/LPBOT_RESEARCH_STATUS_CN.md | `docs/LPBOT_RESEARCH_STATUS_CN.md` | ✅ read | 含 stage A-H 全套, 7 重开条件, 警示 |
| 6 | docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md | `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md` | ✅ read | 含 final freeze + 5 protocol 索引 |
| 7 | README.md | `README.md` | ✅ read | Current Research Status 段已冻结指针 |

### 5 个 protocol verdict

| # | protocol | run_id | verdict | can_run_probe | positive_realistic | best_cell_usd | tx_sent |
|---|---|---|---|---|---|---|---|
| 1 | Meteora DLMM V8 | 20260604_021913 | WARN / REJECT | false | 0 | +$0.544 (zero_il_lvr) | false |
| 2 | Orca Whirlpools V1 | 20260604_025414 | WARN / REJECT | false | 0 | +$0.106 (zero_il_lvr) | false |
| 3 | Raydium CLMM V1 | 20260604_034503 | WARN / REJECT | false | 0 | +$0.167 (zero_il_lvr) | false |
| 4 | Raydium CPMM V1 (AMM v4) | 20260604_040952 | WARN / REJECT | false | 0 | +$0.172 (zero_il_lvr) | false |
| 5 | Solana stable (Meteora/Orca LST) | 20260604_044118 | WARN / REJECT | false | 0 | +$0.204 (zero_il_lvr) | false |

5/5 protocol 一致:
- positive_realistic_count = 0
- positive_optimistic_count = 0
- positive_conservative_count = 0
- positive_zero_il_lvr_count 全部 > 0
- best_scenario = zero_il_lvr
- transaction_sent = false
- solana_wallet_or_keypair_touched = false
- edge_proven = "no"
- tiny_canary_allowed = "no"
- send_hard_disable_still_active = true
- 5 stages 全部 recommended_next_stage 中包含 `STOP_LP_RESEARCH_NOW`

## 2. 必确认项 check

- [x] final freeze exists — `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` 存在
- [x] STOP_LP_RESEARCH_NOW 已写入 — verdict + WHY 文 + 5 protocol 全部写出
- [x] reopen_conditions_documented = true — FINAL_VERDICT.json 字段 + LP_RESEARCH_REOPEN_CONDITIONS_CN.md
- [x] can_run_probe_now = false — final freeze + 5 protocol 全部
- [x] tiny_canary_allowed = "no" — final freeze + 5 protocol 全部
- [x] all 5 protocols realistic positive = 0 — 5/5 verdict 字段 positive_realistic_count=0
- [x] all 5 protocols optimistic positive = 0 — 5/5 verdict 字段 positive_optimistic_count=0
- [x] all 5 protocols conservative positive = 0 — 5/5 verdict 字段 positive_conservative_count=0
- [x] cumulative EV cells = 28560 — FINAL_VERDICT.json cumulative_summary 字段
- [x] no transaction sent, no keypair touched — 5/5 protocol + final freeze 字段一致
- [x] send hard-disable still active — final freeze 字段

## 3. 与后续阶段的接口

本阶段输入证据审计通过. 后续 Stage C/D/E 都在本节 read-back 之上做口径修正, 不会
重新跑任何 protocol, 不会修改任何 heuristic, 不会改变 can_run_probe_now 标志.

输入证据 (只读) 锁存:
- 7 份 final freeze 文档
- 5 份 protocol verdict
- docs/LPBOT_RESEARCH_STATUS_CN.md
- docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md
- README.md
- 1 份 lp_scale_economics addendum (来自历史 2026-06-01 阶段, 不在本任务覆盖)

## 4. 不在本任务覆盖范围的输入 (read 不写)

- 所有 internal/adapters/chain/solana, internal/adapters/wallet, internal/adapters/mev
- configs/config.live.toml, configs/config.canary.toml
- cmd/lpbot 入口
- migrations/postgres
- .env* / .runtime.shadow.env

Stage B 通过. 进入 Stage C (当前结论适用范围).
