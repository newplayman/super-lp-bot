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

# Position-Level Clean Proof

| score_mode | horizon | position_count | future_position_count | terminal_position_count | avg | median | p10 | p5 | p1 | win_rate | pct_signal | terminal_24h_signal | terminal_p10 | terminal_p5 | terminal_p1 | worst_position_contribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_decision_score | 6h | 32 | 21 | 11 | 0.045544 | 0.041518 | 0.000065 | 0.000044 | -2.619847 | 0.968750 | better |  |  |  |  |  |
| open_decision_score | 24h | 30 | 7 | 23 | 0.345617 | 0.029479 | -0.001949 | -1.395984 | -2.537614 | 0.900000 | better | better | -0.015808 | -2.271757 | -2.539156 | shadow-pos-c5e8f94d64e82415136312e3 |
| first_selected_score | 6h | 32 | 21 | 11 | 0.045544 | 0.041518 | 0.000065 | 0.000044 | -2.619847 | 0.968750 | better |  |  |  |  |  |
| first_selected_score | 24h | 30 | 7 | 23 | 0.345617 | 0.029479 | -0.001949 | -1.395984 | -2.537614 | 0.900000 | better | better | -0.015808 | -2.271757 | -2.539156 |  |
| max_score_before_open | 6h | 32 | 21 | 11 | 0.120423 | 0.041518 | 0.000065 | 0.000044 | -2.619847 | 0.968750 | better |  |  |  |  |  |
| max_score_before_open | 24h | 30 | 7 | 23 | 0.419469 | 0.029479 | -0.001949 | -1.395984 | -2.537614 | 0.900000 | better | better | -0.015808 | -2.271757 | -2.539156 |  |
