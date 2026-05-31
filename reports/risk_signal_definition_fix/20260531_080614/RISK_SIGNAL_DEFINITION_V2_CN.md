# Risk Signal Definition V2

- accepted_signals: tvl_drop, exit_depth_drop, pool_mark_gap / stale data
- rejected_signals: price_spike_down, price_spike_up, volume_collapse, abnormal_volume_spike
- exit_signals: none
- hybrid_signals: quarantine-first only
- signal_debounce_rule: consecutive_trigger_required
- data_stale_handling: quarantine_no_entry
- per_horizon_recommendation: 15m=quarantine_only, 30m=quarantine_only, 1h=quarantine_first_price_volume_depth, 2h=quarantine_first_price_volume_depth
- per_proof_unit_recommendation: pool_window=quarantine_first_price_volume_depth, intent_window=quarantine_only
