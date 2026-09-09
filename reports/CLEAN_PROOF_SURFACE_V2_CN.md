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

# Clean Proof Surface v2

- source: `shadow_outcome_labels_repaired_terminal_v1`
- based on `PROOF_EXCLUSION_POLICY_CN.md`

## Summary

| Horizon | raw count | excluded count | clean count | selected clean count | top20 clean count | median_net_pnl_pct | p10_net_pnl_pct | p5_net_pnl_pct | p1_net_pnl_pct | top20 vs bottom20 pct_signal | top20 p10 | bottom20 p10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 6h | 26275 | 9761 | 16514 | 16514 | 3436 | 0.110705 | 0.003071 | 0.000458 | 0.000078 | better | 0.233600 | 0.028041 |
| 24h | 24485 | 16295 | 8190 | 8190 | 1875 | 0.118443 | 0.007121 | 0.000441 | 0.000193 | better | 3.591802 | 0.093351 |
