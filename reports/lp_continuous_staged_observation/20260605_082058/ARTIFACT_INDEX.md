# ARTIFACT INDEX

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- run_id: `20260605_082058`
- branch: `feat/supabase-postgres-deployment`
- index_generated_at_utc: `2026-06-05T08:39:00Z`

## 1. 本轮交付物 (在 `reports/lp_continuous_staged_observation/20260605_082058/`)

| 阶段 | 文件 | 描述 |
|---|---|---|
| A | `CURRENT_V2_PROTECTION_AUDIT_CN.md` | V2 在轨保护审计 (CN) |
| A | `current_v2_protection_audit.json` | V2 在轨保护审计 (JSON) |
| B | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| B | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| C | `CONTINUOUS_STAGED_OBSERVATION_DESIGN_CN.md` | 连续 staged observation 设计 (CN) |
| C | `continuous_staged_observation_design.json` | 连续 staged observation 设计 (JSON) |
| D | `NODE_REPORT_SCHEMA_CN.md` | 节点报告 schema (CN) |
| D | `node_report_schema.json` | 节点报告 schema (JSON) |
| E | `POOL_UNIVERSE_COVERAGE_MANIFEST_SPEC_CN.md` | 池宇宙覆盖范围 manifest spec (CN) |
| E | `pool_universe_coverage_manifest_spec.json` | 池宇宙覆盖范围 manifest spec (JSON) |
| F | `FEE_ESTIMATION_WITHOUT_PROBE_CN.md` | 无探针资金时手续费估算依据说明 (CN) |
| F | `fee_estimation_without_probe.json` | 无探针资金时手续费估算依据说明 (JSON) |
| G | `RANGE_LIQUIDITY_FEE_SENSITIVITY_SPEC_CN.md` | range / tick / bin fee sensitivity spec (CN) |
| G | `range_liquidity_fee_sensitivity_spec.json` | range / tick / bin fee sensitivity spec (JSON) |
| H | (脚本: `scripts/lp_long_horizon_node_report_generator_v1.py`) | 节点报告生成器 v1 (read-only) |
| H | (sample 输出: `reports/lp_long_horizon_node_reports/20260605_043726/6h/`) | 6h partial_sample node report |
| I | `CONTINUOUS_OBSERVATION_NEXT_STAGE_DECISION_CN.md` | Next-stage 决策 (CN) |
| I | `continuous_observation_next_stage_decision.json` | Next-stage 决策 (JSON) |
| J | `FINAL_VERDICT.json` | Final Verdict |
| J | `ONEPAGE_CN.md` | One Page |
| J | `ARTIFACT_INDEX.md` | This file |

## 2. Sample Node Report (在 `reports/lp_long_horizon_node_reports/20260605_043726/6h/`)

11 个文件:

| 文件 | 描述 |
|---|---|
| `NODE_REPORT.json` | 完整 node report (24KB) |
| `NODE_REPORT_CN.md` | Node report CN 摘要 |
| `POOL_UNIVERSE_COVERAGE_MANIFEST.csv` | 3 层覆盖范围 (chain/dex/pool) |
| `POOL_UNIVERSE_COVERAGE_MANIFEST.json` | 同上 (JSON) |
| `FEE_ESTIMATION_BASIS.json` | 5 pool type fee proxy 公式 |
| `FEE_ESTIMATION_BASIS_CN.md` | 同上 (CN markdown) |
| `RANGE_LIQUIDITY_FEE_SENSITIVITY.csv` | 4 pool type × 3 range 表格 |
| `RANGE_LIQUIDITY_FEE_SENSITIVITY.json` | 同上 (JSON) |
| `CANDIDATE_REVIEW.csv` | best + rejected candidates |
| `CANDIDATE_REVIEW.json` | 同上 (JSON) |
| `FINAL_NODE_VERDICT.json` | 节点最终 verdict |

## 3. 工具 (scripts/)

| 文件 | 描述 |
|---|---|
| `scripts/lp_long_horizon_node_report_generator_v1.py` | 节点报告生成器 v1 (read-only, dry-run) |

## 4. 测试 (tests/)

| 文件 | 描述 |
|---|---|
| `tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py` | 验证本轮所有 schema / spec / tool / sample 完整性 |

## 5. 输入证据 (本轮**未**修改, 仅 audit)

| 标签 | 路径 | 状态 |
|---|---|---|
| `staged_request` | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/FINAL_VERDICT.json` | WARN |
| `data_pipeline` | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/FINAL_VERDICT.json` | WARN |
| `scope_audit` | `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json` | WARN |
| `v2_6h_run_startup` | `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/` | IN_FLIGHT (V2 supervisor PID 3872268) |
| `collector_script` | `scripts/lp_long_horizon_readonly_collector_v1.py` | READY |
| `supervisor_6h` | `scripts/run_lp_long_horizon_readonly_6h_once.sh` | RUNNING |

## 6. V2 在轨保护 (本轮**未**触碰)

| 字段 | 状态 |
|---|---|
| tmux session `lp_long_horizon_6h_v2_20260605_043726` | alive |
| supervisor PID 3872268 | alive, ELAPSED 3h+ |
| checkpoint 数 | 4/6 完成 |
| expected end | 2026-06-05T10:51:29Z |
| data_dir `data/lp_long_horizon/20260605_043726/` | 28 文件, 0 修改 |
| report_dir `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/` | 22 文件, 0 修改 |
| supervisor 脚本 | 0 修改 |
| collector 脚本 | 0 修改 |

## 7. 锁定字段 (本轮 5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 8. Forbidden 行为清单 (本轮全部不触发)

- 不 probe / canary / live / paper
- 不读 wallet / keypair / seed / private key
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- 不启用 cron / systemd / daemon
- 不自动启动 12h / 24h / 48h / 72h / 7d
- 不修改 V2 supervisor / collector / data

## 9. Recommended Next Stage

**`LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`**

(连续观察 + 节点报告, A 线严格不触 B 线)

**Allowed next stages** (4 选 1):
- `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1` (本轮推荐)
- `LP_CONTINUOUS_STAGED_OBSERVATION_FIX_REPEAT` (schema/script 不完整时)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户要求暂停)
- `STOP_LP_RESEARCH_NOW` (用户要求停止)

**Forbidden next stages** (本轮明确不选):
- `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` (V2 in-flight, 已执行)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (未批准)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_24H_RUN_APPROVAL_V1` (未批准)
- 任何 probe / canary / live / paper / wallet / keypair stage

## 10. 文件总数 (本轮)

- 本轮 spec + audit + decision + verdict + onepage + index: 22 个文件
- 工具脚本: 1 个 (scripts/lp_long_horizon_node_report_generator_v1.py)
- 测试文件: 1 个 (tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py)
- Sample node report 输出: 11 个文件 (reports/lp_long_horizon_node_reports/20260605_043726/6h/)

**Total: 35 个新文件 (本轮 commit 范围)**
