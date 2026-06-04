# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `66eba1f research: fix repeat long horizon readonly collector 20260604_084008`

## 0. 目的

本轮把"原 7D_RUN_REQUEST_V1 (一次性 7d 墙钟采集)" 改为"6 阶段递增式
(6h/12h/24h/48h/72h/7d) staged run request". 在生成 staged plan 之前,
read-back 上一阶段 fix_repeat_v1 + smoke_v1 + final freeze + 9 项 readiness,
锁存"哪些字段是 boundary" / "哪些字段是 build target" / "哪些字段是 hard-disable".
本轮不启动任何阶段, 不写 cron / systemd / tmux 实际启动, 只生成模板 + gate 规则 +
审批短语.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | fix_repeat_v1 FINAL_VERDICT | `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/FINAL_VERDICT.json` | ✅ read | status=WARN, source_adapter_implemented=true, classifier_implemented=true, retry_backoff_implemented=true, abort_condition_implemented=true, sqlite_enabled=true, jsonl_storage_ready=true, error_rate_monitor_implemented=true, real_data_smoke_ran=true, real_data_rows=72, placeholder_rows=1, total_rows=73, schema_validation_pass=true, research_only_write_ok=true, long_run_ready=false, recommended_next_stage=LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1 (但本轮**改**为 staged request, 不直接 7d) |
| 2 | fix_repeat_v1 smoke_result | `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/real_data_smoke_result.json` | ✅ read | selected_pool_count=5, sqlite_available=true, abort_summary.aborted=false, 0 error, 0 429, 0 write_failure |
| 3 | smoke_v1 FINAL_VERDICT | `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/FINAL_VERDICT.json` | ✅ read | recommended_next_stage=LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT (已完成) |
| 4 | final freeze FINAL_VERDICT | `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` | ✅ read | 5/5 reject, research_freeze_complete=true |

## 2. 9 项 readiness 当前状态 (per fix_repeat_v1)

| 字段 | 当前 | 来源 |
|---|---|---|
| `source_adapter_implemented` | ✅ | fix_repeat_v1 Stage E+F |
| `classifier_implemented` | ✅ | fix_repeat_v1 Stage G |
| `rate_limit_retry_backoff_implemented` | ✅ | fix_repeat_v1 Stage D |
| `abort_condition_implemented` | ✅ | fix_repeat_v1 Stage D |
| `sqlite_enabled` | ✅ | fix_repeat_v1 Stage H |
| `error_rate_monitor_implemented` | ✅ | fix_repeat_v1 Stage D |
| `paid_rpc_indexer_integrated` | ❌ | 仍留待 R0 长期 run |
| `cron_systemd_configured` | ❌ | 仍留待 R0 长期 run |
| `manual_approval_recorded` | ❌ | 仍留待 R0 长期 run |

注: 本轮**不实装** paid_rpc / cron / systemd / 实际 manual approval.
本轮**仅生成** staged plan + gate rules + 审批短语模板 + tmux 模板 (disabled).

## 3. boundary 字段 (locked, 不动)

- [x] `can_run_probe_now = false` (locked)
- [x] `tiny_canary_allowed = "no"` (locked)
- [x] `edge_proven = "no"` (locked)
- [x] `send_hard_disable_still_active = true` (locked)
- [x] `wallet_or_tx_touched = false`
- [x] `transaction_sent = false`
- [x] `long_run_started = false` (本任务不启动任何阶段)
- [x] `global_lp_rejected = false` (口径)

## 4. 改向记录: 7D_RUN_REQUEST_V1 → STAGED_REQUEST_V1

| 字段 | 原 7D_RUN_REQUEST_V1 | 本轮 STAGED_REQUEST_V1 |
|---|---|---|
| 阶段数 | 1 (一次性 7d) | 6 (6h/12h/24h/48h/72h/7d) |
| 起步 | 7d 直接跑 | 6h 起步, manual approval 升级 |
| auto_advance | n/a (单次) | **false** (每阶段必须独立审批) |
| first stage | n/a | **6h** |
| gate 规则 | 1 套 7d 终态 | 6 套 (每阶段独立) |
| cron / systemd | 7D_RUN 实装 | 本轮仅生成 disabled 模板, 不实装 |
| manual approval | 1 次 (进 7D_RUN) | 6 次 (每阶段一次) |

## 5. 硬性禁止项 (本轮全程不破)

- [x] 不启动 7d run
- [x] 不自动启动任何阶段 (auto_advance = false)
- [x] 不设置 cron (本轮 cron_enabled = false)
- [x] 不启用 systemd (本轮 systemd_enabled = false)
- [x] 不启动 daemon (本轮 daemon_started = false)
- [x] 不 probe / canary / live / paper
- [x] 不读取私钥 / seed / keypair / keystore
- [x] 不创建 signer
- [x] 不发送 transaction
- [x] 不 approve / mint / add/remove liquidity / collect / swap / bridge
- [x] 不写 production positions
- [x] 不覆盖 shadow 原始表
- [x] `can_run_probe_now` 必须保持 false
- [x] `tiny_canary_allowed` 必须保持 no
- [x] 本轮**不记录任何 approval 为 true** (本轮仅生成模板)

## 6. 本任务输出

- INPUT_EVIDENCE_AUDIT_CN.md / .json (本文件)
- STAGED_RUN_PLAN_CN.md / .json (Stage C)
- STAGE_GATE_RULES_CN.md / .json (Stage D)
- STAGE_APPROVAL_TEMPLATES_CN.md / .json (Stage E)
- STAGE_RUNTIME_BUDGET_CN.md / .json (Stage F)
- STAGE_FAILURE_AND_ABORT_POLICY_CN.md / .json (Stage G)
- STAGED_TMUX_SCRIPT_TEMPLATE_CN.md / .json (Stage H)
- FINAL_VERDICT.json (Stage I)
- ONEPAGE_CN.md (Stage I)
- ARTIFACT_INDEX.md (Stage I)
- tests/test_lp_long_horizon_readonly_collector_staged_request_v1.py (Stage J)

## 7. 不在本任务范围 (read 不写)

- 任何 6h/12h/24h/48h/72h/7d 实际 run (留待各 STAGE_RUN_APPROVAL_V1)
- 任何 paid RPC / paid indexer (留待 6H_RUN_APPROVAL_V1)
- 任何 cron / systemd / tmux 实际启动 (留待各 STAGE_RUN_APPROVAL_V1)
- 任何 manual approval 流程实装 (留待各 STAGE_RUN_APPROVAL_V1)
- 任何 实际 fee accrual 抓取 (R1 阶段, 需 user tokenId)
- 任何 protocol 重新连接 (5 connector 已 verify, 复用即可)
- 任何 heuristic 改动
- 任何 production 写

## 8. 结论

输入证据 read-back 通过. 9 项 readiness 状态确认. 改向记录 (7D → STAGED) 明确.
boundary 字段全部 locked, 硬禁止项明确. Stage B 通过. 进入 Stage C
(Staged run plan).
