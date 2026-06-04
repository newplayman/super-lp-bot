# LP Research Conclusion Scope Audit — Artifact Index

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: git fetch / branch / status / log 摘要, 脏文件处理 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: final freeze 7 份 + 5 protocol verdict 逐条 read-back |
| `input_evidence_audit.json` | Stage B: 输入证据字段化 |
| `CURRENT_CONCLUSION_SCOPE_CN.md` | Stage C: 当前结论适用范围 (能 / 不能证明什么) |
| `current_conclusion_scope.json` | Stage C: scope 字段化 |
| `MODEL_LIMITATION_AUDIT_CN.md` | Stage D: 6 维度模型边界审计 |
| `model_limitation_audit.json` | Stage D: 模型边界字段化 |
| `MARKET_REGIME_BIAS_AUDIT_CN.md` | Stage E: 市场 regime 偏差审计 + 7 regime 分类 |
| `market_regime_bias_audit.json` | Stage E: regime 偏差字段化 |
| `LONG_HORIZON_REOPEN_PLAN_CN.md` | Stage F: R0-R5 6 阶段重开计划 |
| `long_horizon_reopen_plan.json` | Stage F: 重开计划字段化 |
| `FINAL_VERDICT.json` | Stage H: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage H: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage H: 本索引 (本文件) |

## 修改的文档 (本任务 commit 范围)

- `docs/LPBOT_RESEARCH_STATUS_CN.md` — 加上 scope addendum, run_id 改 060659
- `README.md` — Current Research Status 段加上 scope 字段, run_id 改 060659
- `tests/test_lp_research_conclusion_scope_audit_v1.py` — 新增 pytest

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json`
- `reports/lp_research_final_freeze/20260604_051254/WHY_STOP_LP_RESEARCH_NOW_CN.md`
- `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md`
- `reports/lp_research_final_freeze/20260604_051254/WHAT_THIS_DOES_NOT_MEAN_CN.md`
- `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json`
- `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json`
- `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json`
- `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json`
- `reports/lp_solana_stable_pool_research/20260604_044118/FINAL_VERDICT.json`
- `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md`

## 上一轮同任务 (本任务延续, 不重复提交)

- `reports/lp_research_conclusion_scope_audit/20260604_053626/` — 上一轮 053626 run
  的产物, 与本轮 060659 内容等价但口径精度低, 在 git publish 时一起 add 保留历史

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `CURRENT_CONCLUSION_SCOPE_CN.md` (结论适用范围)
4. `LONG_HORIZON_REOPEN_PLAN_CN.md` (R0-R5 重开计划)
5. `MODEL_LIMITATION_AUDIT_CN.md` (模型边界)
6. `MARKET_REGIME_BIAS_AUDIT_CN.md` (regime 偏差)
7. `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md` (7 条件)
