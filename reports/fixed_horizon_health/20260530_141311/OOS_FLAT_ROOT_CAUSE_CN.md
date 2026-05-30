# OOS Flat Root Cause

- `INTENT_OPEN_EXISTS_BUT_NO_POSITION`
  - table=`shadow_decision_trace` / `positions`
  - metric=`intent_open_rows_last_24h` vs `new_positions_last_24h`
  - time_window=`24h`
  - observed=`5607 intent_open` vs `6 new positions`

- `POSITIONS_EXIST_BUT_NO_FUTURE_MARKS`
  - table=`shadow_position_lifecycle_proof_v2`
  - metric=`position_with_future_6h/12h/24h_mark_count`
  - time_window=`24h`
  - observed=`0 / 0 / 0` for `6` new positions

- `HORIZONS_NOT_MATURE_YET`
  - table=`positions` / `shadow_position_lifecycle_proof_v2`
  - metric=`new_positions_last_24h` vs `future_24h_mark_count`
  - time_window=`24h`
  - observed=`6 new positions`, `0 future 24h marks`

non-root-cause exclusions:

- `SHADOW_DAEMON_NOT_RUNNING`: excluded, process is active for ~5 days
- `SHADOW_DB_WRITES_STALE`: excluded, trace/marks/positions all growing in last 24h
- `DECISION_TRACE_EXISTS_BUT_NO_SELECTED`: excluded, `selected_rows_last_24h = 5756`
- `SELECTED_EXISTS_BUT_NO_INTENT_OPEN`: excluded, `intent_open_rows_last_24h = 5607`
- `MATERIALIZER_BUG`: not primary evidence; materializer produced clean run_ids `20260530_134500` and `20260530_140551` with no duplicates
