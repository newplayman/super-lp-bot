# AUDIT：按 PRD v1.1 全量对账工程完成度（2026-09-10）

- 任务：主脑派 codex（gpt-5.6-luna, xhigh, read-only）对照
  `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md`（1299 行）逐条核对
  60 个 T 用例、14 个 D 决策项、§19 九个任务包、§21 三阶段门槛。
- 性质：**只读**。未改动任何代码、未写任何库。
- 快照：HEAD = `5ba11db`，`reports/lp_rh/scanner.db` as-of 2026-09-10T02:30Z。

> **读法警告**：下表的 `55/60 = 91.67%` 是**测试覆盖度**，不是工程完成度。
> PRD §20 明写「这是最低覆盖，不是测试数量指标」。真正的完成度由
> §21 三阶段门槛决定，当前 Stage A 仍 FAIL。主脑独立核实的两项补充
> 见文末「主脑补充核实」一节——它们不在 codex 的结论里，且改变结论的量级。

---

# 审计结论

当前工程的 T 用例完成度为：

| 判定 | 数量 |
|---|---:|
| 已实现且有测试 | 55 |
| 已实现无测试 | 1 |
| 未实现 | 4 |
| 不适用 | 0 |
| 合计 | 60 |

按 T 矩阵口径：`55 / 60 = 91.67%`。这只是模块与测试覆盖度，不代表已通过 Shadow 或 Tiny Live。PRD 明确说 §20 是最低覆盖，不是测试数量指标（PRD L987-989）。

## 一、60 个 T 用例逐条核对

判定口径：组件级行为已有明确实现和断言即可计入“已实现且有测试”；标记“⚠”表示尚未接入完整端到端主链。

| T | PRD 要求 | 对应测试 | 判定 |
|---|---|---|---|
| T01 | chainId、错误响应混入时，主网身份失败，不升级候选（PRD L993） | `tests/test_lp_rh_capabilities_v1_readonly.py::test_chain_identity_gate_ok_mismatch_unknown:35` | 已实现且有测试 |
| T02 | symbol 正确但地址非 registry 部署，返回身份不匹配（L994） | `tests/test_lp_rh_registry_v1_readonly.py::test_verify_identity_same_symbol_different_address:142` | 已实现且有测试 |
| T03 | 旧 assets schema 明确映射，null/空/closing-only 不转为可交易（L995） | `tests/test_lp_rh_registry_v1_readonly.py::test_legacy_mapping_true_false_null_empty:72`; `::test_closing_only_maps_not_tradable_and_preserves_raw:101` | 已实现且有测试 |
| T04 | 新嵌套 schema 区分 market/extended/overnight（L996） | `tests/test_lp_rh_registry_v1_readonly.py::test_nested_market_extended_overnight_distinguished:84` | 已实现且有测试 |
| T05 | 未知 enum 或语义冲突返回 UNKNOWN/CONFLICT 并阻挡（L997） | `tests/test_lp_rh_registry_v1_readonly.py::test_nested_unknown_enum_is_unknown_and_blocked:92`; `::test_whole_fractional_disagreement_takes_conservative:109` | 已实现且有测试 |
| T06 | implementation 变化使 attestation 过期（L998） | `tests/test_lp_rh_pool_probe_v1_readonly.py::test_attestation_expired_on_code_hash_change:105` | 已实现且有测试 |
| T07 | V3 factory getPool 不匹配时身份失败且不进入经济闸（L999） | `tests/test_lp_rh_pool_probe_v1_readonly.py::test_v3_identity_fail_withholds_economic_fields:46` | 已实现且有测试 |
| T08 | V4 PoolId 不走 V3 探针，协议分派正确（L1000） | `tests/test_lp_rh_pool_probe_v1_readonly.py::test_dispatch_protocol_v4_v3_and_unsupported:36` | 已实现且有测试 |
| T09 | 未支持 hooks/custom fee 时 UNSUPPORTED，网页 APR 不影响结果（L1001） | `tests/test_lp_rh_pool_probe_v1_readonly.py::test_v4_nonzero_hooks_unsupported_policy:81`; APR 回归断言 `tests/test_lp_rh_audit_regression_guards_v1_readonly.py:117-132` | 已实现且有测试 |
| T10 | 不得把 PoolManager 总余额当单池 TVL（L1002） | `tests/test_lp_rh_pool_probe_v1_readonly.py::test_v4_state_view_equal_to_pool_manager_rejected:91` | 已实现且有测试 |
| T11 | 同块高不同 hash 标记分歧，深度确认后只回滚 orphan（L1003） | `tests/test_lp_rh_capabilities_v1_readonly.py::test_provider_independence_block_hash_divergence:88`; `tests/test_lp_rh_reorg_resolution_v1_readonly.py::test_record_contested_is_contested_and_no_rollback:62`; `::test_apply_only_resolved_rows:134` | 已实现且有测试 ⚠ |
| T12 | JSON-RPC error 不能转成 0 余额/费用（L1004） | `tests/test_lp_rh_capabilities_v1_readonly.py::test_probe_provider_jsonrpc_error_kept_and_block_number_none:43` | 已实现且有测试 |
| T13 | 同一 provider 后端不能满足多源冗余（L1005） | `tests/test_lp_rh_capabilities_v1_readonly.py::test_provider_independence_same_backend_suspected:78` | 已实现且有测试 |
| T14 | HTTP 200 但 generatedAt 不推进时 source stale（L1006） | `tests/test_lp_rh_reference_freshness_v1_readonly.py::test_rest_over_age_stale:48`; `tests/test_lp_rh_wire_freshness_v1_readonly.py::test_stale_source_event_time_fails:116` | 已实现且有测试 |
| T15 | 2026-09-07 纽约时间应为 HOLIDAY，不是 RTH（L1007） | `tests/test_lp_rh_market_session_v1_readonly.py::test_t15_labor_day_holiday_not_rth:20` | 已实现且有测试 |
| T16 | DST、提前收市、周末转换正确（L1008） | `tests/test_lp_rh_market_session_v1_readonly.py::test_t16_dst_start_et_conversion:29`; `::test_t16_dst_end_et_conversion:36`; `::test_early_close_postmarket_not_rth:43`; `::test_saturday_weekend:50` | 已实现且有测试 |
| T17 | raw2e18、multiplier、underlying 转换为 token2/股数/总值（L1009） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t17_token_quantity_and_shares:18`; `::test_t17_reference_price_and_total:27` | 已实现且有测试 |
| T18 | 已是 token-equivalent 的价格不得再次乘 multiplier（L1010） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t18_already_token_equivalent_no_double_apply:38` | 已实现且有测试 |
| T19 | USDG 价格归一化（L1011） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t19_usdg_normalized_price:47` | 已实现且有测试 |
| T20 | split 不改变单 token 参考价值，raw 余额不变（L1012） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t20_split_preserves_reference_true:62` | 已实现且有测试 |
| T21 | oraclePaused 或不可用时禁止新增/recenter，保留 stale 标记（L1013） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t21_oracle_paused_blocks:75`; `::test_t21_oracle_paused_none_unknown:83` | 已实现且有测试 |
| T22 | multiplier 未变化且无未来事件时不虚构公司行动（L1014） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t22_pending_equals_current_normal:92` | 已实现且有测试 |
| T23 | 闭市不更新与盘中异常不更新原因分开，均阻挡窄区间（L1015） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t23_stale_session_closed:103`; `::test_t23_stale_while_expected_live:109` | 已实现且有测试 |
| T24 | 无足额退出 quote 时返回 `INPUTS_UNAVAILABLE: EXIT_QUOTE`（L1016） | `tests/test_lp_rh_stock_reference_v1_readonly.py::test_t24_exit_quote_unavailable:122`; `tests/test_lp_rh_exit_depth_v1_readonly.py::test_t24_empty_tick_data_is_unavailable_not_zero:127` | 已实现且有测试 |
| T25 | 100U 政策与旧最小仓位冲突时显式报告，不自动改金额（L1017） | `tests/test_lp_rh_bucket_ledger_v1_readonly.py::test_t25_capital_policy_conflict:123`; `tests/test_lp_rh_terminal_gate_v1_readonly.py::test_t25_live_readiness_policy_conflict_blocks:106` | 已实现且有测试 |
| T26 | MEME 跨池/跨钱包累计暴露超过 2% 时阻挡（L1018） | `tests/test_lp_rh_meme_aggregation_v1_readonly.py::test_t26_cross_pool_bypass_blocked:56` | 已实现且有测试 |
| T27 | 并发 reservation 原子化，不能超剩余额度（L1019） | `tests/test_lp_rh_bucket_ledger_v1_readonly.py::test_t27_competing_reservations:45` | 已实现且有测试 |
| T28 | 价格上涨导致超 cap 时 NO_NEW/REDUCE_EVAL，不误报 admission bug（L1020） | `tests/test_lp_rh_premium_guard_v1_readonly.py::test_classify_400bps_no_new_widen_remove_eval:85`; `::test_classify_800bps_dislocation_no_recenter:91` | 已实现且有测试 |
| T29 | WETH 多但 native ETH 不足时 gas reserve 失败（L1021） | `tests/test_lp_rh_gas_reserve_v1_readonly.py::test_t29_weth_rich_native_zero_fails:18`; `::test_t29_wrapped_does_not_count:27` | 已实现且有测试 ⚠ |
| T30 | 单位资本净边际收益不为正时不推荐加资（L1022） | `tests/test_lp_netcover_engine_v1_readonly.py::test_inv_cost_01_high_apr_but_tiny_absolute_profit_is_skip:80`; `tests/test_lp_rh_shadow_runner_v1_readonly.py::test_conjunct_absolute_profit_fails_when_costs_exceed_fees:383` | 已实现且有测试 |
| T31 | q_min > q_max 时为空区间，允许合法 0 配置（L1023） | `tests/test_lp_rh_size_interval_v1_readonly.py::test_t31_empty_interval_width_negative:11` | 已实现且有测试 ⚠ |
| T32 | 未知 fee 与合法 fee=0 必须区分（L1024） | 缺失分支：`tests/test_lp_rh_netcover_inputs_v1_readonly.py::test_missing_fee_apr_marks_input_unavailable:110`；代码分支：`scripts/lp_rh_netcover_inputs_v1_readonly.py:81-88` | 已实现无测试 |
| T33 | 仅广告 APR 的 reward 不计入验证收入（L1025） | `tests/test_lp_rh_netcover_inputs_v1_readonly.py::test_reward_unverified_zeroes_reward_ev:72`; `::test_reward_missing_zeroes_reward_ev:78` | 已实现且有测试 |
| T34 | 已含 L1 data fee 的总 gas 不得再次追加（L1026） | `tests/test_lp_rh_gas_estimator_v1_readonly.py::test_estimate_gas_usd_measured_anchor:10`; `::test_sanity_understated_reproduces_error:88` | 已实现且有测试 ⚠ |
| T35 | 仅换腿 30% 时按实际 30% 计算成本（L1027） | `tests/test_lp_clmm_leg_cost_v1_readonly.py::test_centered_clmm_leg_fraction_is_the_v3_inventory_value_not_full_position:20`; `::test_leg_cost_uses_exact_inventory_fraction_and_is_below_full_notional:31` | 已实现且有测试 |
| T36 | 回放不得使用未来数据（L1028） | `tests/test_lp_rh_replay_clock_v1_readonly.py::test_per_sample_decided_at_uses_own_sample_time:169`; `::test_multiple_samples_each_judged_at_own_time:221` | 已实现且有测试 |
| T37 | 全程 out-of-range 时 fee 为 0，不按全池 APR 分摊（L1029） | `tests/test_lp_rh_in_range_v1_readonly.py::test_all_out_range:75`; `::test_effective_fee_ev_basic:161` | 已实现且有测试 |
| T38 | collect、价格不变、gas=0 时 NAV 不变（L1030） | `tests/test_lp_rh_pnl_v1_readonly.py::test_t38_collect_no_price_move_nav_unchanged:28` | 已实现且有测试 |
| T39 | collect、gas=0.10 时 NAV 只下降 0.10（L1031） | `tests/test_lp_rh_pnl_v1_readonly.py::test_t39_collect_gas_nav_down_exactly_gas:41` | 已实现且有测试 |
| T40 | 外部入金 10，NAV 增 10 但 PnL 为 0（L1032） | `tests/test_lp_rh_pnl_v1_readonly.py::test_t40_external_deposit_nav_up_pnl_zero:60` | 已实现且有测试 |
| T41 | recenter 不重置累计亏损和 HODL 初始 lot（L1033） | `tests/test_lp_rh_pnl_v1_readonly.py::test_t41_recenter_hodl_initial_lot_not_reset:74` | 已实现且有测试 |
| T42 | 30s/5m/30m markout 分列，不重复累计（L1034） | `tests/test_lp_rh_pnl_v1_readonly.py::test_t42_same_fill_three_windows_not_triple_counted:98`; `tests/test_lp_rh_markout_v1_readonly.py::test_t42_profile_does_not_expose_cross_window_total:57` | 已实现且有测试 |
| T43 | 下跌跌穿下界时不自动下移/补仓（L1035） | `tests/test_lp_rh_meme_audit_v1_readonly.py::test_t43_downtrend_cannot_recenter_lower:153` | 已实现且有测试 |
| T44 | swap 失败但 remove 成功时保留风险库存，不显示 cash closed（L1036） | `tests/test_lp_rh_meme_audit_v1_readonly.py::test_t44_remove_without_swap_keeps_risk:175` | 已实现且有测试 |
| T45 | 原子退出 swap 回滚时 remove 也视为未完成（L1037） | `tests/test_lp_rh_meme_audit_v1_readonly.py::test_t45_atomic_swap_failure_reverts_remove:183` | 已实现且有测试 |
| T46 | 退出转入 USDG 仍需经过风险方向检查（L1038） | `tests/test_lp_rh_meme_audit_v1_readonly.py::test_t46_exit_to_full_usdg_is_blocked:202` | 已实现且有测试 |
| T47 | LIVE=false/授权错误时在签名前拦截（L1039） | `tests/test_lp_rh_readiness_v1_readonly.py::test_live_gate_single_provider:360`; `::test_live_gate_signatures:367`; `tests/test_lp_c6_preflight_v1_readonly.py::test_broadcast_lock_proves_transport_unreached:42` | 已实现且有测试 |
| T48 | 非白名单 target/recipient 时 decoder 拒绝（L1040） | `tests/test_lp_rh_calldata_decoder_v1_readonly.py::test_multicall_child_target_outside_allowlist_is_named:120`; `::test_t48_recipient_outside_allowlist_is_rejected:132` | 已实现且有测试 |
| T49 | quote 后 calldata/size/policy 改变时原模拟失效（L1041） | `tests/test_lp_rh_calldata_decoder_v1_readonly.py::test_verify_intent_accepts_complete_matching_metadata:193`; `::test_verify_intent_rejects_each_missing_required_field:198`; `::test_verify_intent_rejects_mismatch:217` | 已实现且有测试 |
| T50 | 合法零数量腿与 swap 最小到账保护分开判断（L1042） | `tests/test_lp_rh_calldata_decoder_v1_readonly.py::test_t50_zero_leg_is_legitimate:141`; `::test_t50_nonzero_leg_with_zero_minimum_is_rejected:147`; `::test_t50_swap_zero_minimum_is_rejected:153` | 已实现且有测试 |
| T51 | 广播超时且链上已有同 nonce 时 UNKNOWN→对账，不重复开仓/释放 reservation（L1043） | 仅有局部状态测试：`tests/test_lp_rh_bucket_ledger_v1_readonly.py::test_broadcast_unknown_counts_toward_occupancy:58`; `::test_release_broadcast_unknown_rejected:70`；无 HTTP timeout+nonce 对账测试 | 未实现 |
| T52 | crash 发生在 nonce/提交/回执阶段时恢复不重复签名且账本一致（L1044） | 仅有 `tests/test_lp_rh_bucket_ledger_v1_readonly.py::test_try_reserve_duplicate_intent_id:107`，不是 crash recovery | 未实现 |
| T53 | L1 posting 滞后但 L2 多源推进时分层告警（L1045） | 无 T53 测试；RH-07 尚未进入执行适配 | 未实现 |
| T54 | 没有 L1 证据时不得自动进入 L1_FINALIZED（L1046） | 无 T54 测试或 RH finality 适配；RH-07 仍是延期任务（PRD L961-967） | 未实现 |
| T55 | 每个新增硬闸摘除都能被 mutation test 捕获（L1047） | `tests/test_lp_rh_terminal_gate_v1_readonly.py::test_mutation_witness_detects_each_omitted_gate:97`; `tests/test_lp_rh_funnel_autopsy_v1_readonly.py::test_mutation_harness_detects_single_gate_witnesses:144` | 已实现且有测试 |
| T56 | 旧 Base 模型同一 SQLite 快照逐闸差异为 0（L1048） | `tests/test_lp_rh_t56_base_replay_guard_v1_readonly.py::TestT56ZeroDrift::test_replay_matches_golden_field_by_field:135`; `::test_source_db_md5_unchanged_by_replay:144` | 已实现且有测试 |
| T57 | 达预算时停止非必要采集，风险证据优先且不删旧资料（L1049） | `tests/test_lp_rh_collector_v1_readonly.py::test_budget_over_stops_collection_cleanly:198`; `tests/test_lp_rh_store_v1_readonly.py::test_budget_status_ok:187` | 已实现且有测试 |
| T58 | 读 keystore/导入 signer 被权限与依赖测试拒绝（L1050） | `tests/test_lp_c6_preflight_v1_readonly.py::test_keystore_check_stats_but_does_not_read_contents:51`; `tests/test_lp_rh_calldata_decoder_v1_readonly.py::test_source_has_no_forbidden_capability_names:224` | 已实现且有测试 |
| T59 | 旧 terminal 字段无 writer 时 producer-map 必须 FAIL（L1051） | `tests/test_lp_rh_terminal_gate_v1_readonly.py::test_t59_missing_producer_not_computed_fail:129`; `tests/test_lp_rh_funnel_autopsy_v1_readonly.py::test_producer_map_marks_all_missing_as_no_producer:165` | 已实现且有测试 |
| T60 | 0 合格池或 MEME 全闲置时正常解释，不强制下单（L1052） | `tests/test_lp_rh_shadow_runner_v1_readonly.py::test_all_ineligible_t60:117`; `tests/test_lp_rh_terminal_gate_v1_readonly.py::test_t60_all_true_eligible_no_blocker:139` | 已实现且有测试 |

`T11/T29/T31/T34` 的测试证明了模块行为，但尚未证明它们全部接入当前生产 Shadow 主链。尤其 T31 模块明确写着尚未接入 NetCover/终闸（`scripts/lp_rh_size_interval_v1_readonly.py:19-21`）。

## 二、14 个 D 决策项

| 决策 | PRD 决定 | 当前代码状态与证据 |
|---|---|---|
| D01 | Python + SQLite 增量支线，Go 冻结（PRD L67） | 遵循。RH DDL 与 SQLite 表由 `scripts/lp_rh_store_v1_readonly.py:26-60` 定义；Shadow runner 为 Python/SQLite 离线链路（`scripts/lp_rh_shadow_runner_v1_readonly.py:1-9`）。 |
| D02 | 新资本政策只作 Shadow 提案，LIVE 冲突时返回 `CAPITAL_POLICY_CONFLICT`（L68） | 遵循。冲突只报告、不改金额：`scripts/lp_rh_bucket_ledger_v1_readonly.py:173-185`；LIVE 与 Shadow 模式分开：`scripts/lp_rh_terminal_gate_v1_readonly.py:106-124,163-165`。 |
| D03 | 实际 PnL 唯一使用 NAV + 外部现金流，IL/LVR/markout 只是归因（L69） | 模块遵循。公式在 `scripts/lp_rh_pnl_v1_readonly.py:4-8,111-115`；缺失外部流不会默认为有效 PnL（`:221-227,255-256`）。当前真实 DB 没有 Shadow position/mark/economic rows，因此端到端实际 PnL 尚未形成。 |
| D04 | HODL 使用实际初始两腿，不固定 50/50（L70） | 遵循。`hodl_benchmark()` 使用实际初始 raw 数量（`scripts/lp_rh_pnl_v1_readonly.py:118-133`）；Shadow runner 使用开仓实际数量（`scripts/lp_rh_shadow_runner_v1_readonly.py:655-657`）；已有测试 `tests/test_lp_rh_pnl_v1_readonly.py:155`。 |
| D05 | V3 用 factory+pool，V4 用 PoolManager+PoolKey+PoolId，不用单例余额作 TVL（L71） | 遵循。协议分派和 V3/V4 身份逻辑在 `scripts/lp_rh_pool_probe_v1_readonly.py:154-170,250-268`；PoolManager 余额会被拒绝（`:250-253`）。 |
| D06 | 先证明广播/回执；原子退出可选，分步减仓必须有（L72） | 部分遵循。通用 Base executor 有双开关和回执等待（`execution/base_m1_executor_v1.py:734-760`），但没有 RH 专用执行适配、分步退出与恢复闭环；RH-07 交付物仍不存在（PRD L961-967）。 |
| D07 | HOLIDAY/OVERNIGHT/UNKNOWN 与健康状态分离（L73） | 遵循。会话枚举与独立健康 flags 在 `scripts/lp_rh_market_session_v1_readonly.py:47-98,145-192`。 |
| D08 | 新旧 API schema 双适配，未知 enum 为 UNKNOWN（L74） | 遵循。`detect_schema()` 和 fail-closed normalize 在 `scripts/lp_rh_registry_v1_readonly.py:145-185`。 |
| D09 | AMC 只读观察；首个股票应数据完整、可退出；参考价不等于兑付权（L75） | 部分遵循。股票参考价、multiplier、USDG 归一化和退出 quote 要求已实现（`scripts/lp_rh_stock_reference_v1_readonly.py:30-70,128-132`），但首个股票 profile 的持续 Shadow 与执行证据尚未完成。 |
| D10 | MEME 限额，首轮 MEME 不进 LIVE，经济不足时闲置（L76） | 部分遵循。跨池/跨钱包聚合和最坏暴露限制已实现（`scripts/lp_rh_meme_aggregation_v1_readonly.py:2-12,89-129,154-206`）。但 `terminal_gate` 只有通用 target mode（`:54,84-124`），未看到首个 MEME 的独立 LIVE 禁止接线。 |
| D11 | 风险/PnL/终闸先于执行（L77） | 遵循。终闸十项合取定义于 `scripts/lp_rh_terminal_gate_v1_readonly.py:30-52,113-124`；只有 eligibility 后才尝试 reservation（`scripts/lp_rh_shadow_runner_v1_readonly.py:527-536`）。 |
| D12 | 保留旧集中度限制，RH 新政策显式处理冲突（L78） | 部分遵循。RH bucket cap/reservation 和 MEME 专用 cap 存在（`scripts/lp_rh_bucket_ledger_v1_readonly.py:75-124`; `scripts/lp_rh_meme_aggregation_v1_readonly.py:22-27`），但旧共享限制与 RH gate 的联合执行未形成完整证据。 |
| D13 | STOCK/STOCK v1.1 不进 LIVE；后续采用更严格 10% 股票桶、3% 总资本（L79） | 部分遵循。已有研究态明确拒绝 STOCK_STOCK（`scripts/lp_stock_tier_acceptance_v1_readonly.py:143-145`），但未发现 RH LIVE gate 中完整接入 `≤10%` 与 `≤3%` 的执行限制。 |
| D14 | 不跨桶借资；共享钱包不改变账本归属；转拨必须显式授权（L80） | 无法判定/未完成。当前 reservation 明确带 bucket 和 policy version（`scripts/lp_rh_bucket_ledger_v1_readonly.py:94-124`），但没有 RH 专用跨桶转拨、所有权账本和显式授权流程证据。 |

## 三、§19 任务包进度

| 任务包 | 状态 | 证据与缺口 |
|---|---|---|
| RH-00 基线与证据链 | 已完成 | 交付物和只读边界已记录，`reports/rh_pivot/20260907T124500Z/RH-00/VERDICT.json:4-6,20-32`。 |
| RH-01 链/资产/协议能力 | 代码与离线验收完成，真实 corpus 仍不完整 | 代码/测试验收记录为 ACCEPT，`reports/rh_pivot/20260907T124500Z/RH-01b/VERDICT_NOTE.md:12-20`。当前 registry 只有 1 个 V3 pool，V4 字段为空，且 registry 状态为 `DISCOVERED_NOT_ATTESTED`。 |
| RH-02 数据、时段、健康闭环 | 进行中 | 隔离 SQLite、schema、collector、session、budget 已有；PRD L921-927。当前只读快照为 10,517 条 market state、45.11462778055555 小时、coverage 0.9713705208718138，`reference_bid/ask/multiplier_human/oracle_paused` 全部 0 非空；只有 2,456/10,517 条 fee_growth_global_0、2,455/10,517 条 fee_growth_global_1 非空。 |
| RH-03 组合政策、成本、终闸 | 部分完成，仍在收口 | 十项终闸和 mutation 已验收，`reports/rh_pivot/20260907T124500Z/RH-03b/VERDICT_NOTE.md:7-25`。但 gas estimator、size interval 等模块仍未完全接入主终闸；交付物 `100U_FEASIBILITY.md`、`COST_DECOMPOSITION.json`、`BASE_INVARIANCE_DIFF.json` 未找到。 |
| RH-04 账本与 CORE Shadow | 部分完成 | NAV/HODL 和五步闭环已有证据，`reports/rh_pivot/20260907T124500Z/RH-04a/VERDICT_NOTE.md:7-15`、`RH-04b/FIRST_CLOSED_LOOP.md:3-15`。当前 scanner.db 的 `rh_economic_evaluations`、`rh_shadow_positions`、`rh_position_marks`、`rh_gate_decisions` 均为 0 行，持续实证尚未形成。 |
| RH-05 STOCK Shadow | 部分完成，未达到 Shadow | 参考价、乘数、退出深度证据存在，`reports/rh_pivot/20260907T124500Z/RH-05-research/RH05_EVIDENCE_COMPLETE.md:5-12,27-40`；但该报告明确指出 in-range 时长折算未完成，且 Stage B 未开始（`:42-55`）。 |
| RH-06 MEME 审计/可选 Shadow | 代码部分完成，证据交付未完成 | MEME audit、exit state machine、聚合限制和测试存在；但 `MEME_READINESS.md`、`FLOW_QUALITY_LIMITATIONS.md` 等交付物未找到，PRD L953-959 要求的免费证据不足时 NO-GO/闲置结论尚未形成完整报告。 |
| RH-07 受限执行与恢复 | 未开始，按授权延期 | PRD 要求先有实质只读候选，再做 RH 执行适配（L961-967）。当前没有 `EXECUTION_CONTRACT.md`、fork matrix、nonce recovery、exit failure 交付物，也没有 T51-T54 的 RH 实现。 |
| RH-08 面板、告警、回归、故障演练 | 部分完成，未收口 | readiness、autopsy、mutation 和 budget tests 已有；但 `READINESS_DASHBOARD.md`、`FULL_TEST_RAW.log`、`FAULT_INJECTION_REPORT.md`、`GRADUATION_VERDICT.json` 未找到。且 `_build_state()` 将 Stage B 的 weekend/diff/risk event 参数写成 `None/0/0`（`scripts/lp_rh_readiness_v1_readonly.py:758-760`），尚非真实证据接线。 |
| RH-09 Tiny Live 请求包 | 未开始 | PRD L977-983 要求独立候选、资金政策、损失上限、退出路径、负责人和审批模板；`TINY_LIVE_APPROVAL_REQUEST.md` 未找到。 |

## 四、三个阶段门槛

### Stage A / Read-only

按要求不重做已有九条审计，沿用已有结论：当前 Stage A 未毕业，且不能仅靠等待时间自动毕业（`reports/AUDIT_stage_a_prd_reconciliation_20260909.md:201-204`）。

对当前 HEAD 做的只读状态核对结果：

- 观测时长：`45.11462778055555 h < 72 h`。
- 计划窗口覆盖率：`0.9713705208718138 < 0.99`。
- synthetic evidence：`None`，readiness 阻挡。
- 当前函数已检查时间、coverage、key field、attestation、budget、invariant、unknown state（`scripts/lp_rh_readiness_v1_readonly.py:136-185`）。
- 但当前数据库的 `reference_bid`、`reference_ask`、`multiplier_human`、`oracle_paused` 10,517 行均为空；readiness 当前定义的 key-field 子集通过，不能据此证明 PRD 所称全部关键字段真实生产。
- `rh_pool_registry` 当前仍为 `DISCOVERED_NOT_ATTESTED`，而 readiness 另从 attestation 表得到 `has_contract_attestation=true`，两处状态未统一，需工程修复。

结论：Stage A `FAIL`。

### Stage B / Shadow

PRD 要求至少 14 个完整日、覆盖周末，并同时满足真实 RTH/盘外事件、零未解释账差、零不变量、零漏闸、实际全成本/HODL/OOS/最差日/不确定性/NetCover 门槛（PRD L1066-1078）。

当前状态：

- readiness 当前 `days_covered=1`，且 `weekends_covered=None`，代码阻挡 `DAYS_COVERED_INSUFFICIENT` 和 `WEEKENDS_COVERED_INSUFFICIENT`（`scripts/lp_rh_readiness_v1_readonly.py:206-232`）。
- `_build_state()` 把未解释账差和漏风险事件直接传入 `0`，不是从持续 Shadow 证据计算（`:758-760`）。
- 修正后的经济基线只有 `3.95 小时`有效 fee-growth 窗口，不能替代 Stage B 的 14 日样本（`reports/ECONOMICS_corrected_20260909.md:7-19`）。
- 修正后的实际结果为 `net_pnl=-5.308307`、`hodl_delta=-5.159831`，不是正收益证据（同报告 `:21-33`）。

结论：Stage B 尚未开始达到 PRD 验收状态；当前为 `FAIL/WARN`，不能把 RH-04 的五步闭环当作 14 日 Shadow。

### Stage C / Tiny Live

PRD 前置条件包括：Stage B profile 通过、资金政策批准、账户/合约权限验证、至少两套独立数据/执行路径、本地 fork 与故障演练、NAV 对账、操作者和事故处置方案（PRD L1080-1086）。

当前只读结果：

- `usable_provider_count=0`；readiness 要求至少 2 个 provider（`scripts/lp_rh_readiness_v1_readonly.py:234-258`）。
- `capital_policy_approved=None`，阻挡 `CAPITAL_POLICY_NOT_APPROVED`。
- `signatures=0`、`broadcasts=0`、`keys_created=0`，这是安全必要条件，不是 Tiny Live 充分条件（`:246-258,771-775`）。
- `rh_tx_intents=0`、`rh_tx_receipts=0`、`rh_reconciliation_runs=0`，没有 RH 执行/回执/对账闭环。
- RH-07 和 RH-09 交付物均不存在。

结论：Tiny Live `NOT_AUTHORIZED`，距离真钱路径仍有硬阻挡。

## 五、整体完成度与剩余工作

整体评级：`未毕业，不能进入 Tiny Live`。

T 矩阵本身是 `91.67%`，但 PRD 的毕业门槛、任务包交付物和端到端证据仍未完成，因此不能把 `55/60` 等同于项目完成度。

### 按时间等待

- 完成 Stage A 至少 72 小时正向观测、计划窗口 coverage ≥99%（PRD L1062-1064）。
- 形成 Stage B 至少 14 个完整日并覆盖一个周末（L1066-1076）。
- Tiny Live 扩容前还需至少 30 天实际观察（L1086）。
- 当前有效 fee-growth 经济窗口只有 3.95 小时（`reports/ECONOMICS_corrected_20260909.md:7-19`），必须重新积累有效经济样本。

### 工程实现

- 将 T29 native gas reserve、T31 size interval、T34 gas/L1 口径真正接入 NetCover 和终闸；当前 T31 明确未接线（`scripts/lp_rh_size_interval_v1_readonly.py:19-21`）。
- 完成 T51 timeout+同 nonce 对账、T52 crash recovery、T53 L1/L2 分层告警、T54 L1 finality evidence；对应 RH-07 任务包仍未开始（PRD L961-967）。
- 将 reorg detector、contested registry、深度复核和 rollback 自动接成持续采集链；现有实现和测试主要是可调用模块级闭环。
- 修复 readiness 对 Stage B 的证据接线，不能把 weekend、账差和漏事件默认传成 `None/0/0`（`scripts/lp_rh_readiness_v1_readonly.py:758-760`）。
- 统一 `rh_pool_registry.attestation_status` 与 `rh_contract_attestations` 的权威状态。
- 完成 STOCK in-range 时长折算、organic volume 与 raw volume 区分、参考价/DEX 偏离时间序列；当前 in-range 缺口见 `RH05_EVIDENCE_COMPLETE.md:42-55`。
- 补齐 RH-08 原始全量测试日志、fault injection、恢复演练和最终 graduation verdict。
- 让真实 Shadow writer 产生可对账的经济、gate、position mark 数据；当前相关表均为 0 行。

### 产品/所有者决策

- 解决 100U 下 CORE active cap `42.5U` 与旧最小仓位 `50U` 的 `CAPITAL_POLICY_CONFLICT`；代码只能报告，不能自动替所有者批准（PRD D02 L68；`scripts/lp_rh_bucket_ledger_v1_readonly.py:173-185`）。
- 明确 Tiny Live 首个 profile/pool；CORE、STOCK、MEME 不能相互担保，PRD 要求 profile 独立给出全成本、HODL、退出压力和 OOS 证据（L1073-1076）。
- 批准两套独立数据/执行证据路径、账户与合约权限、单笔/日/总损失上限及退出责任人（L1082-1086）。
- 明确 D13 的 STOCK/STOCK 禁止 LIVE 与后续 10%/3%限制，以及 D14 的跨桶转拨授权和账本归属规则。
- 在 `TINY_LIVE_APPROVAL_REQUEST.md` 中完成 owner 审批；审批前签名、广播必须继续保持 0（PRD L977-983）。
---

## 主脑补充核实（不在 codex 结论内，独立复算）

以下两项由主脑在收到 codex 报告后独立查证，均改变「还差多久」的量级。

### 补充一：`COVERAGE_INSUFFICIENT` 不是「再等 27 小时」，可能永远达不到

Stage A 表面上只剩三个 blocker，其中两个被当成「等时间」。但覆盖率这一条
**与已修的 `fee_growth` 缺口完全同构**：`coverage_ratio` 是**无窗口的累计比率**
（`scripts/lp_rh_readiness_v1_readonly.py:127-130`）：

```python
hours_covered    = (last - first).total_seconds() / 3600.0
expected_samples = hours_covered * 3600.0 / expected_interval_secs
coverage_ratio   = actual_samples / expected_samples
```

历史缺口一旦产生就**永久留在分子里**，无法被后续的完美采集抹掉。

as-of `2026-09-10T02:33:23Z` 实测：

| 量 | 值 |
|---|---|
| 时间跨度 | 45.3024 h |
| 实际样本 | 10,563 |
| 期望样本（15s） | 10,872.6 |
| 累计覆盖率 | **0.971527**（阈值 0.99） |
| 累计缺口 | 309.6 个样本 |

缺口的分布（按小时统计）证明它是**历史一次性事故**，不是当前采集器有病：

```
2026-09-08T05  164   <- 首个不完整小时（05:15 才开始）
2026-09-08T06  198   <- 缺 42  ┐
2026-09-08T07  219   <- 缺 21  │ 早期部署不稳，
2026-09-08T08  218   <- 缺 22  │ 8 小时共缺 ~182
...                            │
2026-09-08T13  231   <- 缺  9  ┘
2026-09-08T14  240   满格
...（此后基本满格，偶发 5~42 的空档，多为改代码/重启造成的分钟级中断）
2026-09-09T15  198   <- 缺 42（当晚重构 shadow runner 的时段）
```

窗口内覆盖率随窗口变短而变好，说明采集器现在是健康的：

| 窗口 | 窗口内覆盖率 | 每小时实得 |
|---|---|---|
| 近 6 h | 0.9965 | 239.2 |
| 近 12 h | 0.9833 | 236.0 |
| 近 24 h | 0.9818 | 235.6 |
| 近 36 h | 0.9869 | 236.9 |

**但累计比率要爬回 0.99，需要用未来的样本去稀释这 309.6 个历史缺口：**

| 今后的采集速率 | 累计比率达到 0.99 还需 |
|---|---|
| 完美 240/h（一个样本都不丢） | **83.7 小时 = 3.49 天** |
| 按近 6 h 实测 239.2/h | **128.2 小时 = 5.34 天** |
| 按近 24 h 实测 235.6/h | **永远达不到**（累计比率收敛到 0.9818） |

对照：`HOURS_COVERED_INSUFFICIENT` 只差 **26.7 小时**。

**结论：真正的长杆是 COVERAGE，最乐观也比表面上的「再等 27 小时」长 3 倍以上；
若今后的中断率维持在近 24 小时的水平，这道门永远过不去。**

这是一道「静默假红」——它看起来像在等时间，实际上等不到。
**处置需要用户决定**（改口径 = 放松闸门，主脑不自行决定）：

| 选项 | 做法 | 风险 |
|---|---|---|
| A | 改成**滑动窗口**（如最近 72 h 内的覆盖率），历史缺口自然滚出窗口 | 与 `fee_growth` 修法一致；但等于承认「早期数据不算数」 |
| B | 保持累计口径，**接受 3.5~5 天等待**，且期间必须零中断（改代码/重启都会再添缺口） | 最保守，但与「边改边跑」的现实冲突 |
| C | 从**最后一次代码变更**之后重新起算窗口（类似 `first_populated_time` 的做法） | 语义最贴近「当前代码的数据质量」，但每次改代码都重置计时 |

主脑倾向 **C**：它同时解决了「历史事故污染」和「改代码后数据口径变了」两个问题，
且与本仓库已接受的 `fee_growth` 窗口修法同源。

**用户 2026-09-10 批复「以上 abc 都同意」，按 C 执行**，并把 A 的兜底与 B 的信息
一起容纳（三个口径并列显示，只有判定窗口那个进 blockers）。
已写 spec `docs/specs/20260910_RH-02bn_judgment_window.md`，待 RH-02bm 落地后派
（两包改同一文件，不能并发）。

### C 的界定与实测后果（主脑已验证）

窗口起点取**采集侧代码**最后一次变更时间，白名单只有两个文件：
`scripts/lp_rh_collector_v1_readonly.py`、`scripts/lp_rh_store_v1_readonly.py`。

理由：Stage A 判的是「这批数据是怎么采出来的」。采集器或 schema 一变，
之前的数据就是另一套口径采的。**闸门自身的变更不改变已采数据的质量，
所以不重置计时**——这避免了「改个闸门就把 Stage A 计时清零」的过度激进。

```
采集侧最后变更 = f3fb67f @ 2026-09-09T16:05:41Z
                 "feat(rh-02ac): collect feeGrowthGlobal so the loop can value what it opens"
窗口内 2549 行 / 全量 10607 行
窗口 hours    = 10.642        （累计口径 45.30）
窗口 coverage = 0.9981   PASS （累计口径 0.9715  FAIL）
```

| | 改之前 | 改之后 |
|---|---|---|
| `COVERAGE_INSUFFICIENT` | 0.9715，最乐观 3.5 天，按实测速率**永远达不到** | **0.9981，已达标** |
| `HOURS_COVERED_INSUFFICIENT` | 还差 26.7 小时 | 还差 **61.4** 小时 |

**净效果是 Stage A 变得更远，不是更近。** 但它把一道「可能永远过不去的假红」
换成了一道「确定 61.4 小时后能过的真门」。阈值一个字没动（72 小时 / 0.99 保持不变），
本包只改「用哪段数据算」。

这个窗口起点与 `fee_growth` 的 `first_populated_time`（09-09T16:05:55）几乎重合，
因为正是同一次 commit 加的那两列——不是巧合，是同一次口径变更。

### 补充二：4,487 步通过了终闸，但 PRD 规定的账本表一行都没有

`reports/lp_rh/shadow.db`（影子运行器自有库）：

- `rh_shadow_episodes` 113 行，`rh_shadow_blockers` 241 行
- 其中 **24 个 episode 有 eligible steps，累计 4,487 步通过终闸十项合取**
- 全部落在 UTC 13-20（纽约 RTH）；非 RTH 被 `market_and_chain_risk_pass` 拦住，
  因为 `allows_new_position(OVERNIGHT, [])` 返回 `False`——**这部分行为是对的**
  （CORE 池套用股票时段规则是否合适是另一个产品问题，不是缺陷）

而 `reports/lp_rh/scanner.db` 里 PRD 规定的账本表：

```
rh_economic_evaluations   0
rh_gate_decisions         0
rh_shadow_positions       0
rh_position_marks         0
rh_journal                0
rh_bucket_reservations    0
```

**修好的 NAV/fee 公式产出的结果只落在 runner 自有的 `rh_shadow_episodes` 里，
没有进入毕业判定所依赖的账本。** Stage B 要求的 14 天证据
（零未解释账差、零不变量、零漏闸、全成本、HODL、OOS、最差日）
全部依赖这些空表——**这 14 天还没有开始计时**。

根因（writer 是缺失、未接线，还是写到别处）已派 codex 独立审查，结论待回。

### 补充三：Stage B 的两个证据被硬编码成「零」

`scripts/lp_rh_readiness_v1_readonly.py:758-760`：

```python
state["stage_b"] = stage_b_status(
    days_covered=span_days, weekends_covered=None, unexplained_ledger_diffs=0,
    invariant_violations=invariant_violations, missed_risk_events=0)
```

`stage_b_status()` 的接口本身是对的（`None` → `*_UNAVAILABLE` 阻断），
但调用处把 `unexplained_ledger_diffs` 和 `missed_risk_events` **写死成 `0`**,
而仓库里没有任何代码查过这两件事。这是静默假绿族的**第 25、26 例**。

当前被 `DAYS_COVERED_INSUFFICIENT`（1/14）挡着看不出来；跑满 14 天后
这两个假 `0` 会让 Stage B 直接放行。已派 RH-02bm 修复
（spec：`docs/specs/20260910_RH-02bm_stage_b_evidence.md`）。
