# Entry-Safe Fee Velocity Policy

- `sample_start_time`: `entry decision time`
- `feature_cutoff_time_rule`: `feature_cutoff_time <= sample_start_time`
- `previous_fully_closed_bucket_rule`: `True`
- `banned_future_data`
- allowed_fee_features:
  - `previous bucket volume x fee tier from shadow_position_marks current_vol24h_usd/current_tvl_usd`
  - `previous bucket pool_score_history FeeAPRScore`
  - `previous bucket cached volume proxy only as low confidence fallback`
- diagnostic_only_fee_features:
  - `realized fee after sample_start`
  - `future volume`
  - `same bucket incomplete volume`
  - `unknown timestamp fee`
- confidence_levels:
  - `high`: `timestamp-safe mark volume x fee tier with stable recent coverage`
  - `medium`: `score_history or mark-volume proxy with partial coverage`
  - `low`: `external cached approximation or stale/incomplete data`
