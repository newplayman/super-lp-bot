# Stage B: 输入证据审计

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- audit_at_utc: `2026-06-05T08:21:00Z`
- operator: agent (只读)

## 0. 目的

确认本轮 A→L 使用的输入证据完整, 锁定用户两次方向调整的 redirect 链路, 并明确本轮**不**启动任何新 run, **不**触碰 V2.

## 1. 6 个核心输入证据

| 标签 | 路径 | 状态 | 关键字段 |
|---|---|---|---|
| `staged_request` | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/FINAL_VERDICT.json` | WARN | stages=[6h,12h,24h,48h,72h,7d], one_shot_7d_replaced=true, auto_advance=false, manual_approval_each_stage=true |
| `data_pipeline` | `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/FINAL_VERDICT.json` | WARN | 6 data categories, 7 regime, R0 proxy/R1 actual, smoke mode only writes to data/lp_long_horizon |
| `scope_audit` | `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json` | WARN | 6 model limitations, 4 HIGH impact, R0-R5 phases, locked conclusions unaffected by regime |
| `v2_6h_run_startup` | `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/` | IN_FLIGHT | supervisor PID 3872268 alive, 4/6 ckpt done, expected end 2026-06-05T10:51:29Z |
| `collector_script` | `scripts/lp_long_horizon_readonly_collector_v1.py` (22277B) | READY | design+smoke 2 modes, default design, write only to data/lp_long_horizon |
| `supervisor_6h` | `scripts/run_lp_long_horizon_readonly_6h_once.sh` (32301B) | RUNNING | SLEEP_SECONDS≥3600, LOOP_COUNT=6, approval phrase check, no forbidden process, fail-safe trap |

## 2. 用户方向调整 redirect 链

| 调整点 | 从 | 到 | 原因 |
|---|---|---|---|
| 第一次 | `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` (one-shot 7d) | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` (staged 6h/12h/24h/48h/72h/7d) | 用户 pivot: one-shot 7d → staged (per staged_request FINAL_VERDICT line 47) |
| 第二次 | (隐含) "每个节点停机等待人工审批" (per staged_request 字段 `auto_advance_allowed: false` + `manual_approval_required_each_stage: true`) | (本轮新设计) "collector 连续跑, 节点自动生成报告, 任何节点都不得自动 probe, 任何节点都不得自动进入交易" | 用户 pivot: 不要每个节点都停, 让 collector 连续跑, 用节点报告判断数据质量 + 是否继续采集 |

## 3. 关键断言 (本轮承诺)

| 断言 | 值 |
|---|---|
| `one_shot_7d_replaced` | ✅ **true** |
| `stages` | ✅ **`["6h", "12h", "24h", "48h", "72h", "7d"]`** |
| `auto_advance_allowed_originally` | ✅ **false** |
| `user_new_intent_continuous_observation_with_node_reports` | ✅ **true** |
| `user_new_intent_no_manual_stop_at_each_node` | ✅ **true** |
| `this_turn_only_designs_reporting_does_not_start_new_run` | ✅ **true** |
| `current_v2_6h_run_in_flight` | ✅ **true** (PID 3872268) |
| `current_v2_6h_run_protected` | ✅ **true** (per Stage A 审计) |

## 4. 本轮 (A→L) 范围声明

### 允许

- 设计 `continuous_staged_observation_spec`
- 设计 `node_report_schema`
- 设计 `coverage_manifest_spec`
- 设计 `fee_estimation_explanation`
- 设计 `range_liquidity_fee_sensitivity_spec`
- 实现 `node_report_generator_v1.py` (Python 只读脚本, 不启动 collector)
- 写 `tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py`
- commit + push 到 `feat/supabase-postgres-deployment` 分支 (本轮新文件)

### 禁止 (同 Stage A)

- 启动 V3 / 12h / 24h / 72h / 7d 新 run
- 修改 V2 supervisor (`scripts/run_lp_long_horizon_readonly_6h_once.sh`)
- 修改 V2 collector (`scripts/lp_long_horizon_readonly_collector_v1.py`)
- 写 V2 data_dir / V2 report_dir / V2 FINAL_VERDICT
- commit V2 数据 (本轮 commit 仅触及 `reports/lp_continuous_staged_observation/20260605_082058/` + `scripts/lp_long_horizon_node_report_generator_v1.py` + `tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py`)
- kill V2 supervisor / tmux
- 启动 daemon / cron / systemd
- probe / canary / live / paper
- 读 wallet / keypair / signer / 私钥
- 发送 transaction / approve / mint / swap / bridge
- 接 paid RPC / paid indexer

## 5. 一致性结论

| 维度 | 状态 |
|---|---|
| 6 个输入证据全部存在 | ✅ |
| 用户两次方向调整 redirect 链清晰 | ✅ |
| 本轮不启动新 run, 不触碰 V2 | ✅ |
| `can_run_probe_now` 保持 `false` | ✅ |
| `tiny_canary_allowed` 保持 `"no"` | ✅ |
| `edge_proven` 保持 `"no"` | ✅ |
| LP strategy research 仍处于 freeze | ✅ (per `docs/LPBOT_RESEARCH_STATUS_CN.md` + scope_audit line 22) |

**Stage B PASS** → 进入 Stage C (连续 staged observation 设计).
