# 输入工件审计

| input | exists |
|---|---|
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/POOL_REGIME_RULE_FIX_DECISION_CN.md` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/ENTRY_SAFE_REGIME_FEATURE_POLICY_CN.md` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/ENTRY_SAFE_REGIME_AWARE_COUNTERFACTUAL_CN.md` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/entry_safe_regime_aware_counterfactual.csv` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/LEAKY_VS_ENTRY_SAFE_COMPARISON_CN.md` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/leaky_vs_entry_safe_comparison.csv` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/ENTRY_SAFE_ROBUSTNESS_AUDIT_CN.md` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_rule_fix/20260531_113056/entry_safe_robustness_audit.csv` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_aware_review/20260531_110005/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_aware_short_hold/20260531_095237/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/pool_regime_classifier/20260531_092109/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/risk_signal_definition_fix/20260531_080614/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/risk_aware_short_hold/20260531_073906/FINAL_VERDICT.json` | yes |
| `/tmp/fee_exit_repo/reports/new_strategy_hypothesis/20260531_071724/FINAL_VERDICT.json` | yes |

- 上轮 stage 确认: `yes`
- leakage_found_after_fix: `no`
- recommended_next_stage 确认: `yes`
- regime-aware 保留率过低: `yes`
- regime-aware 误杀率过高: `yes`
- regime-aware missed profit 过高: `yes`
- 足够执行 fee velocity / exit depth counterfactual: `yes`
- 当前只做 research-only 审计，不硬判 edge。
