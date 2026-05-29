# ONEPAGE

- stage = FIXED_HORIZON_VPS_POSITION_LIFECYCLE_MATERIALIZATION_V1
- data_source = vps_postgres
- db_ready = no
- fixed_horizon_hypothesis = collecting_oos
- materialization = not run
- fixed_horizon_gate = FAIL
- edge_proven = no
- tiny_canary_allowed = no
- recommended_next_stage = FIXED_HORIZON_DB_OR_SCHEMA_FIX