# Risk Signal Definition Fix V1

- data_source = vps_postgres
- db_ready = yes
- tested_signal_count = 7
- tested_combo_count = 16
- best_signal_combo = price_plus_exit_depth
- best_horizon = 1h
- best_proof_unit = pool_window
- best_window = recent_48h
- tail_improved_after_fix = yes
- risk_exit_helpful_after_fix = no
- quarantine_helpful = yes
- recommended_signal_mode = quarantine_first_price_volume_depth
- recommended_next_stage = POOL_REGIME_CLASSIFIER_V1
- tiny_canary_allowed = no
