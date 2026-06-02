# Artifact Index — `20260601_185436`

Stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
Environment: `vps_local`（不需要 ssh，本机即 VPS）
Local run dir: `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436`
Repo report dir: `reports/lp_bsc_fee_velocity_overnight/20260601_185436`

## 当前权威状态（一句话）

```text
runner 仍在跑（PID 2982619, user=deploy）；
checkpoint 显示 34/40 (85%)；
final/FINAL_VERDICT.json 是 21:05 占位、stale；
data CSV 因 RPC RuntimeError 仍为 header-only；
authoritative_status_source = checkpoint_and_run_log；
recommended_next_stage = WAIT_FOR_OVERNIGHT_COMPLETION
```

## 本轮新增 / 修正文件

### 权威判定与 finalize 报告

| 文件 | 用途 |
|---|---|
| `LOCAL_SYNC_FINAL_VERDICT_V2.json` | v2 verdict，字段语义已修正 |
| `LOCAL_SYNC_FINAL_VERDICT_V2_CN.md` | 同上中文版 |
| `RUNNING_STATUS.json` | finalizer auto 分支输出 |
| `RUNNING_STATUS_CN.md` | finalizer auto 分支中文版 |
| `ONEPAGE_STATUS_CN.md` | 单页总览 |

### 审计报告（Phase B-G + M）

| 文件 | 用途 |
|---|---|
| `VPS_LOCAL_RUN_DIR_AUDIT_CN.md` / `vps_local_run_dir_audit.json` | Phase B 本机 run 目录审计 |
| `VPS_LOCAL_TMUX_PROCESS_STATUS_CN.md` / `vps_local_tmux_process_status.json` | Phase C tmux/process 状态（runner active） |
| `LOCAL_VPS_ARTIFACT_SYNC_CN.md` / `local_vps_artifact_sync.json` | Phase D rsync `/tmp` → repo 报告（无 `--delete`） |
| `CHECKPOINT_PROGRESS_AUDIT_CN.md` / `checkpoint_progress_audit.json` | Phase E 进度 34/40 |
| `RUN_LOG_AUDIT_CN.md` / `run_log_audit.json` | Phase F run.log 解析 |
| `FINAL_AUTHORITY_AUDIT_CN.md` / `final_authority_audit.json` | Phase G final 权威性判定 |
| `VPS_LOCAL_SAFETY_AUDIT_CN.md` / `vps_local_safety_audit.json` | Phase M 本机安全检查（待写） |

### 新增 / 修复的工具

| 文件 | 说明 |
|---|---|
| `scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py` | 新 finalize/status 脚本（auto/running/partial/complete 四分支；--overwrite-final 才允许重建） |
| `scripts/collect_bsc_fee_velocity_overnight_artifacts.sh` | 重写为双模：本机 `/tmp` 优先 + SSH fallback，不使用 `--delete`，stale 警告 |
| `tests/test_finalize_bsc_fee_velocity_overnight_run_v1_readonly.py` | Pytest 覆盖 4 分支 + 安全断言 |
| `tests/test_collect_bsc_fee_velocity_overnight_artifacts.py` | Pytest 覆盖 local 优先、stale 警告、no-delete |

## 仍存在的运行产物（来自 /tmp，Phase D 同步）

| 路径 | 说明 |
|---|---|
| `checkpoint/state.json` | 当前权威进度（last_checkpoint_at 06:24:51） |
| `checkpoint/hourly_*.json` | 8 个 hourly 快照 |
| `final/FINAL_VERDICT.json` | **占位文件，stale**，selected_pool_count=0 不可作为结论 |
| `final/ARTIFACT_INDEX.md`, `final/ONEPAGE_CN.md`, ... | bootstrap 阶段写入的 placeholder 报告 |
| `logs/run.log` | 70 行扫描日志 |
| `data/pool_fee_velocity.csv` | 仅 header |
| `data/swap_logs_decoded.csv` | 仅 header |
| `scripts/lp_bsc_fee_velocity_overnight_runner.py` | runner 脚本副本 |
| `scripts/lp_bsc_fee_velocity_overnight_backfill_v1_readonly.py` | backfill 脚本副本 |

## v1 verdict 字段错误对照

`LOCAL_SYNC_FINAL_VERDICT.json` 中：

- `vps_final_synced = false` ✗ — 文件**已**同步；只是内容 stale。
- `selected_pool_count = 0` ✗ — 0 来自 stale final，权威值是 **8**。
- `root_cause = unknown` ✗ — 现已名命为 `stale_final_bootstrap_placeholder + rpc_runtime_error_on_public_fallback`。

详细对照见 `LOCAL_SYNC_FINAL_VERDICT_V2_CN.md`。

## 上一轮（仓库已有）的报告

| 文件 | 备注 |
|---|---|
| `SYNC_STATUS_CN.md` / `sync_status.json` | v1 同步报告（保留作历史） |
| `FINAL_VERDICT_REVIEW_CN.md` | v1 final review |
| `SELECTED_POOL_ZERO_ROOT_CAUSE_CN.md` / `selected_pool_zero_root_cause.json` | v1 早期根因分析 |
| `NEXT_FIX_PLAN_CN.md` / `next_fix_plan.json` | v1 修复计划（已被本轮 v2 verdict superseded） |
| `ONEPAGE_CN.md` | v1 单页（已被 `ONEPAGE_STATUS_CN.md` superseded） |
| `LOCAL_SYNC_FINAL_VERDICT.json` | v1 同步 verdict（已被 v2 superseded） |
| `BSC_OVERNIGHT_START_SAFETY_AUDIT_CN.md`, `BSC_RPC_READINESS_CN.md`, `BSC_SELECTED_POOL_SET_CN.csv`, `INPUT_ARTIFACT_AUDIT_CN.md`, `TMUX_START_HEALTHCHECK_CN.md`, `VPS_OVERNIGHT_RUN_BOOTSTRAP_CN.md` 等 | 启动期审计材料（仍有效） |
