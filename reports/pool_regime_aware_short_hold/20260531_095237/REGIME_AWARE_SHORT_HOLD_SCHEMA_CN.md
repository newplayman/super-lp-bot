# Regime Aware Short Hold Schema

- target_table: pool_regime_aware_short_hold_counterfactual_v1
- fields: run_id, variant_name, sample_id, proof_unit_type, pool_id, token_pair, window, horizon, bucket_start, bucket_end, regime_primary, regime_secondary, regime_confidence, entry_allowed, quarantine_reason, entry_value, target_value, fee_proxy, exit_cost_proxy, hold_to_horizon_pnl_pct, regime_filtered_pnl_pct, opportunity_retained, loss_avoided, missed_profit, false_quarantine_flag, data_quality_status, invalid_reason, created_at
- scope: research-only
- proof_unit_priority: pool_window, then intent_window
- tiny_canary_allowed: no
