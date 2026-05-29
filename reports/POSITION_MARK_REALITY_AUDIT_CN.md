# Position Mark Reality Audit

- workspace: `/opt/lpbot/lp-bot-v3-origin-check`
- snapshot: `clean_remote_repaired_v2_20260528_0902`
- source: `shadow_outcome_labels_repaired_v2` + `shadow_position_marks` + `shadow_decision_trace`
- original tables overwritten: no

## Horizon Summary

| Horizon | selected/intended_open | position_id present | entry position mark exists | future position mark exists | pool_mark_only | position_mark_outside_window | position_mark_missing | position_id_join_failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6h | 26275 | 26191 | 26052 | 20508 | 5683 | 5683 | 0 | 84 |
| 24h | 24485 | 24401 | 24264 | 10354 | 14047 | 14047 | 0 | 84 |

## Nearest Future Position Mark Distance

| Horizon | p50 hours | p90 hours | p99 hours | max hours |
| --- | ---: | ---: | ---: | ---: |
| 6h | 0.008 | 0.041 | 10.178 | 11.028 |
| 24h | 0.008 | 0.017 | 0.295 | 1.383 |

## pool_mark_only by Pair Bucket

| Horizon | Pair Bucket | pool_mark_only samples |
| --- | --- | ---: |
| 6h | WETH/USDC | 3079 |
| 6h | cbBTC/WETH | 909 |
| 6h | USAD/USDT | 894 |
| 6h | cbBTC/USDC | 801 |
| 24h | WETH/USDC | 6712 |
| 24h | cbBTC/USDC | 2786 |
| 24h | cbBTC/WETH | 2369 |
| 24h | USAD/USDT | 2089 |
| 24h | 其他 | 91 |

## Root Cause Judgment

| Horizon | Primary root cause | Secondary root cause | Evidence | SQL_join_condition_error |
| --- | --- | --- | --- | --- |
| 6h | window_too_narrow | only_pool_mark_available | `position_mark_outside_window = pool_mark_only = 5683`, `position_mark_missing = 0`, `position_id_join_failed = 84` | no evidence |
| 24h | window_too_narrow | only_pool_mark_available | `position_mark_outside_window = pool_mark_only = 14047`, `position_mark_missing = 0`, `position_id_join_failed = 84` | no evidence |

## Interpretation

- repaired_v2 的主缺口不是 token decimals，也不是 strict-valid 元数据；而是 target_time 之后拿不到 position-level future mark。
- `position_mark_missing = 0` 说明不是“position mark 根本没写入”。
- `position_mark_outside_window == pool_mark_only` 说明失败样本大多已经有同一 `position_id` 的 mark，但 mark 落在 `target_time` 之前，因此被当前 strict reality 语义排除。
- 少量 `position_id_join_failed` 仍然存在，但量级远小于 mark 覆盖问题。
