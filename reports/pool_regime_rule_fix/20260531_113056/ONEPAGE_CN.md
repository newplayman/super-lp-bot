# Pool Regime Rule Fix V1

- status: WARN
- entry_safe_classifier_built: yes
- same_bucket_features_banned: yes
- previous_closed_bucket_rule_applied: yes
- leakage_found_after_fix: no
- lookahead_risk_after_fix: LOW
- entry_safe_best_variant: entry_safe_enter_HEALTHY_or_STABLE_FEE
- entry_safe_best_window: recent_7d
- entry_safe_best_horizon: 2h
- entry_safe_tail_improved: yes
- tail_improvement_p10/p5/p1: 0.6139328805/1.3421482562/4.6716364959
- opportunity_retention_rate: 0.0962800875
- false_quarantine_rate: 0.6629213483
- missed_profit_rate: 0.3204584098
- robustness_status: WARN
- overfit_risk: MEDIUM
- recommended_next_stage: FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1
- tiny_canary_allowed: no
