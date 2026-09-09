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

# Full Strategy Clean Proof

| horizon | total count | future count | terminal count | terminal share pct | avg | median | p10 | p5 | p1 | win_rate | top20 median | bottom20 median | pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 24h | 22453 | 10178 | 12275 | 54.6698 | 0.919996305689333032438540251124828911653046418 | 0.091393 | -2.22786979715392 | -2.37094620269922 | -2.54400081819266 | 0.82848617111299158242 | 4.126081 | 0.0699570933516261 | better |
| 6h | 24229 | 18618 | 5611 | 23.1582 | 0.841224910052526965814633894043161855336711125 | 0.140837 | 0.000439 | -0.0197680684341946 | -2.52197814125685 | 0.94279582318708985100 | 2.053079 | 0.155292 | better |

## Judgment

- combined_clean better in both horizons, but future_clean and terminal_clean need to be read separately.
- terminal_clean 24h worse prevents current full-strategy proof from being accepted.
