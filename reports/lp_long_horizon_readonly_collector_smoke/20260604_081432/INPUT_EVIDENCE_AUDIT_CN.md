# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `cdeb058 research: build lp long horizon readonly data pipeline 20260604_062324`

## 0. 目的

在跑 smoke 之前, 把上一阶段 pipeline 留下的 7 份权威产物 + collector 脚本逐条
read-back 验证, 锁存"哪些字段是 boundary" / "哪些字段是 smoke target" / "哪些字段
是 hard-disable". 这是只读 audit, 不修改任何上一阶段 verdict, 不修改 collector 脚本.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | FINAL_VERDICT.json | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/FINAL_VERDICT.json` | ✅ read | stage=LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1, status=WARN, long_horizon_pipeline_ready=true, collector_script_built=true, market_regime_classifier_spec_ready=true, actual_fee_accrual_schema_ready=true, can_run_probe_now=false, tiny_canary_allowed=no, edge_proven=no, wallet_or_tx_touched=false, transaction_sent=false, send_hard_disable_still_active=true, recommended_next_stage=LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1, safety.*=false |
| 2 | ONEPAGE_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/ONEPAGE_CN.md` | ✅ read | 5 核心字段 ready, 6 类 schema, 7 regime, 5 section actual fee, smoke 模式 30 cells |
| 3 | READONLY_COLLECTOR_ARCHITECTURE_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/READONLY_COLLECTOR_ARCHITECTURE_CN.md` | ✅ read | 5 设计原则, 5 层架构, CLI 参数表, safety guard 8 invariants |
| 4 | RESEARCH_ONLY_SCHEMA_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/RESEARCH_ONLY_SCHEMA_CN.md` | ✅ read | 6 张表 schema, sqlite DDL, 写路径约束, 字段命名约定 |
| 5 | MARKET_REGIME_CLASSIFIER_SPEC_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/MARKET_REGIME_CLASSIFIER_SPEC_CN.md` | ✅ read | 7 regime + 优先级, 输入数据 8 项, 输出 schema, decision tree, 边界情况 5 类 |
| 6 | ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md` | ✅ read | 5 section (entry/exit/collect_fee/tokens_owed/derived) |
| 7 | COLLECTOR_SAFETY_AUDIT_CN.md | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/COLLECTOR_SAFETY_AUDIT_CN.md` | ✅ read | 7 层审计, 30+ banned tokens, 7 forbidden write paths |
| 8 | scripts/lp_long_horizon_readonly_collector_v1.py | `scripts/lp_long_horizon_readonly_collector_v1.py` | ✅ read | default design mode, smoke 1 pass, AST+tokenize safety self-check, 9 reject paths |

## 2. 必确认项 check

### 2.1 boundary 字段 (locked, 不动)

- [x] previous stage = `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- [x] `can_run_probe_now = false` (locked)
- [x] `tiny_canary_allowed = "no"` (locked)
- [x] `edge_proven = "no"` (locked)
- [x] `send_hard_disable_still_active = true` (locked)
- [x] `global_lp_rejected = false` (口径锁定)
- [x] `current_probe_allowed = false`
- [x] `long_term_lp_value_judged = false`
- [x] `wallet_or_tx_touched = false` (locked)
- [x] `transaction_sent = false` (locked)

### 2.2 smoke target 字段 (本任务)

- [x] `collector_script_built = true` (上一阶段已构建)
- [x] `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1` (本任务)
- [x] `default_mode = design` (脚本已实现)
- [x] `smoke_mode_writes_only_to_data_lp_long_horizon = true` (脚本已实现)
- [x] smoke 1 pass, 不 daemon
- [x] long-run 需要 separate audit + manual approval

### 2.3 hard-disable 字段 (本任务全程不破)

- [x] 不读取私钥 / seed / keypair / keystore
- [x] 不创建 signer
- [x] 不发送 transaction
- [x] 不 approve / mint / add_liquidity / remove_liquidity / collect_fee
- [x] 不 swap / bridge
- [x] 不启动 live / canary / paper / probe
- [x] 不写 production positions
- [x] 不覆盖 shadow 原始表
- [x] 不启动长期 daemon
- [x] 不自动跑 7d/14d/30d
- [x] 不接 paid RPC / paid indexer
- [x] `can_run_probe_now` 必须保持 false
- [x] `tiny_canary_allowed` 必须保持 no

## 3. 本任务输出 (lock from input)

- INPUT_EVIDENCE_AUDIT_CN.md / .json
- COLLECTOR_CLI_REVIEW_CN.md / .json
- COLLECTOR_DESIGN_MODE_RESULT_CN.md / .json
- COLLECTOR_SMOKE_RESULT_CN.md / .json
- SMOKE_OUTPUT_SCHEMA_VALIDATION_CN.md / .json
- MARKET_REGIME_SMOKE_VALIDATION_CN.md / .json
- COLLECTOR_HEALTH_AND_FAILURE_MODE_CN.md / .json
- LONG_HORIZON_COLLECTOR_NEXT_STAGE_DECISION_CN.md / .json
- FINAL_VERDICT.json
- ONEPAGE_CN.md
- ARTIFACT_INDEX.md
- tests/test_lp_long_horizon_readonly_collector_smoke_v1.py

## 4. 不在本任务范围 (read 不写)

- 任何 long-run 启动 (LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1 是后续独立 stage)
- 任何 paid indexer / paid RPC 接入
- 任何 实际 fee accrual 抓取 (R1 阶段)
- 任何 regime split 实际跑 (R2 阶段)
- 任何 incentive / vault 候选 review (R3 阶段)
- 任何 probe preflight (R4 阶段)
- 任何 manual probe (R5 阶段)
- 任何 protocol re-run
- 任何 heuristic 改动
- 任何 collector 脚本代码改动 (Stage I 仅运行不修改)

## 5. 与 R0 阶段的对应

本任务是 R0 阶段的 smoke 验证, 不启动 long-run:
- ✅ 运行 design mode (Stage D)
- ✅ 运行 smoke mode 1 pass (Stage E)
- ✅ 验证 output schema (Stage F)
- ✅ 验证 regime sample (Stage G)
- ✅ 评审 health / failure mode (Stage H)
- ✅ 决定下阶段 (Stage I)
- ⏸ 7d run (R0 阶段后续, 需独立 stage + manual approval)
- ⏸ 14d / 30d run (更后续)

## 6. 结论

输入证据 read-back 通过. boundary 字段全部 locked, smoke target 字段清晰,
hard-disable 项明确. Stage B 通过. 进入 Stage C (collector CLI 审查).
