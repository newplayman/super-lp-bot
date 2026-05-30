# VPS Fixed Horizon Schema Audit

| table | exists | row_count | latest_timestamp |
|---|---:|---:|---|
| `shadow_decision_trace` | yes | 399212 | `1780149219` |
| `shadow_position_marks` | yes | 54025 | `1780149247` |
| `positions` | yes | 68 | `1780144485` |
| `shadow_exit_decisions` | yes | 53872 | `1780149247554` |
| `shadow_exit_actions` | yes | 67 | `1780144449735` |
| `shadow_outcome_labels` | yes | 734863 | `1779867359024` |
| `shadow_outcome_labels_repaired_terminal_v1` | yes | 50760 | `1779964434` |
| `shadow_terminal_position_marks_repaired_v1` | yes | 19730 | `` |
| `shadow_position_lifecycle_proof_v1` | yes | 68 | `1779985075` |
| `shadow_position_lifecycle_proof_v2` | yes | 204 | `2026-05-30 13:52:44.635927+00:00` |

- enough_to_materialize_6h: `yes`
- enough_to_materialize_12h: `yes`
- enough_to_materialize_24h: `yes`
- basis:
  - `positions` 有 68 条 lifecycle 主样本
  - `shadow_position_marks` 最新 mark 已覆盖到当前 run
  - `shadow_position_lifecycle_proof_v2` 本轮已写入 `68 * 3 = 204` 行
  - 本轮 valid future mark 数量：
    - `6h = 42`
    - `12h = 40`
    - `24h = 8`

- caveat:
  - `24h` 可物化，但完成样本仍偏少，只够支持 `INSUFFICIENT` 结论，不足以判 edge。
