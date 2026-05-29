# LPBOT_STRATEGY_PORTFOLIO_STATUS

## current_full_strategy
- status = FAIL
- proof_unit = position_lifecycle
- blocker = position_level_tail_not_acceptable
- blocker = terminal_or_lifecycle_tail_risk
- blocker = trace_duplication_invalidated_decision_trace_proof
- allowed_next_action = no canary / no live / no micro
- recommended_action = frozen / no further canary work

## fixed_horizon_hypothesis
- status = collecting_oos
- proof_unit = position_lifecycle
- sample_status = insufficient
- blocker = recent_oos_position_count_insufficient
- recommended_action = continue fresh OOS accumulation

## tier_c_shadow_research
- status = batch_rejected
- blocker = holder_concentration_extreme
- blocker = trader_concentration_extreme
- blocker = no_micro_candidate
- blocker = no_shadow_only_data_ready
- recommended_action = rediscovery only after market change

- edge_proven = no
- tiny_canary_candidate = no
- tiny_canary_allowed = no
- recommended_primary_next_stage = FIXED_HORIZON_FRESH_OOS_ACCUMULATION