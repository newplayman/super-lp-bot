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

# Position-Level Quarantine Simulation

| scenario | horizon | position_count | median | p10 | p5 | p1 | top20_vs_bottom20_signal | terminal_signal | combined_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline position-level proof | 6h | 32 | 0.041518 | 0.000065 | 0.000044 | -2.619847 | better | worse | better |
| exclude worst 1 position | 6h | 31 | 0.032134 | 0.000064 | 0.000042 | -2.657816 | better | worse | better |
| exclude worst 3 positions | 6h | 29 | 0.023516 | 0.000062 | 0.000040 | -2.733754 | better | worse | better |
| exclude worst 5 positions | 6h | 29 | 0.023516 | 0.000062 | 0.000040 | -2.733754 | better | worse | better |
| exclude worst 1 pool | 6h | 27 | 0.021416 | 0.000060 | 0.000038 | -2.809693 | better | worse | better |
| exclude worst 3 pools | 6h | 24 | 0.021254 | 0.000057 | 0.000034 | -2.923601 | better | worse | better |
| baseline position-level proof | 24h | 30 | 0.029479 | -0.001949 | -1.395984 | -2.537614 | better | better | better |
| exclude worst 1 position | 24h | 29 | 0.034862 | 0.000058 | -0.011849 | -1.821359 | better | better | better |
| exclude worst 3 positions | 24h | 27 | 0.069957 | 0.000534 | 0.000066 | 0.000040 | better | worse | better |
| exclude worst 5 positions | 24h | 27 | 0.069957 | 0.000534 | 0.000066 | 0.000040 | better | worse | better |
| exclude worst 1 pool | 24h | 26 | 0.029479 | 0.000067 | 0.000039 | -1.891476 | better | better | better |
| exclude worst 3 pools | 24h | 23 | 0.024095 | 0.000224 | 0.000065 | 0.000038 | better | better | better |
