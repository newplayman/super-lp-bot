# Final 权威性审计

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: G
- run_id: `20260601_185436`

## 三方对照

| 信号 | final/FINAL_VERDICT.json | checkpoint/state.json | logs/run.log |
|---|---|---|---|
| mtime / last_event | 1780340745（21:05） | 1780377085（07:11） | 末行 `2026-06-02T05:11:25Z` |
| selected_pool_count | **0** | **8** | 见 7 个 pool 进入 scan |
| windows_completed | `["14d","24h","30d","72h","7d"]`（虚构） | 24h/72h/7d/14d × 7、30d × 6，共 34/40 | 34 个 checkpoint 事件 |
| swap_log_count | 0 | n/a | `log_count: 0` × 34（一致，但原因是 RPC 失败） |
| status / 终态 | `FAIL` | `is_completed: false` | last log mid-scan `30d` |
| runner active? | n/a | 推断仍在跑 | 末行无收尾 |

`final/FINAL_VERDICT.json` 与 checkpoint/log 直接冲突：

- `selected_pool_count=0`：**错误**。8 个池都已选中并写入 `BSC_SELECTED_POOL_SET_CN.csv`。
- `windows_completed`：**虚构**。本轮 run 还没完成任何 pool 的全部窗口（最近的 30d 全集只完成 6/8）。
- 整体 `status=FAIL` 是 bootstrap 写入时占位用，不是结论。

## 规则判定

```text
runner_process_active = true        (Phase C)
final.mtime < checkpoint.mtime      (36340 秒)
completed_target_count = 34 < 40    (Phase E)
data CSV 仍空                       (Phase B/F)

→ rule_1: runner_active
  authoritative_status_source = checkpoint_and_run_log
  final_is_current = false
  final_is_stale_or_unverified = true
  must_not_overwrite_final = true
```

## `selected_pool_count = 0` 根因

不是策略空，不是池子被全部过滤掉，**只是** `final/FINAL_VERDICT.json` 是 runner bootstrap 阶段写出的占位文件，没有任何后续 scan 结果回填。原因结构性：

- runner 写 final 是在 21:05（启动后 ~12 分钟）；
- 之后 10 小时进入 long scan loop；
- scan loop 把数据写到 `data/*.csv`（实际上 RPC 失败、未写入数据）和 `checkpoint/state.json`（推进中）；
- scan loop 没有循环回写 final，因此 `final.selected_pool_count` 永远停留在 bootstrap 时的 0。

## 能否用 data 重建 final？

**不能**。两份 data CSV 都是 header-only：

```text
data/pool_fee_velocity.csv  : 1 行（仅 header）
data/swap_logs_decoded.csv  : 1 行（仅 header）
```

且 34 个 checkpoint 全部 `log_count: 0`，其中 20 个 partial+rpc_error。重建 final 没有可用素材；即使 runner 自然结束跑到 40/40，data 也大概率仍为空。

## 结论

| 字段 | 值 |
|---|---|
| final_exists | yes |
| final_status (文件原值) | `FAIL`（占位，不可作为权威） |
| final_selected_pool_count | 0（占位） |
| checkpoint_selected_pool_count | 8（权威） |
| final_is_current | **false** |
| final_is_stale_or_unverified | **true** |
| authoritative_status_source | `checkpoint_and_run_log` |
| selected_pool_zero_from_stale_final | **true** |
| must_not_overwrite_final | **true**（runner 还活着） |
| data_csvs_usable_for_rebuild | **false** |

## 下一步建议

```text
1. Phase H 实现 finalize/status 脚本，按本规则走 running 分支：
   - 不覆盖 final
   - 写 RUNNING_STATUS_CN.md + RUNNING_STATUS.json
2. runner 自然退出后（--max-hours 10 已超），人工重跑 Phase D/E/F/G：
   - 若 completed_target_count = 40 但 data 仍空 → finalize_mode=partial_warn
   - 若 data 真的有 row → 才允许 --overwrite-final 重建权威 final
3. 不发起新 long-run，不 probe/canary/live/paper。
```
