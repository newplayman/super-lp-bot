# RISK_AWARE_EXIT_COUNTERFACTUAL_SPEC

比较三条路径：
1. fixed_horizon: 持有到 6h / 12h / 24h
2. current_terminal_exit: 当前老退出逻辑
3. risk_aware_exit_v0: 第一次触发风险信号时退出，未触发则持有到 fixed horizon

每个 position_lifecycle 输出字段：
- position_id
- tier
- pool_id
- token_pair
- entry_time
- horizon
- fixed_horizon_pnl_pct
- current_terminal_pnl_pct
- risk_aware_exit_pnl_pct
- risk_exit_time
- risk_exit_reason
- loss_saved_vs_fixed
- loss_saved_vs_current_terminal
- missed_profit_after_exit
- false_exit_flag
- data_quality_status

- proof_unit = position_lifecycle only
- decision_trace 不作为主样本
- risk-aware 结果不允许直接推进 canary