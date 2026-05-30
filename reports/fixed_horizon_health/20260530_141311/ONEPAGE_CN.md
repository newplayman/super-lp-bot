# One Page

- data_source = `vps_postgres`
- db_ready = `yes`
- shadow_daemon_running = `yes`
- db_writes_fresh = `yes`
- decision_trace_rows_last_24h = `28042`
- selected_rows_last_24h = `5756`
- intent_open_rows_last_24h = `5607`
- new_positions_last_24h = `6`
- future_marks_coverage_status = `LOW_24H`
- materializer_status = `HEALTHY`
- root_cause = `INTENT_OPEN_EXISTS_BUT_NO_POSITION`, `POSITIONS_EXIST_BUT_NO_FUTURE_MARKS`, `HORIZONS_NOT_MATURE_YET`
- recommended_next_stage = `SHADOW_MARK_COVERAGE_FIX`
- tiny_canary_allowed = `no`
