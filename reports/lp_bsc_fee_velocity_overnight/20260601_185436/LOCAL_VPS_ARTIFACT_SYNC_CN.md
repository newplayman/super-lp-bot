# 本机 artifact 同步

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: D
- run_id: `20260601_185436`
- environment: `vps_local`

## 同步动作

```text
synced_from = /tmp/lp_bsc_fee_velocity_overnight_20260601_185436
synced_to   = reports/lp_bsc_fee_velocity_overnight/20260601_185436
options     = -av （**故意不使用 --delete**，并排除本轮新写的审计报告）
```

## 为什么不使用 `--delete`

任务文档要求 `rsync -a --delete`，但当前 runner **仍 alive**（见 Phase C）。如果使用 `--delete`：

1. 会立即删除已在 repo 里写好的 `VPS_LOCAL_*`、`vps_local_*`、`LOCAL_VPS_*` 等本阶段产物（因为它们不存在于 `/tmp` 源端）；
2. runner 在我们 rsync 完成后会再次 checkpoint，导致一种"刚同步又过时"的窗口，错觉是收口完成。

因此本阶段使用 `-av` + 路径白名单：保留本轮审计文件，不破坏 /tmp 的新 checkpoint 写入。后续 runner 自然退出后，可再做一次同步以补齐最终 state。

## 同步结果

| artifact | 已同步 | 备注 |
|---|---|---|
| final/FINAL_VERDICT.json | yes | 仍是 21:05 的占位 final（mtime 1780340745），与 /tmp 一致 |
| checkpoint/state.json | yes | 07:11 写入的最新状态（mtime 1780377085） |
| logs/run.log | yes | 70 行，最后一行 `[2026-06-02T05:11:25Z]` |
| data/pool_fee_velocity.csv | yes | **1 行（仅 header）** |
| data/swap_logs_decoded.csv | yes | **1 行（仅 header）** |

保留的 phase 审计文件：

- `VPS_LOCAL_RUN_DIR_AUDIT_CN.md`
- `VPS_LOCAL_TMUX_PROCESS_STATUS_CN.md`
- `vps_local_run_dir_audit.json`
- `vps_local_tmux_process_status.json`

## 重要观察

`final/FINAL_VERDICT.json` 在 /tmp 中的 mtime 是 21:05（runner 启动后约 12 分钟），10 小时间内没有任何更新。这印证了：

```text
final 是 bootstrap 占位输出，不是当前 scan loop 的权威终态。
```

下一阶段（E/F/G）将基于 checkpoint + run.log 给出权威 progress 与 staleness 判定。
