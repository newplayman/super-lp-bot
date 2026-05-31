# 输入工件审计

| input | exists |
|---|---|
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FINAL_VERDICT.json` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FEE_EXIT_COUNTERFACTUAL_REPORT_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/fee_exit_counterfactual_report.csv` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FEE_EXIT_BEST_VARIANT_SELECTION_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/fee_exit_best_variant_selection.json` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/SMALL_CAPACITY_AUDIT_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/small_capacity_audit.csv` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FEE_EXIT_VS_REGIME_AWARE_COMPARISON_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/fee_exit_vs_regime_aware_comparison.csv` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FEE_EXIT_ROBUSTNESS_AUDIT_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/fee_exit_robustness_audit.csv` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/FEE_EXIT_NEXT_STAGE_DECISION_CN.md` | yes |
| `/tmp/fee_rule_repo/reports/fee_velocity_exit_depth/20260531_115101/fee_exit_next_stage_decision.json` | yes |
| `/tmp/fee_rule_repo/reports/pool_regime_rule_fix/20260531_113056/FINAL_VERDICT.json` | yes |
| `/tmp/fee_rule_repo/reports/pool_regime_aware_review/20260531_110005/FINAL_VERDICT.json` | yes |
| `/tmp/fee_rule_repo/reports/risk_signal_definition_fix/20260531_080614/FINAL_VERDICT.json` | yes |
| `/tmp/fee_rule_repo/reports/new_strategy_hypothesis/20260531_071724/FINAL_VERDICT.json` | yes |

- 上轮 stage 是否正确: `yes`
- 上轮 recommended_next_stage 是否为 FEE_VELOCITY_RULE_FIX: `yes`
- opportunity retention 过低: `yes`
- false_filter / missed_profit 过高: `yes` / `yes`
- fee_minus_exit_cost 为负: `yes`
- 足够执行 rule fix: `yes`
- 当前不硬判 edge。
