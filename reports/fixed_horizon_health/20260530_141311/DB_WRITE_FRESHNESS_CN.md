# DB Write Freshness

- `shadow_decision_trace` total=399732 latest=`2026-05-30 14:19:39+00:00` 2h=2400 6h=7200 12h=14381 24h=28042 48h=73311 status=`HEALTHY`
- `shadow_position_marks` total=54129 latest=`2026-05-30 14:20:07+00:00` 2h=481 6h=1441 12h=2882 24h=5766 48h=11532 status=`HEALTHY`
- `positions` total=68 latest=`2026-05-30 12:34:45+00:00` 2h=1 6h=1 12h=2 24h=6 48h=12 status=`HEALTHY`
- `shadow_exit_decisions` total=53976 latest=`2026-05-30 14:20:07.445000+00:00` 2h=480 6h=1440 12h=2880 24h=5760 48h=11520 status=`HEALTHY`
- `shadow_exit_actions` total=67 latest=`2026-05-30 12:34:09.735000+00:00` 2h=1 6h=1 12h=2 24h=6 48h=12 status=`HEALTHY`
- `shadow_outcome_labels` total=734863 latest=`2026-05-27 07:35:59.024000+00:00` 24h=0 48h=0 status=`STALE`
- `shadow_position_lifecycle_proof_v2` total=408 latest=`2026-05-30 14:06:54.987561+00:00` 2h=408 6h=408 12h=408 24h=408 48h=408 status=`HEALTHY`

判断：

- `shadow_decision_trace` 在增长，说明 shadow 选择链路仍在产出 trace。
- `positions` 在增长，但 24h 只新增 `6` 个，样本增长速度很慢。
- `shadow_position_marks` 在增长，说明 mark worker 没停。
- `shadow_position_lifecycle_proof_v2` 的增长是 materializer 重跑写入，不代表 fresh OOS 自然增长。
- 所有关键运行表都不是 stale，所以本轮不能把根因归到 `SHADOW_DAEMON_NOT_RUNNING` 或 `SHADOW_DB_WRITES_STALE`。
