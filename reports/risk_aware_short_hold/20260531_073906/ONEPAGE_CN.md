# Risk Aware Short Hold Counterfactual V1

- data_source = vps_postgres
- db_ready = yes
- proof_units_tested = pool_window, intent_window
- horizons_tested = 15m, 30m, 1h, 2h
- valid_sample_count = 21655
- tail_improved = no
- risk_exit_helpful = no
- no_entry_quarantine_helpful = yes
- fee_proxy_sufficient = yes
- data_quality_sufficient = yes
- false_exit_rate = 0.0022
- missed_profit_rate = 0.0067
- best_window = recent_72h
- best_horizon = 30m
- best_proof_unit = pool_window
- recommended_next_stage = RISK_SIGNAL_DEFINITION_FIX
- tiny_canary_allowed = no
