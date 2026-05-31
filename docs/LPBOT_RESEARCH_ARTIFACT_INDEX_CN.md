# LPBOT 研究工件索引

## portfolio_status

- latest report dir: `/Users/bendu/lp-bot/v3/reports/portfolio_status/20260529_160811`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/portfolio_status/20260529_160811/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: 已统一归档 current_full_strategy FAIL、fixed_horizon collecting_oos、Tier C 非主线。

## fixed_horizon

- latest report dir: `/Users/bendu/lp-bot/v3/reports/fixed_horizon_policy/20260530_145208`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/fixed_horizon_policy/20260530_145208/FINAL_VERDICT.json`
- status: `FAIL`
- one-line conclusion: fixed-horizon position lifecycle 没有形成可继续的主线 proof。

## materializer_semantics

- latest report dir: `/Users/bendu/lp-bot/v3/reports/materializer_classification/20260531_044242`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/materializer_classification/20260531_044242/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: terminal_before_target 被错误归入 no_future_mark 的语义问题已修正。

## shadow_mark_coverage

- latest report dir: `/Users/bendu/lp-bot/v3/reports/shadow_mark_coverage/20260531_042501`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/shadow_mark_coverage/20260531_042501/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: mark worker 不是主因，核心问题是 materializer classification。

## intent_lifecycle

- latest report dir: `/Users/bendu/lp-bot/v3/reports/intent_lifecycle_dedup/20260531_061138`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/intent_lifecycle_dedup/20260531_061138/FINAL_VERDICT.json`
- status: `FAIL`
- one-line conclusion: DQ 和 dedup 修完后仍无 review-ready signal。

## tierb

- latest report dir: `/Users/bendu/lp-bot/v3/reports/tierb_data_fix/20260530_125453`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/tierb_data_fix/20260530_125453/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: Tier B 当前没有可继续推进的研究候选。

## tierc

- latest report dir: `/Users/bendu/lp-bot/v3/reports/tierc_shadow/20260529_155854`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/tierc_shadow/20260529_155854/TIER_C_BATCH_FINAL_FREEZE_VERDICT.json`
- status: `PASS`
- one-line conclusion: Tier C batch 已冻结为 rejected，只能等待市场变化后 rediscovery。

## risk_aware_short_hold

- latest report dir: `/Users/bendu/lp-bot/v3/reports/risk_aware_short_hold/20260531_073906`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/risk_aware_short_hold/20260531_073906/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: risk exit 不 helpful，只有 quarantine 有帮助。

## pool_regime_classifier

- latest report dir: `/Users/bendu/lp-bot/v3/reports/pool_regime_classifier/20260531_092109`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/pool_regime_classifier/20260531_092109/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: regime classifier 有尾部解释力，但不是独立可交易策略。

## pool_regime_aware_short_hold

- latest report dir: `/Users/bendu/lp-bot/v3/reports/pool_regime_aware_review/20260531_110005`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/pool_regime_aware_review/20260531_110005/FINAL_VERDICT.json`
- status: `FAIL`
- one-line conclusion: leakage 修正后仍然过筛过重，机会保留太低。

## fee_velocity_exit_depth

- latest report dir: `/Users/bendu/lp-bot/v3/reports/fee_velocity_rule_fix/20260531_122413`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/fee_velocity_rule_fix/20260531_122413/FINAL_VERDICT.json`
- status: `FAIL`
- one-line conclusion: P2 无任何 practical variant 通过，研究线停止。

## final_freeze

- latest report dir: `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: LP 策略研究正式冻结，推荐 `STOP_LP_RESEARCH_NOW`。
