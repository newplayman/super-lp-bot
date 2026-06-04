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

## lp_real_data_reopen

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_real_data_reopen/20260601_112642`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_real_data_reopen/20260601_112642/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: real-data reopen prep 设计完成，但尚未形成可重开 economics 的真实数据集。

## lp_precise_quote

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_precise_quote/20260601_120001`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_precise_quote/20260601_120001/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: precise quote read-only pipeline 已打通。

## lp_v3_tick_liquidity

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_v3_tick_liquidity/20260601_130245`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_v3_tick_liquidity/20260601_130245/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: v1 只完成部分覆盖，后续进入 fix repeat。

## lp_v3_tick_liquidity_fix

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_v3_tick_liquidity_fix/20260601_132644`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_v3_tick_liquidity_fix/20260601_132644/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: 标准 V3 tick-liquidity 高置信快照已补齐。

## lp_real_cost_model

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_real_cost_model/20260601_141103`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_real_cost_model/20260601_141103/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: real cost model 打通后出现 `6` 个 positive proxy，但 fee 成为主阻断。

## lp_real_fee_accrual

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_real_fee_accrual/20260601_143401`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_real_fee_accrual/20260601_143401/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: pool-level / simulated fee 可用，但 actual fee lineage 缺失。

## lp_real_fee_accrual_fix

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_real_fee_accrual_fix/20260601_145519`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_real_fee_accrual_fix/20260601_145519/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: tokenId 无法从现有历史数据恢复，strict probe readiness 不通过，转 STOP。

## lp_real_data_final_freeze

- latest report dir: `/Users/bendu/lp-bot/v3/reports/lp_real_data_final_freeze/20260601_150954`
- final verdict path: `/Users/bendu/lp-bot/v3/reports/lp_real_data_final_freeze/20260601_150954/FINAL_VERDICT.json`
- status: `PASS`
- one-line conclusion: real-data reopen 研究线正式收口，保持 `STOP_LP_RESEARCH_NOW`。

## lp_meteora_dlmm_targeted_top_pool_feed

- latest report dir: `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913`
- final verdict path: `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 56 verified, 27 quote-ready, best cell +$0.544 (zero_il_lvr), positive_realistic=0; recommend next: Orca.

## lp_orca_whirlpool_readonly_connector

- latest report dir: `reports/lp_orca_whirlpool_readonly_connector/20260604_025414`
- final verdict path: `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 75 verified, 10 quote-ready, best cell +$0.106 (zero_il_lvr), positive_realistic=0; tick array LAZY init.

## lp_raydium_clmm_readonly_connector

- latest report dir: `reports/lp_raydium_clmm_readonly_connector/20260604_034503`
- final verdict path: `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 65 verified, 50 quote-ready (liquidity ratio heuristic), best cell +$0.167 (zero_il_lvr), positive_realistic=0.

## lp_raydium_cpmm_readonly_connector

- latest report dir: `reports/lp_raydium_cpmm_readonly_connector/20260604_040952`
- final verdict path: `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 81 verified, 73 quote-ready, best cell +$0.172 (zero_il_lvr), positive_realistic=0; AMM v4 (675kPX9MHT) is the only deployed constant-product Raydium on mainnet; new cp-swap pid CPMMoo8L... NOT on mainnet.

## lp_solana_stable_pool_research

- latest report dir: `reports/lp_solana_stable_pool_research/20260604_044118`
- final verdict path: `reports/lp_solana_stable_pool_research/20260604_044118/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: 25 verified (all Orca LST-stable), 10 quote-ready, best cell +$0.204 (mSOL/USDC zero_il_lvr), positive_realistic=0; Meteora DAMM v2 API mislabels Orca pools; recommend next: STOP_LP_RESEARCH_NOW.

## lp_research_final_freeze (FINAL FREEZE)

- latest report dir: `reports/lp_research_final_freeze/20260604_051254`
- final verdict path: `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json`
- status: `WARN`
- one-line conclusion: **LP Research Final Freeze** — 5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP. Cumulative 28560 EV cells, 1898 positive in zero_il_lvr only, 0 in optimistic/realistic/conservative. Best cell $0.544 (Meteora DLMM memecoin). Overall recommendation: **STOP_LP_RESEARCH_NOW**. can_run_probe_now=false, tiny_canary_allowed=no, edge_proven=no. Reopen conditions documented. 12 reusable modules preserved.
