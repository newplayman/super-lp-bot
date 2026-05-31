# Entry Safe Regime Feature Policy

- sample_start_time: counterfactual entry timestamp from risk_aware_short_hold_counterfactual_v1.start_time
- classifier_feature_cutoff_time: previous fully closed 15m bucket_end, always <= sample_start_time
- previous_closed_bucket_rule: for each sample_start use bucket_end = floor(sample_start/15m); features are computed from bucket [bucket_end-15m, bucket_end], never same bucket as sample_start
- allowed_features_for_entry_safe_classifier: previous bucket price_move_5m/15m/30m/1h, previous bucket volume_change_15m/30m/1h, previous bucket tvl_change_1h, previous bucket exit_depth and slippage approximations, previous bucket stale_data_flag, previous bucket data_quality_score, previous bucket fee_proxy
- banned_features: same bucket price / volume / tvl / stale data computed at bucket_end after sample_start, target horizon outcome, future mark after sample_start, any feature requiring data after sample_start
- diagnostic_only_features: security_score_latest, concentration_proxy_latest, same_bucket features until timestamp safe
