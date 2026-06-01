# Entry-Safe IL/LVR Policy

- `sample_start_time`: `quote_depth_curve_v2.feature_cutoff_time`
- `feature_cutoff_time`: `<= sample_start_time`
- `previous_fully_closed_bucket_rule`: `True`
- `same_bucket_features_banned`: `True`
- `banned_future_data`: `['future realized IL after sample_start', 'target horizon outcome', 'post-entry price path', 'exact LP pnl after horizon']`
- `allowed_features`: `['previous bucket realized volatility proxy', 'previous bucket price movement proxy', 'previous bucket risk/adverse movement proxy', 'pool type known before entry']`

- confidence `high`: `exact position or range known and timestamp safe`
- confidence `medium`: `pool type plus entry-safe volatility proxy`
- confidence `low`: `generic volatility fallback`
