# Checkpoint 进度审计

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: E
- run_id: `20260601_185436`
- source: `checkpoint/state.json`（rsync 自 `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436/checkpoint/state.json` after Phase D）

## 摘要

| 字段 | 值 |
|---|---|
| selected_pool_count | 8 |
| pool_count | 8 |
| windows | `["24h", "72h", "7d", "14d", "30d"]` |
| window_count | 5 |
| expected_pool_window_targets | **40** |
| completed_target_count | **34** |
| remaining_target_count | 6 |
| progress_pct | **85.0%** |
| last_checkpoint_at_unix | 1780374291 (≈ 2026-06-02 06:24:51) |
| current_time_unix | 1780377085 (≈ 2026-06-02 07:11:25) |
| latest_block | 101743639 |
| resume | `false` |
| rpc_env_key | `public_fallback` |
| is_completed | **false** |
| completion_ratio | `34/40` |

## 按窗口完成度

| window | 完成 | 总数 |
|---|---|---|
| 24h | 7 | 8 |
| 72h | 7 | 8 |
| 7d | 7 | 8 |
| 14d | 7 | 8 |
| 30d | **6** | 8 |

## 按 pool 完成度

| pool | 完成窗口数 |
|---|---|
| 0xf2688Fb5B81049DFB7703aDa5e770543770612C4 (WBNB/USDC 0.01%) | 5/5 |
| 0x172fcD41E0913e95784454622d1c3724f546f849 (WBNB/USDT 0.01%) | 5/5 |
| 0x18C5aFFA481e7EDbF37405AdE553827d6387899f (WBNB/USDC 1.0%) | 5/5 |
| 0x36696169C63e42cd08ce11f5deeBbCeBae652050 (WBNB/USDT 0.05%) | 5/5 |
| 0x81A9b5F18179cE2bf8f001b8a634Db80771F1824 (WBNB/USDC 0.05%) | 5/5 |
| 0xc721dECCD986D54B39e8c29428A1f06155c3671e (WBNB/USDC 0.25%) | 5/5 |
| 0x1401ff943D08a7E098328C1d3a9d388923B115D2 (WBNB/USDT 0.25%) | **4/5** |
| 0x6805E0E5333c5c3acCF2930Be4734E2b98f4Ce06 (WBNB/USDT 1.0%) | **0/5** ← 未触及 |

## 与原任务文档的差异

任务文档写 `completed_target_count 当前约 33`。实际为 **34**（run.log 也已写到 `processed_pool_windows: 34`）。这是因为任务文档基于较早的状态快照；本审计基于 Phase D rsync 后最新 state.json（mtime 1780377085）。

## 关键事实

1. **不是空跑** — `selected_pool_count = 8` 且实际已扫到 7 个 pool，只有 1 个 pool 完全未触及。
2. **不是已完成** — 仍差 6 个 pool-window 目标（其中 5 个属于未启动的 `0x6805...`，1 个属于正在跑的 `0x1401...|30d`）。
3. **进度 85%**，runner 还活着（Phase C 确认），但 `--max-hours 10` 已过期，预计将很快自动退出，留下一个 **partial completion**。

## 对 finalize 决策的影响

```text
is_completed = false
runner_process_active = yes (来自 Phase C)
→ finalize 模式 = running_status
→ 不写 FINAL_VERDICT，不写 PARTIAL_FINAL_VERDICT，只写 RUNNING_STATUS
当 runner 退出后再判断；届时 is_completed 仍可能 = false，
那时 finalize 模式应为 partial_warn。
```
