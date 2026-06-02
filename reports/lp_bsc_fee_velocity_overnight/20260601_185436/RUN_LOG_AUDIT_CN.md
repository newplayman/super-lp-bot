# run.log 审计

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: F
- run_id: `20260601_185436`
- source: `reports/lp_bsc_fee_velocity_overnight/20260601_185436/logs/run.log`

## 摘要

| 字段 | 值 |
|---|---|
| first_log_time | `2026-06-01T19:13:16Z` |
| last_log_time | `2026-06-02T05:11:25Z` |
| log_line_count | 70 |
| has_traceback | no |
| has_error | no |
| has_max_hours_reached | no |
| has_scan_loop | yes |
| scan_loop_line_count | 35 |
| checkpoint_events_count | 34 |
| partial_checkpoint_count | **20** |
| partial_checkpoint_share | **58.8%** |
| rpc_error_checkpoint_count | 20 |
| last_processed_pool_window | `0x1401ff943D08a7E098328C1d3a9d388923B115D2 \| 14d` |
| in_progress_target | `0x1401ff943D08a7E098328C1d3a9d388923B115D2 \| 30d` |
| final_written_hint | no |

## 关键观察

1. **日志没有 traceback，没有 stderr ERROR 关键字** — 但 `partial: true, root_cause: rpc_error:RuntimeError` 出现了 **20 次**，约占已完成 checkpoint 的 59%。RPC 健康度严重劣化。
2. **`log_count: 0` 出现在所有 checkpoint 中** — `data/swap_logs_decoded.csv` header-only 与之一致：runner 实际上没有解码出任何 swap log，无论是否 partial。这是数据获取层（eth_getLogs / RPC quota）的问题，不是策略问题。
3. **`scan_loop_line_count (35) > checkpoint_events_count (34)`** — runner 在 `[2026-06-02T05:11:25Z] scan pool=0x1401ff...|30d` 启动了新窗口扫描，**还没写 checkpoint**。这是 runner 当前的活跃点。
4. **`final_written_hint = no`** — log 中没有任何 "wrote final" / "FINAL_VERDICT" 字样，证实 final/FINAL_VERDICT.json 是 21:05 bootstrap 写入后再无更新。

## 与 final 占位的对照

| 信号 | final/FINAL_VERDICT.json 说法 | run.log + checkpoint 事实 |
|---|---|---|
| selected_pool_count | 0 | **8** |
| windows_completed | `["14d","24h","30d","72h","7d"]` | 24h/72h/7d/14d 各 7 个、30d 6 个、共 34/40，**未完成** |
| swap_log_count | 0 | 0（一致——但原因是 RPC 失败，不是没池子） |
| fee_ready_pool_count | 0 | 0（一致——但同样是 RPC 问题） |
| best_pool / best_pair / ... | 空 | 不可填（仍在扫） |

`final` 把 `selected_pool_count=0` 说成结论；事实是 8 个池都已选中、7 个已部分处理，只是 RPC 拉不出 swap log。**这是 final 文件最严重的失实之处。**

## 含义

```text
runner 还在跑（Phase C 确认）；
log 还在 05:11Z 这一刻；
data CSV 还是空的（RPC 故障）；
最近 20 个 checkpoint 都 partial。
→ 即便 runner 自然退出，本轮 run 也只能算 partial run；
→ data/ 本身没有可用结果，不能"重建权威 final"；
→ 唯一合理动作：标记当前 final 为 stale 占位，写 RUNNING_STATUS 或 PARTIAL_WARN。
```
