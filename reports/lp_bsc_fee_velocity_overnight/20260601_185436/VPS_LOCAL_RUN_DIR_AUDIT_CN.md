# VPS 本机 run 目录审计

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: B
- run_id: `20260601_185436`
- environment: `vps_local`（不需要 ssh）
- run_dir: `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436`

## 存在性

| artifact | 存在 | 备注 |
|---|---|---|
| run_dir | yes | |
| final/ | yes | bootstrap 期写入 |
| data/ | yes | 仅 header，没有 row |
| checkpoint/ | yes | 含 8 个 hourly + state.json |
| logs/ | yes | 70 行 |
| final/FINAL_VERDICT.json | yes | 1019 字节，写于 21:05 |
| checkpoint/state.json | yes | 2350 字节，写于 07:11 |
| logs/run.log | yes | 70 行，末行 05:11:25Z |
| data/pool_fee_velocity.csv | yes | **1 行（仅 header）** |
| data/swap_logs_decoded.csv | yes | **1 行（仅 header）** |

## 时间戳关键比较

| 文件 | mtime (UNIX) | 本地时间近似 |
|---|---|---|
| final/FINAL_VERDICT.json | 1780340745 | 2026-06-01 21:05 |
| data/pool_fee_velocity.csv | 1780340745 | 2026-06-01 21:05 |
| data/swap_logs_decoded.csv | 1780340745 | 2026-06-01 21:05 |
| checkpoint/state.json | 1780377085 | 2026-06-02 07:11 |
| logs/run.log | 1780377085 | 2026-06-02 07:11 |

**checkpoint 比 final 新 36340 秒（≈ 10 小时 5 分钟）**。
final / data CSV mtime 完全相同 (21:05)，说明 runner 在启动后 12 分钟就一次性写出了"占位 final"和 header-only CSV，然后开始真正的 scan loop，之后未再回填 data CSV、也未再覆盖 final。

## 数据空状态成因

`run.log` 中所有 33 个 `processed_pool_windows` 的 checkpoint 事件都报 `log_count: 0`，最近 14d/7d 窗口报 `partial: true, root_cause: "rpc_error:RuntimeError"`。这是**当前 run 实际还没有有效 fee 数据落盘**，而不是 final/FINAL_VERDICT.json 的 `selected_pool_count=0` 反映了真实结论。

## 立刻可见的结论

1. 仓库内 final/FINAL_VERDICT.json 是 bootstrap 占位文件，不是当前权威终态。
2. data CSV 还是空的，因此即便 process 结束，也不能用 data 重建权威 final——data 本身就是 0 行。
3. 后续 phase 必须用 checkpoint + run.log 作为权威源；data CSV 缺失需要单独标记。
