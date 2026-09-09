# 结论摘要

| 条目 | 状态 | 一句话结论 |
|---|---|---|
| Gas 漂移 | 未达刷新阈值 | 29 条观测全部在静态值 ±20% 内，最大绝对漂移 11.21%，触发 0 次。 |
| Stage A 覆盖 | 进行中 | 当前覆盖 38h15m43s；预计 72h 于 `2026-09-11 05:15:28Z`，约 90h 毕业于 `2026-09-11 23:15:29Z`。 |

# 任务一证据

审计快照：`2026-09-09T19:31:03Z`。静态值为 [`pool_meta.json:251`](/opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/pool_meta.json:251) 的 `0.4005191780352`，其 provenance 时间为 `08:49:23Z`。

- 观测数：29 条
- 时间跨度：`2026-09-09T12:35:53.244820Z` 至 `2026-09-09T19:30:02.215545Z`
- 持续时间：约 6h54m09s
- 最小值：`0.3556170337666176`
- 中位数：`0.366905052244224`
- 最大值：`0.4031180568728352`
- 漂移范围：`-11.21%` 至 `+0.65%`
- ±20% 阈值范围：`0.32041534242816` 至 `0.48062301364224`

小时聚合（漂移按该小时 gas 均值相对静态值计算）：

| UTC 小时 | 条数 | gas 均值 | 均值漂移 | 小时内最大绝对漂移 |
|---|---:|---:|---:|---:|
| 12:00 | 2 | 0.3777197714 | -5.69% | 5.71% |
| 13:00 | 4 | 0.3791097574 | -5.35% | 7.74% |
| 14:00 | 4 | 0.3709977535 | -7.37% | 8.33% |
| 15:00 | 4 | 0.3648841341 | -8.90% | 9.75% |
| 16:00 | 4 | 0.3646278492 | -8.96% | 9.89% |
| 17:00 | 4 | 0.3625397298 | -9.48% | 10.51% |
| 18:00 | 4 | 0.3646211177 | -8.96% | 11.21% |
| 19:00 | 3 | 0.3615850119 | -9.72% | 10.83% |

刷新阈值结果：

- 超过 ±20% 的观测：0 条
- 阈值触发事件：0 次
- 当前趋势：gas 大部分时间低于静态值，下午逐步从约 `-5%` 下移至约 `-9%`，但尚未接近刷新阈值。

仓库中已有刷新脚本：[`lp_rh_gas_refresh_v1_readonly.py`](/opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_gas_refresh_v1_readonly.py:153)。

其 `--apply` 路径：

- 仅当 verdict 为 `REFRESHED` 且新值为正数时写入。
- 修改指定的 `--pool-meta` 文件；若指向当前文件，就是 `reports/lp_rh/pool_meta.json`。
- 默认额外创建 `pool_meta.json.bak-<UTC时间戳>`。
- 在同目录创建临时文件，最后用 `os.replace` 原子替换目标文件。
- 不写 `gas_history.db`。
- 业务内容近似幂等：相同输入二次执行，除 `gas_provenance.computed_at` 外内容相同；但操作层面并非严格幂等，因为每次默认创建新备份、重新替换文件，文件 mtime/hash 会变化。
- 没有文件锁。daemon 作为读者不会读到半写 JSON，因为替换是原子的，通常会读到完整旧版本或完整新版本；但两个刷新写者并发时存在 last-writer-wins、备份时序不确定和 provenance 丢失风险。

shadow daemon 每 episode 重新读取文件的逻辑见 [`lp_rh_shadow_daemon_v1_readonly.py:104`](/opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_shadow_daemon_v1_readonly.py:104) 和 [`:274`](/opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_shadow_daemon_v1_readonly.py:274)。

# 任务二证据

审计快照：`2026-09-09T19:31:03Z`。

| 表 | 实际行数 |
|---|---:|
| `rh_market_states` | 8,879 |
| `rh_assets` | 194 |
| `rh_contract_attestations` | 387 |
| `rh_pool_registry` | 1 |
| `rh_source_snapshots` | 8,869 |

`rh_market_states`：

- 时间跨度：`2026-09-08T05:15:14.435446Z` 至 `2026-09-09T19:30:57.531469Z`
- 覆盖时长：`38h15m43.096023s`
- 相邻采样间隔中位数：`15.000115s`
- 大于 30 分钟的空洞：0 个

最大的 5 个实际间隔也都低于 30 分钟：

| 间隔 | 起点 | 终点 |
|---:|---|---|
| 271.00s | `2026-09-09T15:41:10.465532Z` | `15:45:41.465622Z` |
| 143.00s | `2026-09-09T15:38:47.465407Z` | `15:41:10.465532Z` |
| 79.00s | `2026-09-09T15:37:28.465305Z` | `15:38:47.465407Z` |
| 72.02s | `2026-09-08T06:22:26.950321Z` | `06:23:38.972574Z` |
| 66.71s | `2026-09-08T06:10:46.840816Z` | `06:11:53.550198Z` |

按中位采样速率推算：

| 目标覆盖 | 还需时间 | 预计 UTC 时刻 |
|---|---:|---|
| 72h | 约 33h44m17s | `2026-09-11T05:15:28Z` |
| 90h | 约 51h44m17s | `2026-09-11T23:15:29Z` |

逐列非空率（按 `IS NOT NULL` 统计；未发现空字符串）：

`rh_market_states`，共 8,879 行：

| 列 | 非空率 |
|---|---:|
| `asset_address` | 100.00% |
| `sample_time` | 100.00% |
| `chain_id` | 100.00% |
| `source_payload_hash` | 100.00% |
| `session` | 100.00% |
| `health_flags_json` | 100.00% |
| `reference_bid` | 0.00% |
| `reference_ask` | 0.00% |
| `reference_mid` | 99.45% |
| `reference_age_secs` | 99.32% |
| `multiplier_human` | 0.00% |
| `oracle_paused` | 0.00% |
| `derived_block_hash` | 24.95% |
| `derived_block_number` | 25.12% |
| `source_event_time` | 22.63% |
| `fee_growth_global_0` | 9.24% |
| `fee_growth_global_1` | 9.24% |

低于 50% 的列：

`reference_bid`、`reference_ask`、`multiplier_human`、`oracle_paused`、`derived_block_hash`、`derived_block_number`、`source_event_time`、`fee_growth_global_0`、`fee_growth_global_1`。

`rh_assets`，共 194 行：

| 列 | 非空率 |
|---|---:|
| `chain_id`、`address`、`metadata_version`、`symbol_display`、`uid`、`underlying`、`decimals`、`multiplier_raw`、`status`、`capability_json`、`source_payload_hash`、`updated_at` | 均为 100.00% |

低于 50%：无。

`rh_pool_registry`，共 1 行：

| 列 | 非空率 |
|---|---:|
| `chain_id`、`protocol`、`pool_key`、`pool_address` | 100.00% |
| `pool_id` | 0.00% |
| `token0`、`token1`、`fee`、`tick_spacing` | 100.00% |
| `hooks` | 0.00% |
| `attestation_status`、`discovered_at` | 100.00% |

低于 50%：`pool_id`、`hooks`。

与 [`COLUMN_HEALTH_SCAN_20260909.md:195`](/opt/lpbot/lp-bot-v3-origin-check/reports/rh_pivot/20260907T124500Z/COLUMN_HEALTH_SCAN_20260909.md:195) 对照：

- 初始扫描为 23 个 EMPTY 列，行数为旧快照的 `rh_market_states=6498`。
- 文档后续复扫已记录 `23 → 10`，见 [`:269`](/opt/lpbot/lp-bot-v3-origin-check/reports/rh_pivot/20260907T124500Z/COLUMN_HEALTH_SCAN_20260909.md:269)。
- 当前实际仍为 10 个 EMPTY 列，因此 EMPTY 数量与复扫基线一致，但行数和部分非空率已继续增长。
- 当前 10 个 EMPTY 为：`rh_market_states` 4 个、`rh_contract_attestations` 3 个、`rh_pool_registry` 2 个、`rh_source_snapshots.raw_ref` 1 个。
- 文档对剩余列的分类仍适用：`pool_id/hooks` 是 v4 概念；参考价相关列和 `oracle_paused` 需要设计或链上语义；attestation 三列及 `raw_ref` 属于语义未定义，不应直接伪填。

# 给主脑的建议

| 需用户授权才能做的 | 可直接做的 |
|---|---|
| 是否启用 gas 自动刷新并允许其写入 `pool_meta.json`。 | 继续保持 gas cron 采集，并按小时生成漂移监控。 |
| 是否为刷新脚本增加单写者锁或调度互斥，避免并发 `--apply`。 | 在达到 72h 和 90h 时重新做只读覆盖审计。 |
| 对 `reference_bid/ask/multiplier_human`、`oracle_paused`、attestation 三列及 `raw_ref` 作产品/数据语义决策。 | 保持未定义字段为 NULL，不为通过 EMPTY 扫描而填造值。 |
| 是否将 90h 覆盖作为 Stage A 毕业条件，以及是否还需满足 PRD 的 99% 门槛。 | 记录当前 10 个 EMPTY 列和低于 50% 的部分填充列，作为毕业前待决事项。 |