# W2 SPEC — 全成本组合账和跨轮连续性

**目标 SHA**: 18a8f39744af2d61d16737b7311d88cd88accea9 (W1 完成后)
**owner-授权**: 已批 V3 taskpack（仅代码+测试，不启动服务）

## 范围

只动：
- `scripts/lp_rh_shadow_runner_v1_readonly.py` (run_episode / episode_summary / cost flow)
- `scripts/lp_rh_shadow_daemon_v1_readonly.py` (run_one_round / continuous portfolio)
- `scripts/lp_rh_pnl_v1_readonly.py` (NAV / NetPnL 公式按 PRD v1.1 §11-16)
- `tests/test_lp_rh_shadow_runner_v1_readonly.py` (新增部分仓 100/1000 测试)
- `tests/test_lp_rh_shadow_daemon_v1_readonly.py` (新增跨轮 / 重启 / 重叠样本测试)
- `tests/test_lp_rh_pnl_v1_readonly.py` (新增 collect/remove/残余库存会计)
- `tests/test_lp_rh_reconciliation_v1_readonly.py` (新增持久化账本对账)
- `specs/W2_FULL_COST_ACCOUNTING_V3.md` (本文件追加 patch log)

**不许动**：
- `scripts/lp_rh_calldata_*` (W1 范围)
- `internal/adapters/` (Go)
- 六个冻结常量
- main 分支

## 必须交付

### G1: 真实入口部分仓控制（合法 part-size 100/1000）

新建 `tests/test_lp_rh_shadow_runner_v1_readonly.py::TestFullCostPartSizeControl`:
- `test_legal_part_size_round_trip_cost_10` — capital=1000, position=100, 初始其他 900, 满足 CORE 42.5% 上限；round-trip cost 注入 10；flat price；fee/reward=0；断言：
  - 最终 `episode_summary.net_pnl == Decimal("-10")` 精确
  - `episode_summary.nav_start == Decimal("1000")`
  - `episode_summary.nav_end == Decimal("990")`
  - `steps[0].nav == Decimal("990")`（成本已计入开仓步）
  - `rh_tx_intents` 有 grant 行 + WHITELIST_PASSED 状态
  - `rh_position_marks` 有 entry 行
  - `rh_journal` 有 2 行 debit/credit 反映资产流出
  - 完全不能 position=0 时通过（必须真有 grant）
- `test_no_admission_keeps_capital_unchanged` — 同资本但 admission 拒绝（任何原因）→ 断言 NAV 1000→1000, PnL 0, rh_tx_intents 无 WHITELIST_PASSED 行, 无 cost 行
- `test_external_funding_increases_nav_only` — 无交易，注入 +10 资金 → NAV +10, PnL 0, journal 有 external_flow 行
- `test_full_capital_accounting_arithmetic_control` — capital=1000, position=1000 必须**只在会计层**验证算术（不要求通过 CORE 准入；用 mock 或 fake admission）

### G2: collect / remove 会计

新建 `tests/test_lp_rh_pnl_v1_readonly.py::TestCollectRemoveAccounting`:
- `test_collect_no_gas_does_not_change_nav` — collect 后未收 gas → NAV 不变
- `test_collect_with_gas_deducts_once` — collect 后收 gas 一次 → NAV -gas
- `test_remove_returns_principal_not_fee_income` — remove 后本金回收不算手续费收入；journal 不应有 fee 行（仅有 amount_received 行）
- `test_remove_succeeds_but_swap_fails_keeps_inventory_risk` — remove 后兑换失败 → 保留 risk inventory，liquidation_nav != reference_nav；标记 remove_incomplete 状态

### G3: 跨轮 / 重启 / 重叠样本连续性

新建 `tests/test_lp_rh_shadow_daemon_v1_readonly.py::TestCrossRoundContinuity`:
- `test_two_rounds_preserve_capital_and_dont_reset` — 跑 2 轮，每轮 round-trip cost 10 → 总 cost 20，portfolio_id 不变，初始 HODL lots 不重建
- `test_restart_resume_uses_same_portfolio_id` — 关闭再打开 daemon，portfolio_id 一致，初始 capital 一致，无重复赠本金
- `test_overlapping_samples_not_double_charged` — 同一样本被两轮读到 → journal 不重复计费（依靠 unique idempotency_key）
- `test_late_sample_after_window_close_not_counted_as_active` — 样本超出观察窗口 → 不进入 active episode，journal 无对应 debit
- `test_reorg_dedup_by_block_hash_tx_id` — 同 block_hash+tx_id 重复样本 → 不重复入库（unique constraint）
- `test_unobserved_window_does_not_silently_fill_zero` — 缺观测时间窗口 → 不填 0，标记 UNOBSERVED

### G4: 边界与场景变异

新建 `tests/test_lp_rh_shadow_runner_v1_readonly.py::TestAccountingEdgeVariants`:
- `test_variant_remove_capital_baseline_zero_pnl` — 去掉 capital baseline（None）→ 必须失败（强制要求 baseline）
- `test_variant_missing_one_cost_leak` — 漏一次成本注入（只 8 不是 10）→ 必须 fail 断言 nav_end=992 ≠ 期望 990
- `test_variant_double_deduct_one_cost` — 多扣一次（注入 15 不是 10）→ 必须 fail 断言
- `test_variant_lost_idle_cash` — 不持有 900 闲置 → 必须 fail
- `test_variant_collect_repeated_incorrectly` — collect 重复算利 → 必须 fail
- `test_variant_reset_baseline_mid_episode` — episode 中途 reset nav_start → 必须 fail
- `test_usdg_not_one_usd_treatment` — USDG 实际价格 1.02 时不能当 1.0 计入 NAV
- `test_out_of_range_position_does_not_accrue_fee` — 价格出区间 → 无 fee 行
- `test_dust_residual_inventory_tracked` — 残余 dust inventory 保留 + liquidation_nav 反映风险
- `test_partial_decimal_token_sorts_correctly` — token0 (dec=18) / token1 (dec=6) 时排序 + amount 准确

## 验收命令

```bash
# After G1+G2:
python -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py tests/test_lp_rh_pnl_v1_readonly.py -v --tb=short -p no:cacheprovider 2>&1 | tail -15

# After G3:
python -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -v --tb=short -p no:cacheprovider 2>&1 | tail -15

# Full regression:
python -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -5
# Baseline must remain ≤53 fail
```

## 风险与边界

- 不连 RPC，不启动 daemon
- 不创建私钥
- 不放宽六个常量
- 不修改 runner 主体业务（只在 run_one_round / episode_summary 入口和会计层）
- 不修改 runner 中现有的 39 个 A 类 fail（那是 W1+2 协作的部分，但 W2 范围只加测不修旧 fail）

## 输出要求

每完成一个 G 分块运行对应 pytest，贴最后 10 行。最后一次全量回归贴最后 5 行 + 总 fail/pass/skip 计数与 V2 基线（53/5059/14）+ W1 后基线对比。
