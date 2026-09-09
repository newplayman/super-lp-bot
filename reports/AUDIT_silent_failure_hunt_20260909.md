# 新发现（按危害排序）

1 | `scripts/lp_rh_calldata_decoder_v1_readonly.py:242-251` | 全新第17种：单边意图校验，缺失 claim 被当作“不冲突” | `decoded` 缺少 11 个意图字段、但 `intent` 完整时，代码只检查 `if x in claims` 的字段 | `decode_calldata("0x42966c68"+"00"*32)` 配完整 intent 返回 `(True, [])`，等于 11 个字段均未验证 | 缺任一 decoded claim 必须返回 `INTENT_CLAIM_MISSING`；同时校验原始 calldata hash

2 | `scripts/lp_rh_shadow_runner_v1_readonly.py:222-230,446-464`; `scripts/lp_rh_collector_v1_readonly.py:330-342` | 全新第17种：持久化健康标志未接线，风险字段缺失被当安全 | collector 写入 `health_flags_json=["CHAIN_DEGRADED"]`，loader 只保留字符串，未解析为 `chain_degraded`；`bool(None)` 变成 `False` | `market_and_chain_risk_pass` 可从应为 False 变为 True；实际数据库已有 52 行 `["CHAIN_DEGRADED"]`（`reports/rh_pivot/20260907T124500Z/STAGE_A_GATES_EVIDENCE.json:62-66`） | 解析 `health_flags_json` 映射到全部风险布尔值；JSON 缺失、损坏或未知 flag 时 fail-closed

3 | `scripts/lp_rh_readiness_v1_readonly.py:112-130` | 全新第17种：缺失审计计数被布尔化为零 | `signatures/broadcasts/keys_created=None` 时，`if signatures or ...` 不触发阻塞 | 输入 provider=2、capital=True、三个计数均为 `None`，返回 `live_allowed=True, blockers=[]` | 未知状态被误判为“零次未授权操作”，直接放行 LIVE readiness | 三个计数必须显式为非负整数且等于 0 才通过；`None` 应产生 INPUTS_UNAVAILABLE

4 | `scripts/lp_rh_gas_reserve_v1_readonly.py:44-57,100-137` | 全新第17种：非有限金额进入安全闸门 | `_to_decimal` 接受 `Decimal("Infinity")`，reserve gate 未做 finite 校验 | `native_balance_wei=Infinity` 时返回 `pass=True, reason="OK", available_usd=Infinity`，而正常所需仅 `$1.05` | 可用余额从有限值变成无穷大，且无异常、无失败状态 | 所有余额、价格、gas 结果先执行 `is_finite()` 与正数校验，否则返回 UNKNOWN/FAIL

5 | `scripts/lp_rh_meme_audit_v1_readonly.py:111-124,184-189` | 第6种变体：空结构化证据默认通过 | `holder_concentration_evidence={}` 时，`value.get(..., True)` 得到 True | 其余安全事实均通过时，`admission_check(...)` 返回 `(True, [])`；实际持仓集中度完全未知却被接纳 | 未知证据被误判为已验证 | Mapping 必须含显式布尔 `available=True` 或 `verified=True`；空对象和缺键均拒绝

6 | `scripts/lp_rh_exit_depth_v1_readonly.py:263-297` | 第6种：退出方向缺失默认 `zero_for_one=True` | 调用者未提供 `zero_for_one`、但实际退出方向为 token1→token0 | 在同一池状态、$100 仓位、100 bps 上限下：默认方向得到 `max_exit_usd=20.202`、`sufficient=False`；正确反向得到 `$100`、`sufficient=True`，低估约 4.95 倍 | 数字正常但退出深度结论方向依赖默认值 | `zero_for_one` 缺失时直接 `INPUTS_UNAVAILABLE`，禁止默认方向

7 | `scripts/lp_rh_pnl_v1_readonly.py:213-215` | 第6种：外部资金流缺失默认 0 | 事件步骤省略 `external_net_flow` 时直接按零计算 PnL | 固定价格、固定 LP 本金，钱包因外部入金增加 `$100` 时，输出 `net_pnl=+$100`；正确值应为 `$0` | PnL 被高估 `$100`，且 `attribution.reconciled=False` 仍输出数字 | `external_net_flow` 缺失必须返回 INPUTS_UNAVAILABLE；只允许显式 `"0"`

8 | `scripts/lp_rh_premium_guard_v1_readonly.py:115-134` | 全新第17种：时间方向未校验 | `generated_at` 晚于 `now` 时，负龄仍满足 `age_secs <= max_age_secs` | 生成时间领先当前时间 1 小时，返回 `("FRESH", -3600)` | 尚未生成的未来报价被判为新鲜 | 对未来时间设置容差；超过容差返回 INVALID/UNKNOWN，不得返回 FRESH

# 已查过但判定为安全的路径

- `lp_netcover_engine_v1_readonly.py`、`lp_rh_netcover_inputs_v1_readonly.py`：金额有限性、缺失输入和绝对收益闸门均能阻断。
- `lp_swap_cost_model_v1_readonly.py`、`lp_v3_fee_share.py`、`lp_v3_position_value.py`、`lp_rh_v3_inventory_v1_readonly.py`：检查了 raw/human/USD 换算和 token decimals，未发现新的量纲错误。
- `lp_rh_in_range_v1_readonly.py`、`lp_rh_markout_v1_readonly.py`、`lp_rh_stock_reference_v1_readonly.py`、`lp_rh_reference_freshness_v1_readonly.py`：缺数据返回 None/不可用，未来时间已有容差保护。
- `lp_rh_terminal_gate_v1_readonly.py`、`lp_rh_store_v1_readonly.py`、`lp_rh_shadow_watchdog_v1_readonly.py`、`lp_rh_reorg_resolution_v1_readonly.py`、`lp_rh_reorg_rollback_v1_readonly.py`：缺失、过期、争议状态不会直接变成通过。
- 未发现新的无出处经济常量；50/30/20、active fraction、coverage 阈值、organic window 参数均有 PRD/spec 或明确的 proposed/policy 标注。
- 导入级全局 Decimal 精度修改属于已确认第16类，未重复列为新发现：`lp_bsc_quoter_staticcall_amount_fix_v1_readonly.py:23`、`lp_bsc_pancakeswap_v3_precise_quote_v1_readonly.py:23`、`lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py:23`、`lp_precise_quote_pipeline_v1_readonly.py:25`、`lp_bsc_fee_velocity_smoke_v1_readonly.py:44`、`strategy_evidence_r4b_active_liquidity_replay.py:21`、`strategy_evidence_r4c_independent_clmm_liquidity_replay.py:48`、`lp_base_m1_c5_dry_run_v1_readonly.py:36`、`lp_bsc_fee_velocity_short_backfill_v2_readonly.py:39`、`lp_bsc_realdata_economics_with_recovered_fee_v1_readonly.py:36`。

# 我不确定的

- `scripts/lp_rh_coverage_audit_v1_readonly.py:226-227` 未按 `asset_address` 过滤，若数据库包含多个资产会合并计算覆盖率；当前证据显示该数据库只有一个资产，无法证明现阶段已触发。
- `scripts/lp_rh_pool_probe_v1_readonly.py:113-122,261-274` 对 V4 pool key 缺失字段使用零值，但只有声明的 `pool_id` 恰好匹配该合成 key 时才会产生错误 attestation；未找到现实输入证据。
- `scripts/lp_rh_size_interval_v1_readonly.py:38-51,80-102` 接受 `Infinity`，但尚未确认上游是否允许“无上限”语义，因此未计入铁证。