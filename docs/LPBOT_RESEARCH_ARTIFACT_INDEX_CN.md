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

## lp_scale_economics

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_scale_economics/20260601_082100`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_scale_economics/20260601_082100/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 新 LP scale economics 研究框架定义完成，但 first-pass data readiness 仅为 `PARTIAL`。

## lp_data_pipeline

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_data_pipeline/20260601_084943`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_data_pipeline/20260601_084943/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: quote/depth、fee velocity、entry-safe snapshot 路径均可行，但尚未达到 economics 可运行条件。

## lp_quote_depth_curve

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_quote_depth_curve/20260601_090437`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_quote_depth_curve/20260601_090437/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: quote/depth v1 已建成，但 coverage/confidence 不足，不能直接进入 virtual notional。

## lp_quote_depth_curve_fix

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_quote_depth_curve_fix/20260601_091739`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_quote_depth_curve_fix/20260601_091739/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: quote/depth v2 将 data-ready 池提升到 14 个，满足 virtual notional 前置条件。

## lp_virtual_notional_economics

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_virtual_notional_economics/20260601_094238`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_virtual_notional_economics/20260601_094238/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 25 池、500 行 economics 结果里 `positive_proxy_count = 0`，最优 20U 仍为负 EV。

## lp_fee_velocity_pipeline

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_fee_velocity_pipeline/20260601_100642`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_fee_velocity_pipeline/20260601_100642/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: fee pipeline 跑通且 EV 略改善，但无任何 positive proxy，阻断转向 fixed cost。

## lp_fee_velocity_fix_repeat

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_fee_velocity_fix_repeat/20260601_103248`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_fee_velocity_fix_repeat/20260601_103248/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 即使 `fixed_cost = 0` 仍无 positive proxy，主阻断收敛为 `data_confidence_low`。

## lp_il_lvr_pipeline

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_il_lvr_pipeline/20260601_105452`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_il_lvr_pipeline/20260601_105452/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 即使 `IL/LVR = 0` 仍无 positive proxy，scale economics 新线正式收敛到 `STOP_LP_RESEARCH_NOW`。

## lp_scale_final_freeze

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_scale_final_freeze/20260601_110649`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_scale_final_freeze/20260601_110649/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: 新 LP scale economics 研究线完成最终冻结和 handoff，不再继续 probe/canary/live。
