# Tier B Data Fix Counterfactual Readiness

- watch_pool_count: 77
- processed_pool_count: 16
- data_ready_count: 0
- research_candidate_count: 0
- shadow_only_data_ready_count: 0
- watch_count: 77
- reject_count: 0
- risk_signal_coverage: 0.7188
- position_lifecycle_data_available: true
- fixed_horizon_baseline_available: true
- can_run_counterfactual_now: false

未达标原因：
- 没有任何 `RESEARCH_CANDIDATE`。
- 16 个优先池里，stability 仍然只有 partial，无法把 risk signal coverage 推到 0.8 以上。
- 77 个 WATCH 池中，59 个在完整补数前就已经暴露硬风险，不适合直接进入 counterfactual。
