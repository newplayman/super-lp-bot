# Stage A: 输入证据审计

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- audit_stage: `A_INPUT_EVIDENCE_AUDIT`
- audited_at_utc: `2026-06-05T13:30:00Z`

## 0. 目的

确认本轮输入证据完整, 锁定 V2 supervisor finalize 失败根因, 并明确 rebuild 路径.

## 1. 4 个核心输入证据

| 标签 | 路径 | 关键事实 |
|---|---|---|
| `v2_final_verdict` | `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json` | status=**FAIL**, runtime=360, gate=**false**, rows=**0**, `finalize_error: trap EXIT rc=1` |
| `node_report_verdict` | `reports/lp_long_horizon_node_reports/20260605_043726/6h/FINAL_NODE_VERDICT.json` | full_sample=**true**, ckpts=6/6, gate=PASS, rows=30/180/150/30/42/6 |
| `v2_data_dir` | `data/lp_long_horizon/20260605_043726/` | 6 ckpts × 7 文件 = 42 文件, dedup rows=5/180/150/30/42/6 |
| `supervisor_script` | `scripts/run_lp_long_horizon_readonly_6h_once.sh` | 747 行, post-6h block 有 typo + 缺少 aggregate-failure handler |

## 2. 关键断言

| 断言 | 值 |
|---|---|
| `runtime_valid` | ✅ **true** (actual_runtime_minutes=360 >= 330) |
| `short_mode_used` | ✅ **false** (LOCKED) |
| `checkpoint_count` | ✅ **6** |
| `checkpoint_data_exists` | ✅ **true** (42 文件 完整) |
| `original_final_verdict_status` | ❌ **FAIL** |
| `original_finalizer_failed` | ✅ **true** (trap EXIT rc=1) |
| `original_rows_zero_due_to_finalize_bug` | ✅ **true** (FINAL_VERDICT 显示 0/0/0/0/0, 实际 ckpt 有 5/180/150/30/42/6) |
| `data_dir_unchanged` | ✅ **true** (本轮不动 data_dir) |
| `wallet_or_tx_touched` | ❌ **false** |

## 3. V2 supervisor finalize 失败根因分析

### 3.1 现状

| 维度 | V2 FINAL_VERDICT | Node Report (重建) | 实际 ckpt |
|---|---|---|---|
| actual_runtime_minutes | 360 | 360 | (supervisor log: 360) |
| actual_runtime_valid_for_6h_gate | true | true | true |
| short_mode_used | false | false | false |
| pool_snapshot_rows | 0 | 30 | 30 (= 5 unique pools × 6 ckpts) |
| quote_snapshot_rows | 0 | 180 | 180 |
| fee_velocity_rows | 0 | 150 | 150 |
| liquidity_distribution_rows | 0 | 30 | 30 |
| market_regime_rows | 0 | 42 | 42 |
| actual_fee_accrual_placeholder_rows | (not in V2 verdict) | 6 | 6 |
| **status** | **FAIL** | **PASS** | (real) |
| **gate_pass** | **false** | **true** | (real) |

### 3.2 根因

V2 supervisor 6h wallclock 跑完 (T0=04:51:15Z, END_TS=10:51:29Z, 真实 360 min), 6 ckpts 全部生成 (42 文件), 但 post-6h block (Python heredoc at line 350 of supervisor script) 在写 FINAL_VERDICT.json **之前**失败. 失败原因未在 log 留 Python traceback (因为 heredoc 用 `set -e` 直接 abort 了).

随后 fail-safe trap (V1 "no silent loss" 修复) 触发, 写 FAIL FINAL_VERDICT with default zeros, **覆盖**了 post-6h block 即将写入的真实数据.

### 3.3 supervisor script 已知 bug

| 行号 | Bug | 严重度 |
|---|---|---|
| 537 | `LP_LONG_HORIZON_READONLY_COLLECTOR FIX_REPEAT` 中间有空格, 应为 `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT` | low (本轮不触发, 因 gate=true) |
| (post-6h block) | 缺 aggregate-failure handler — 失败时直接 abort, 没有 fallback 路径 | high (本次事故的根因) |
| (trap at line 99) | trap EXIT 时**不**应覆盖成功的 FINAL_VERDICT (line 102-104 已有 early-return, 但仍要确认 trap 触发时 FINAL_VERDICT 尚未被 post-6h block 写入) | high |

**本轮 (LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1) 修复策略**:

1. **Stage B**: 修补 supervisor script (line 537 typo + 加 aggregate-failure fallback handler + 强化 trap 保护)
2. **Stage C**: 新增独立 `scripts/rebuild_lp_long_horizon_6h_verdict_from_checkpoints_v1.py` (read-only + write to NEW report_dir)
3. **Stage D**: 用 rebuild 脚本从 V2 ckpt 数据生成 CORRECTED_FINAL_VERDICT + 6 supporting reports, 写到 `reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726/`, **不**覆盖 V2 原始 FAIL verdict

## 4. 一致性结论

| 维度 | 状态 |
|---|---|
| 4 个输入证据全部存在 | ✅ |
| runtime_valid=true | ✅ |
| checkpoint_count=6, data 完整 | ✅ |
| 原始 FAIL verdict 状态锁定 | ✅ |
| rebuild 路径不覆盖原始 | ✅ |
| `can_run_probe_now=false` 保持 | ✅ |
| `tiny_canary_allowed="no"` 保持 | ✅ |
| `edge_proven="no"` 保持 | ✅ |
| LP strategy research 仍处于 freeze | ✅ |

**Stage A PASS** → 进入 Stage B (修复 supervisor finalize 逻辑).
