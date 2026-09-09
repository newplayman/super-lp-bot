> # ⛔ 本文档已作废（2026-09-09）
>
> **不要用本文档里的任何收益数字做决策。**
>
> 它的结论建立在三个已被证伪的公式之上：
>
> 1. **手续费量纲错误** —— `accrued += position_usd * (d0+d1) / 2**128`。
>    feeGrowthGlobal 的单位是「每单位 liquidity 的 token 数」(Q128)，要乘仓位的
>    **liquidity** 而非 **USD 名义值**，且两种不同 decimals 的 token 原始整数被直接相加。
>    实测**虚高 1022 倍**（隐含年化 29076% vs 真实 26.7%）。已修：commit `12efd38`。
> 2. **HODL 基准规模不一致** —— 用虚拟 `1 token0 + 1 token1`（约 $2485）对比 $1000 仓位，
>    差 2.485 倍；且 `net_pnl` 与 `hodl_delta` 各取各的可用步首尾，**窗口不对齐**。
>    已修：commit `9c59e2e`。
> 3. **NAV 从不市价重估** —— `lp_principal` 恒为 `position_usd`，NAV 唯一变动项是
>    只增不减的手续费，**`net_pnl` 在数学上不可能为负**。已修：commit `9c59e2e`。
>
> 修正后的真实经济结果见 **`reports/ECONOMICS_corrected_20260909.md`**，
> 独立参考实现见 **`reports/golden_reference_20260909.py`**，
> 作废判定的完整依据见 **`reports/AUDIT_stale_conclusions_20260909.md`**。
>
> **保留本文件是为了留痕，不是为了引用。**

---

# Clean Proof Surface v1

- source: `shadow_outcome_labels_repaired_terminal_v1`
- rule:
  - `entry_trusted = true`
  - `outcome_type in (future_position_mark, terminal_exit_mark)`
  - `mark_source != pool_mark_only`
  - `terminal_value_usd > 0 if terminal_exit_mark`
  - `net_pnl_pct calculable`
  - `invalid_reason not in (entry_untrusted, terminal_value_zero_bug, pool_mark_only)`

## Summary

| Horizon | total count | selected count | top20 count | excluded entry_untrusted count | excluded terminal_zero_bug count | excluded pool_mark_only count | median_net_pnl_pct | p10_net_pnl_pct | top20 vs bottom20 pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6h | 18618 | 18618 | 3436 | 1935 | 27 | 5767 | 0.158153 | 0.003778 | better |
| 24h | 10178 | 10178 | 1900 | 1921 | 27 | 14131 | 0.160851 | 0.007943 | better |
