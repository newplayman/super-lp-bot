# Position Mark Repair Plan

## Goal

在不覆盖原始 `shadow_position_marks` 的前提下，设计独立研究层表：`shadow_position_marks_repaired_v2`，显式表达不同 outcome 语义。

## Proposed Table

```sql
CREATE TABLE shadow_position_marks_repaired_v2 (
  id TEXT PRIMARY KEY,
  repair_version TEXT NOT NULL,
  decision_trace_id TEXT NOT NULL,
  horizon TEXT NOT NULL,
  pool_id TEXT NOT NULL,
  position_id TEXT,
  target_time BIGINT NOT NULL,
  outcome_type TEXT NOT NULL,
  mark_provenance TEXT NOT NULL,
  mark_confidence TEXT NOT NULL,

  original_mark_id BIGINT,
  original_mark_time BIGINT,
  original_mark_source TEXT,

  terminal_mark_time BIGINT,
  terminal_mark_source TEXT,
  terminal_exit_decision_time BIGINT,
  terminal_exit_action_time BIGINT,
  terminal_exit_reason TEXT,

  reconstructed_mark_time BIGINT,
  reconstructed_mark_source TEXT,
  reconstructed_from TEXT,

  pool_mark_time BIGINT,
  pool_mark_source TEXT,

  net_pnl_usd NUMERIC,
  net_pnl_pct NUMERIC,
  mark_gap_seconds BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);
```

## outcome_type

- `future_position_mark`
- `terminal_exit_mark`
- `reconstructed_position_mark`
- `pool_mark_only`

## Rules

- `future_position_mark`:
  - allowed in edge proof when lineage trusted and mark_time >= target_time
- `terminal_exit_mark`:
  - allowed in edge proof only when `shadow_exit_decision` and `shadow_exit_action` are auditable, and terminal pnl fields are complete
- `reconstructed_position_mark`:
  - research-only by default; must not silently enter edge proof
- `pool_mark_only`:
  - never allowed in edge proof
- `only_pre_target_mark`:
  - never allowed in edge proof

## Provenance Split

- original fields come from `shadow_position_marks`
- terminal fields come from `shadow_exit_decisions`, `shadow_exit_actions`, and closed-position marks
- reconstructed fields come from research-only lineage recovery logic
- pool-only fields come from pool-level fallback and are explicitly non-proof

## Non-goals

- no overwrite of `shadow_position_marks`
- no overwrite of `shadow_outcome_labels`
- no live/canary execution
- no strategy or scoring changes
