# Quote Depth Coverage Failure Diagnosis

- `selected_pool_count_low`: `5` / `v1_pool_universe_only_7_and_required_entry_safe_snapshot` / model_artifact=`yes`
- `high_confidence_count_low`: `5` / `confidence_hardcoded_to_20usd_only` / model_artifact=`yes`
- `medium_confidence_count_low`: `5` / `confidence_hardcoded_to_100usd_only` / model_artifact=`yes`
- `low_confidence_count_high`: `15` / `all_500plus_forced_low` / model_artifact=`yes`
- `capacity_100_low`: `1` / `capacity_limit_capped_by_exit_depth20_proxy_around_33_to_63usd` / model_artifact=`yes`
- `capacity_500plus_zero`: `0` / `safe_capacity_formula_anchored_to_small_exit_depth_proxy` / model_artifact=`yes`
- `rejected_pools`: `2` / `entry_safe_snapshot_missing_or_non_base` / model_artifact=`partially`
- `expanded_universe_count`: `25` / `broadened_base_high_tvl_high_volume_pools` / model_artifact=`no`
