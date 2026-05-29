# Tier C Sample Accumulation Plan

- scope: MICRO_CANDIDATE + WATCH only
- exclude: REJECT
- proof_unit: position_lifecycle
- horizons: 15m / 30m / 1h / 2h / 6h

## Plan

1. Continue read-only shadow observation of the 1 MICRO_CANDIDATE pool and 3 WATCH pools.
2. On each run, check whether any candidate pool has moved from `shadow_decision_trace` only into actual `positions` / `shadow_position_marks` / `shadow_exit_decisions`.
3. If candidate pool positions appear, emit position-level OOS rows with fixed horizons only.
4. If positions still do not appear, keep the phase in SAMPLE_INSUFFICIENT and treat the blocker as `not_selected_score_lt_60` / shadow top-cutoff exclusion.

## Success Condition for Next Stage

- At least 1 candidate pool with non-zero `positions`.
- Corresponding `shadow_position_marks` and `shadow_exit_decisions` exist.
- position_count >= 10 before any EARLY interpretation.

## Current State

- candidate_pool_count_for_oos: 4
- position_count: 0
- sample_sufficiency: INSUFFICIENT
- edge_proven: no
- tiny_canary_allowed: no