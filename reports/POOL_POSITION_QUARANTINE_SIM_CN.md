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

# Pool / Position Quarantine Simulation

| scenario | horizon | count | selected_count | top20_count | median | p10 | p5 | p1 | pct_signal | terminal_clean_signal | combined_clean_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline clean proof | 6h | 24229 | 24229 | 4846 | 0.140837 | 0.000439 | -0.019768 | -2.521978 | better | better | better |
| exclude worst 1 position | 6h | 23947 | 23947 | 4790 | 0.135143 | 0.000441 | -0.019768 | -2.521978 | better | better | better |
| exclude worst 3 positions | 6h | 19260 | 19260 | 3852 | 0.222133 | 0.000609 | 0.000064 | -2.521978 | better | better | better |
| exclude worst 5 positions | 6h | 17818 | 17818 | 3564 | 0.218925 | 0.000779 | 0.000356 | 0.000031 | better | better | better |
| exclude worst 1 pool | 6h | 19335 | 19335 | 3867 | 0.077965 | 0.000420 | -2.227870 | -2.521978 | better | better | better |
| exclude worst 3 pools | 6h | 11853 | 11853 | 2371 | 0.052169 | 0.000407 | 0.000064 | -2.521978 | better | better | better |
| exclude pool_mark_only terminal paths | 6h | 24229 | 24229 | 4846 | 0.140837 | 0.000439 | -0.019768 | -2.521978 | better | better | better |
| baseline clean proof | 24h | 22453 | 22453 | 4491 | 0.091393 | -2.227870 | -2.370946 | -2.544001 | better | worse | better |
| exclude worst 1 position | 24h | 22171 | 22171 | 4435 | 0.097926 | -2.227870 | -2.370946 | -2.521978 | better | better | better |
| exclude worst 3 positions | 24h | 17484 | 17484 | 3497 | 0.218925 | 0.000064 | -0.019768 | -2.521978 | better | worse | better |
| exclude worst 5 positions | 24h | 16042 | 16042 | 3209 | 0.511073 | 0.000779 | 0.000274 | 0.000064 | better | better | better |
| exclude worst 1 pool | 24h | 18004 | 18004 | 3601 | 0.034862 | -2.227870 | -2.370946 | -2.521978 | better | better | better |
| exclude worst 3 pools | 24h | 10967 | 10967 | 2194 | 0.021822 | 0.000270 | 0.000064 | -2.521978 | better | better | better |
| exclude pool_mark_only terminal paths | 24h | 22453 | 22453 | 4491 | 0.091393 | -2.227870 | -2.370946 | -2.544001 | better | worse | better |
