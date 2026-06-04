# LP Long Horizon Read-only Data Pipeline — Artifact Index

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: workspace 安全检查 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: 7 boundary 字段 + 3 build target 字段 read-back |
| `input_evidence_audit.json` | Stage B: 字段化 |
| `LONG_HORIZON_DATA_REQUIREMENTS_CN.md` | Stage C: 6 类数据 schema 蓝图 |
| `long_horizon_data_requirements.json` | Stage C: 字段化 |
| `READONLY_COLLECTOR_ARCHITECTURE_CN.md` | Stage D: 5 层架构 + CLI + rate limit |
| `readonly_collector_architecture.json` | Stage D: 字段化 |
| `RESEARCH_ONLY_SCHEMA_CN.md` | Stage E: 6 张表 jsonl/csv + sqlite DDL |
| `research_only_schema.json` | Stage E: 字段化 |
| `MARKET_REGIME_CLASSIFIER_SPEC_CN.md` | Stage F: 7 regime + decision tree + 优先级 |
| `market_regime_classifier_spec.json` | Stage F: 字段化 |
| `ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md` | Stage G: 5 section schema (entry/exit/collect/tokens_owed/derived) |
| `actual_fee_accrual_schema.json` | Stage G: 字段化 |
| `COLLECTOR_SAFETY_AUDIT_CN.md` | Stage H: 7 层审计 (架构/代码/数据源/写路径/锁存/进程/跨阶段) |
| `collector_safety_audit.json` | Stage H: 字段化 |
| `FINAL_VERDICT.json` | Stage K: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage K: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage K: 本索引 (本文件) |

## 新增 / 修改文件 (本任务 commit 范围)

- `scripts/lp_long_horizon_readonly_collector_v1.py` — 新增 (design + smoke mode, default design)
- `tests/test_lp_long_horizon_readonly_data_pipeline_v1.py` — 新增 (52 个 assertion 全部通过)
- `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/` — 17 份本阶段产物

未修改:
- `docs/LPBOT_RESEARCH_STATUS_CN.md` (本阶段是技术实施, 不是口径修正)
- `README.md` (同上)
- 任何 `cmd/` `internal/` `migrations/` `configs/` `web/` 文件
- 任何 `data/dryrun*` `data/shadow*` `data/live*` 表

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json`
- `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md`
- `reports/lp_research_conclusion_scope_audit/20260604_060659/MODEL_LIMITATION_AUDIT_CN.md`
- `reports/lp_research_conclusion_scope_audit/20260604_060659/MARKET_REGIME_BIAS_AUDIT_CN.md`

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `INPUT_EVIDENCE_AUDIT_CN.md` (上游 boundary / build target 锁存)
4. `LONG_HORIZON_DATA_REQUIREMENTS_CN.md` (6 类数据)
5. `READONLY_COLLECTOR_ARCHITECTURE_CN.md` (采集器架构)
6. `MARKET_REGIME_CLASSIFIER_SPEC_CN.md` (7 regime)
7. `ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md` (actual fee schema)
8. `COLLECTOR_SAFETY_AUDIT_CN.md` (7 层审计)
9. `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md` (R0-R5 全局)

## 后续阶段 (本任务不覆盖)

- R0 阶段长期运行 (LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1) — 需独立 stage + manual approval
- R1 阶段 actual fee 抓取 — 需 user 提供 tokenId 或 paid indexer
- R2 阶段 regime split EV 跑 — 需 R0 + R1 数据
- R3 阶段 candidate review — 需 R0 + R1 + R2
- R4 阶段 10U tokenId probe preflight — 需 R3 candidate
- R5 阶段 manual probe — 需 R4 preflight, manual approval only
