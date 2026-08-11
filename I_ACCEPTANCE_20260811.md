# TP-I P0 验收（2026-08-11）

提交顺序（仅提交，未推送）：

1. `650f355 i(fix-I1): evaluate stage2 netcover gate`
2. `392be05 i(fix-I2): filter dust swap price inputs`

## I1：真实 NetCover gate

Stage-2 现在先报告 `inputs_complete` / `inputs_reason`，再通过共享
`apply_netcover_gate` 产生 `netcover_ratio` / `netcover_pass` /
`netcover_reason`。`stage2_pass` 的第五个合取项为真正的
`netcover_pass`；没有新增或放宽阈值，继续使用共享
`NETCOVER_SHADOW=1.0`。

同池固定原始回放快照
`reports/lp_tp_h/20260811/h3a_aaplx_stage2_run3.json` 的纯重算结果：

```text
pool_id          = 9462784c-c0e5-4539-914e-ac006e5b3097 (AAPLX-USDC)
fee_ev_usd       = 0.009182465753424658
reward_ev_usd    = 0.0
netcover_ratio   = 0.02706561398934868
inputs_complete  = true
netcover_pass    = false
stage2_pass      = false
```

因此输入齐全不再会被误报为经济过闸。新增单测构造
`fee_ev << gas`，断言 `inputs_complete=True` 而
`netcover_pass=False`。

## I2：dust 与中位数稳健过滤

每笔 decoded vault delta 已是按 decimals 归一后的 UI 数量；两腿均需
超过 `max(1e-6 UI, reserve * 1e-9)`。否则在生成隐含价格前剔除并计入
`dropped_dust_swaps`。随后价格相对中位数偏离超过 10 倍的样本被剔除并
计入 `dropped_price_outlier_swaps`；该类剔除超过 20% 会使
`economic_price_complete=False`（fail-closed）。同一保护也在
`_replay_price_path` 中重施，避免旧快照或旁路调用污染 sigma、bar close、
`price_ratio_worst` 和 IL。

对上述固定原始回放重新执行新过滤：

```text
historical swaps              = 52
dropped_dust_swaps            = 9
kept economic swaps           = 43
dropped_price_outlier_swaps   = 0
cleaned swaps                 = 43
dropped_median_price_samples  = 1  # legacy raw path 的防御性二次保护
price_ratio_worst             = 1.0120494125665074
il_apr_pct                    = 0.6545174473291393
```

九笔低腿记录中，八笔本来没有可算价格；另一笔正是
`delta_a=-1e-08, delta_b=5000.0` 的 `5e11` 伪价格。清洗后的价格比在
个位数内，且接近预期的约 1.01。

本包也实际启动了 `--replay-limit 60` 的免费公共 Solana RPC 定向读取；
该环境的免费端点轮换在验收窗口内未完成，所以没有把它伪报为完成实跑。
以上数值来自该池已保存的原始链上回放快照，以纯函数重算，因而可复现。

## Base 固定快照不变性

固定快照 `h4_base_invariance` 的 Markdown 哈希相同。JSON 直接哈希不同
仅因 `generated_at` 与 `source.scanner_db` 的绝对/相对路径；删去这两个
非经济字段、排序后的两侧 SHA-256 均为：

```text
b85b51596a5e764c6e1e1c753a5b6e94451decd6b1bc5f01a5b9105ceed122e9
```

因此固定 Base 经济结果不变。

## 已知局限

当前约 6 小时采样属于盘中窗口，看不到隔夜跳空；而股票代币的重要风险
恰包括开盘跳空。本包如实保留该局限，未把它包装成已解决的风险。

## 全量测试原始输出

### `python3 -m pytest`

```text
$ python3 -m pytest
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-7.4.4, pluggy-1.4.0
rootdir: /opt/lpbot/lp-bot-v3-origin-check
configfile: pytest.ini
collected 3113 items

tests/test_base_m1_executor_c4.py ...................                    [  0%]
tests/test_collect_bsc_fee_velocity_overnight_artifacts.py .........     [  0%]
tests/test_d4_paper_position_integration.py ........                     [  1%]
tests/test_finalize_bsc_fee_velocity_overnight_run_v1_readonly.py ...... [  1%]
...........                                                              [  1%]
tests/test_inv_gate_02_terminal_conjunction.py .............             [  2%]
tests/test_lp_attribution_ledger_v2_readonly.py ............             [  2%]
tests/test_lp_base_10u_probe_armed_runner_monitor_v1.py ................ [  3%]
......................................                                   [  4%]
tests/test_lp_base_10u_probe_authorization_package_v1.py ............... [  4%]
..............................                                           [  5%]
tests/test_lp_base_10u_probe_execution_implementation_v1.py ............ [  6%]
..................                                                       [  6%]
tests/test_lp_base_10u_probe_executor_review_v1.py ....................  [  7%]
tests/test_lp_base_10u_probe_executor_review_v1_rerun.py ............... [  7%]
.......                                                                  [  7%]
tests/test_lp_base_10u_probe_executor_v1_build.py ...................... [  8%]
..................                                                       [  9%]
tests/test_lp_base_10u_probe_final_execution_review_v1.py .............. [  9%]
..............................                                           [ 10%]
tests/test_lp_base_10u_probe_monitor_finalize_go_nogo_v1.py ............ [ 11%]
.......................................                                  [ 12%]
tests/test_lp_base_10u_probe_operator_execution_request_v1.py .......... [ 12%]
..................................                                       [ 13%]
tests/test_lp_base_m1_c5_dry_run_v1_readonly.py ..                       [ 13%]
tests/test_lp_base_probe_dry_run_builder_v1_readonly.py ................ [ 14%]
.....                                                                    [ 14%]
tests/test_lp_base_probe_execution_spec_review_v1_readonly.py .......... [ 14%]
..................                                                       [ 15%]
tests/test_lp_base_sepolia_smoke_v1_readonly.py ........                 [ 15%]
tests/test_lp_bsc_fee_velocity_recovery_probe_preflight_v1_readonly.py . [ 15%]
....................                                                     [ 16%]
tests/test_lp_bsc_probe_dry_run_builder_v1_readonly.py ................. [ 16%]
.....                                                                    [ 17%]
tests/test_lp_bsc_probe_preflight_review_v1_readonly.py ................ [ 17%]
                                                                         [ 17%]
tests/test_lp_bsc_probe_wallet_address_dry_run_v1_readonly.py .......... [ 17%]
...........                                                              [ 18%]
tests/test_lp_c2_once_report_v1_readonly.py .                            [ 18%]
tests/test_lp_c6_preflight_v1_readonly.py ......                         [ 18%]
tests/test_lp_capital_tiers_v1_readonly.py ......                        [ 18%]
tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py .. [ 18%]
s...........................s.....s.ss....s                              [ 20%]
tests/test_lp_cost_sensitivity_v1_readonly.py .....                      [ 20%]
tests/test_lp_d2_window_discretization_v1.py ...                         [ 20%]
tests/test_lp_d5_c6_preflight_v1.py ......                               [ 20%]
tests/test_lp_defensive_exit_lower_replay_v1_readonly.py .....           [ 20%]
tests/test_lp_defensive_exit_replay_v1_readonly.py ......                [ 20%]
tests/test_lp_evm_wallet_crosschain_dry_run_router_v1_readonly.py ...... [ 21%]
.............                                                            [ 21%]
tests/test_lp_exit_policy_v1_readonly.py .............................   [ 22%]
tests/test_lp_funnel_autopsy_v1_readonly.py .....                        [ 22%]
tests/test_lp_funnel_rerank_v1_readonly.py .........................     [ 23%]
tests/test_lp_funnel_root_cause_diagnostics_v1_readonly.py .             [ 23%]
tests/test_lp_funnel_vet_v1_readonly.py .............                    [ 23%]
tests/test_lp_il_inventory_engine_v1_readonly.py ...................     [ 24%]
tests/test_lp_il_math_replay_v1_readonly.py ...                          [ 24%]
tests/test_lp_long_horizon_12h_finalize_and_node_report_v1.py .......... [ 24%]
................................                                         [ 25%]
tests/test_lp_long_horizon_12h_node_report_v1.py .....................   [ 26%]
tests/test_lp_long_horizon_6h_finalizer_rebuild_v1.py .................. [ 27%]
..............                                                           [ 27%]
tests/test_lp_long_horizon_collector_adapter_coverage_wiring_v1.py ..... [ 27%]
...........................                                              [ 28%]
tests/test_lp_long_horizon_node_report_generator_v1.py ................. [ 29%]
..................                                                       [ 29%]
tests/test_lp_long_horizon_partial_12h_node_report_review_v1.py ........ [ 30%]
...........                                                              [ 30%]
tests/test_lp_long_horizon_partial_12h_request_v1.py ................... [ 30%]
.........                                                                [ 31%]
tests/test_lp_long_horizon_r1_12h_full_wallclock_observation_v1.py ..... [ 31%]
...................                                                      [ 32%]
tests/test_lp_long_horizon_r1_12h_node_report_review_v1.py ............. [ 32%]
..................                                                       [ 33%]
tests/test_lp_long_horizon_r1_12h_real_data_observation_v1.py ...s...... [ 33%]
..........                                                               [ 33%]
tests/test_lp_long_horizon_r1_pause_and_freeze_record_v1.py ............ [ 34%]
...................                                                      [ 34%]
tests/test_lp_long_horizon_r1_real_data_observation_upgrade_v1.py ...... [ 34%]
................                                                         [ 35%]
tests/test_lp_long_horizon_readonly_12h_extension_request_v1.py ........ [ 35%]
......................                                                   [ 36%]
tests/test_lp_long_horizon_readonly_collector_6h_real_wallclock_v1.py .. [ 36%]
........................s....                                            [ 37%]
tests/test_lp_long_horizon_readonly_collector_6h_real_wallclock_v2.py .. [ 37%]
..................s....                                                  [ 38%]
tests/test_lp_long_horizon_readonly_collector_6h_run_approval_v1.py .... [ 38%]
..............................................s.........                 [ 40%]
tests/test_lp_long_horizon_readonly_collector_fix_repeat_v1.py ......... [ 40%]
.................................................s.......                [ 42%]
tests/test_lp_long_horizon_readonly_collector_smoke_v1.py .............. [ 42%]
..............s..                                                        [ 43%]
tests/test_lp_long_horizon_readonly_collector_staged_request_v1.py ..... [ 43%]
................................s.                                       [ 44%]
tests/test_lp_long_horizon_readonly_data_pipeline_v1.py ................ [ 44%]
.....................................s                                   [ 46%]
tests/test_lp_long_horizon_real_pool_universe_collector_fix_v1.py ...... [ 46%]
.....................                                                    [ 47%]
tests/test_lp_long_horizon_real_pool_universe_coverage_expand_v1.py .... [ 47%]
...................................                                      [ 48%]
tests/test_lp_long_horizon_rpc_reachability_adapter_smoke_fix_v1.py .... [ 48%]
..........................                                               [ 49%]
tests/test_lp_long_horizon_stage_supervisor_finalize_fix_v1.py ......... [ 49%]
.............                                                            [ 49%]
tests/test_lp_lvr_coefficient_calibration_v1_readonly.py ....            [ 50%]
tests/test_lp_m0n_income_validation_v1_readonly.py .....                 [ 50%]
tests/test_lp_meteora_dlmm_known_pool_connector_v1.py .................. [ 50%]
..........................................                               [ 52%]
tests/test_lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1.py ... [ 52%]
...........                                                              [ 52%]
tests/test_lp_meteora_dlmm_quote_binarray_coverage_expand_v1.py ........ [ 52%]
......................................................                   [ 54%]
tests/test_lp_meteora_dlmm_quote_binarray_coverage_expand_v2.py ........ [ 54%]
............................................                             [ 56%]
tests/test_lp_meteora_dlmm_quote_binarray_fix_v1.py .................... [ 56%]
.........................................                                [ 58%]
tests/test_lp_meteora_dlmm_sdk_connector_feasibility_v1.py ............. [ 58%]
...........................................                              [ 60%]
tests/test_lp_meteora_dlmm_survival_ev_preview_v1.py ................... [ 60%]
.................................                                        [ 61%]
tests/test_lp_meteora_dlmm_targeted_top_pool_feed_expansion_v1.py ...... [ 61%]
.............                                                            [ 62%]
tests/test_lp_multicall3_v1_readonly.py ......                           [ 62%]
tests/test_lp_multichain_survival_ev_v1_readonly.py .................... [ 63%]
............................................                             [ 64%]
tests/test_lp_multiwindow_stability_v1_readonly.py ........              [ 64%]
tests/test_lp_netcover_amm_dispatch_v1_readonly.py .............         [ 65%]
tests/test_lp_netcover_engine_v1_readonly.py ................            [ 65%]
tests/test_lp_netcover_inputs_v1_readonly.py ........................... [ 66%]
....................                                                     [ 67%]
tests/test_lp_orca_whirlpool_readonly_connector_v1.py .................. [ 67%]
                                                                         [ 67%]
tests/test_lp_panel_server_v1_readonly.py .............................. [ 68%]
..                                                                       [ 68%]
tests/test_lp_polymarket_competitor_collector_v1_readonly.py ........... [ 69%]
..........................................                               [ 70%]
tests/test_lp_pool_resolve_and_rank_v1_readonly.py ............          [ 70%]
tests/test_lp_portfolio_allocator_v1_readonly.py ................        [ 71%]
tests/test_lp_portfolio_paper_runner_solana_v1_readonly.py ............. [ 71%]
                                                                         [ 71%]
tests/test_lp_portfolio_paper_runner_v1_readonly.py .................... [ 72%]
...................................                                      [ 73%]
tests/test_lp_raydium_clmm_readonly_connector_v1.py ...................  [ 74%]
tests/test_lp_raydium_cpmm_readonly_connector_v1.py .................... [ 74%]
                                                                         [ 74%]
tests/test_lp_report_digest_v1_readonly.py .....                         [ 75%]
tests/test_lp_research_conclusion_scope_audit_v1.py .................... [ 75%]
.....................                                                    [ 76%]
tests/test_lp_research_final_freeze_handoff_v1.py ...................... [ 77%]
                                                                         [ 77%]
tests/test_lp_reward_decay_replay_v1_readonly.py ..........              [ 77%]
tests/test_lp_reward_observation_progress_v1_readonly.py ....            [ 77%]
tests/test_lp_reward_persistence_v1_readonly.py .....                    [ 77%]
tests/test_lp_rpc_pool_v1_readonly.py ............................       [ 78%]
tests/test_lp_rwa_anchors_v1_readonly.py ...........                     [ 78%]
tests/test_lp_rwa_collector_daemon_v1_readonly.py ..........             [ 79%]
tests/test_lp_rwa_instrument_v1_readonly.py .................            [ 79%]
tests/test_lp_rwa_session_v1_readonly.py ...........                     [ 80%]
tests/test_lp_scanner_daemon_v1_readonly.py ............................ [ 81%]
...................                                                      [ 81%]
tests/test_lp_shadow_gate_v1_readonly.py ..................              [ 82%]
tests/test_lp_solana_connector_design_v1_readonly.py ................... [ 82%]
.........................................                                [ 84%]
tests/test_lp_solana_readonly_rpc_registry_v1.py ....................... [ 84%]
.............................................                            [ 86%]
tests/test_lp_solana_rpc_registry_fix_repeat_v1.py ..................... [ 87%]
..............................                                           [ 88%]
tests/test_lp_solana_rpc_registry_fix_repeat_v2.py ..................... [ 88%]
.......................................                                  [ 89%]
tests/test_lp_solana_stable_pool_research_v1.py ...................      [ 90%]
tests/test_lp_solana_stock_stage2_v1_readonly.py ...................     [ 91%]
tests/test_lp_solana_tier_c_risk_evidence_v1_readonly.py ...             [ 91%]
tests/test_lp_stock_e5_position_report_v1_readonly.py ..                 [ 91%]
tests/test_lp_stock_tier_acceptance_v1_readonly.py .......               [ 91%]
tests/test_lp_stock_tier_c_shadow_v1_readonly.py ....                    [ 91%]
tests/test_lp_stock_tier_policy_v1_readonly.py .....................     [ 92%]
tests/test_lp_stock_token_universe_v1_readonly.py ...................... [ 93%]
............                                                             [ 93%]
tests/test_lp_swap_cost_model_v1_readonly.py ........................... [ 94%]
.....                                                                    [ 94%]
tests/test_lp_tg_alerter_v1_readonly.py .............                    [ 94%]
tests/test_lp_tier_b_baseline_v1_readonly.py .....                       [ 95%]
tests/test_lp_tier_b_baseline_v2_readonly.py ......                      [ 95%]
tests/test_lp_tier_b_level2_replay_v1_readonly.py ....                   [ 95%]
tests/test_lp_tier_c_exit_feasibility_v1_readonly.py ............        [ 95%]
tests/test_lp_tier_c_sample_builder_v1_readonly.py .............         [ 96%]
tests/test_lp_tier_range_policy_v1_readonly.py ..............            [ 96%]
tests/test_lp_tp_d_compare_v1_readonly.py .                              [ 96%]
tests/test_lp_tp_d_full_once_v1_readonly.py ..                           [ 96%]
tests/test_lp_universe_screener_v1_readonly.py .............             [ 97%]
tests/test_lp_universe_second_opinion_v1_readonly.py .....               [ 97%]
tests/test_lp_v3_fee_share.py .......                                    [ 97%]
tests/test_lp_v3_position_value.py .........                             [ 97%]
tests/test_lp_vol_range_sizer_v1_readonly.py ......                      [ 98%]
tests/test_m0_legacy_environment_node_quarantine_v1.py ..                [ 98%]
tests/test_p0_postgres_shadow_audit_v1.py ............................   [ 98%]
tests/test_solana_m1_sidecar_e3.py ................................      [100%]

================= 3099 passed, 14 skipped in 136.54s (0:02:16) =================
```

### `go test ./...`

```text
$ go test ./...
ok  	github.com/lpbot/lpbot/adapters/broadcast/disabled	(cached)
?   	github.com/lpbot/lpbot/adapters/bus/inproc	[no test files]
?   	github.com/lpbot/lpbot/adapters/bus/nats	[no test files]
?   	github.com/lpbot/lpbot/adapters/store/postgres	[no test files]
?   	github.com/lpbot/lpbot/adapters/store/sqlite	[no test files]
ok  	github.com/lpbot/lpbot/cmd/lpbot	(cached)
ok  	github.com/lpbot/lpbot/cmd/lpbot-backtest	(cached)
?   	github.com/lpbot/lpbot/cmd/lpbot-cli	[no test files]
?   	github.com/lpbot/lpbot/cmd/lpbot-migrate-postgres	[no test files]
ok  	github.com/lpbot/lpbot/cmd/lpbot-recon	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/alerter/log	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/alerter/telegram	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/bus/inproc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/chain/base	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/chain/base/abi	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/chain/solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/birdeye	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/defillama	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/subgraph	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/holderconcentration/basescan	[no test files]
?   	github.com/lpbot/lpbot/internal/adapters/mev/flashbots	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/mev/flashbots-protect	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/mev/jito	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/aerodrome	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/pancakeswap_v3_solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/raydium_clmm	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/uniswap_v3	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/whirlpool	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/rpc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/simulator/anvil	0.021s
ok  	github.com/lpbot/lpbot/internal/adapters/simulator/sol_rpc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/store/postgres	7.430s
ok  	github.com/lpbot/lpbot/internal/adapters/store/postgres/migrator	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/store/sqlite	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/store/sqlite/sqlcgen	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/wallet/keystore	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/wallet/kms	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/wallet/none	[no test files]
ok  	github.com/lpbot/lpbot/internal/core/audit	(cached)
ok  	github.com/lpbot/lpbot/internal/core/execution	(cached)
ok  	github.com/lpbot/lpbot/internal/core/loop	(cached)
ok  	github.com/lpbot/lpbot/internal/core/pnl	(cached)
ok  	github.com/lpbot/lpbot/internal/core/reconcile	(cached)
ok  	github.com/lpbot/lpbot/internal/core/reporting	(cached)
ok  	github.com/lpbot/lpbot/internal/core/risk	(cached)
ok  	github.com/lpbot/lpbot/internal/core/scanner	(cached)
ok  	github.com/lpbot/lpbot/internal/core/simulation	(cached)
ok  	github.com/lpbot/lpbot/internal/core/strategy	(cached)
ok  	github.com/lpbot/lpbot/internal/core/tierc	(cached)
ok  	github.com/lpbot/lpbot/internal/core/watchdog	(cached)
ok  	github.com/lpbot/lpbot/internal/domain	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/config	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/decimal_db	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/health	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/idgen	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/log	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/metrics	(cached)
?   	github.com/lpbot/lpbot/internal/platform/redis	[no test files]
ok  	github.com/lpbot/lpbot/internal/platform/timex	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/trace	(cached)
ok  	github.com/lpbot/lpbot/internal/ports	(cached)
ok  	github.com/lpbot/lpbot/pkg/decimal	(cached)
ok  	github.com/lpbot/lpbot/pkg/il	(cached)
ok  	github.com/lpbot/lpbot/pkg/tickmath	(cached)
?   	github.com/lpbot/lpbot/scripts/aggregate-verdict	[no test files]
ok  	github.com/lpbot/lpbot/tests/chaos	(cached)
?   	github.com/lpbot/lpbot/tests/fork	[no test files]
ok  	github.com/lpbot/lpbot/tests/property	(cached)
ok  	github.com/lpbot/lpbot/tests/property/mocks	(cached)
```
