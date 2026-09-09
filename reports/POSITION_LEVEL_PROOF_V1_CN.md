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

# Position-Level Proof V1

| score_mode | horizon | position_count | future_position_count | terminal_position_count | invalid_position_count | win_rate | avg_net_pnl_pct | median_net_pnl_pct | p10_net_pnl_pct | p5_net_pnl_pct | p1_net_pnl_pct | top20_position_count | bottom20_position_count | top20_median | top20_p10 | top20_p5 | bottom20_median | bottom20_p10 | bottom20_p5 | top20_vs_bottom20_signal | future_only_signal | terminal_only_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_decision_score | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| open_decision_score | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| first_selected_score | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| first_selected_score | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| max_score_before_open | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| max_score_before_open | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| median_score_before_open | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| median_score_before_open | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |

## Judgment

- decision_trace_level_better_survives_position_level = yes
- full_strategy_position_level_pass = no
- future_only_position_level_better = no
- terminal_only_position_level_24h = better
- position_level_tail_acceptable = no
