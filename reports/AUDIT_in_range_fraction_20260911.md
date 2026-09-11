# AUDIT：in-range 时长折算——机制缺失，但当前数据未受影响（2026-09-11）

- 性质：只读实测。未改任何代码。
- 触发：`RH05_EVIDENCE_COMPLETE.md` 指出「in-range 时长折算仍未实现——
  当前 fee-growth 是全区间上界……这是 STOCK 策略进入 Shadow 前必须补的最后一块」。
- 主脑核实后发现：这不只影响 STOCK，**CORE 池的 fee 计算走的是同一条路径**。

## 一、机制确实缺失

`scripts/lp_rh_in_range_v1_readonly.py` 实现完整（PRD T37，codex 对账标为
「已实现且有测试」），提供：

```
tick_from_price(price_human, dec0=, dec1=)
in_range_fraction(samples, tick_lower=, tick_upper=, dec0=, dec1=)
effective_fee_ev(full_range_fee_ev=, in_range_fraction=, concentration_multiplier=)
range_scan(samples, center_tick=, ...)
```

**被生产代码引用 0 次**（`grep -rn "lp_rh_in_range" scripts/` 除自身外无结果）。

这是本轮发现的**第四个「模块写好了但零引用」**，前三个是
T29 native gas reserve、T31 size interval、T34 gas estimator，均已在
`104077e` / `f04bef5` 及在建包中接线。

runner 的 fee 计算按 `L_pos × Δfee_growth / 2^128` 分摊全池费用增长，
**隐含假设头寸 100% 时间在区间内**。集中流动性头寸一旦价格越界就不再赚费，
这个假设会高估收益。

## 二、但当前数据上高估幅度是零

用判定窗口内的真实样本实测（`reports/lp_rh/scanner.db`）：

```
range_pct = 10.0%   入场价 = 2484.0
区间 = [2235.60, 2732.40]   ticks = [-199198, -197191]

样本            5038
跳过（无价格）      6      <- 缺数据不算出区间，被排除在分母外
在区间内         5032
in_range_fraction  1.0000
出区间次数          0

=> 当前 fee 按 100% 在区间计，实际也是 100.0%，高估倍数 1.00x
```

**结论：当前 CORE 池的 fee 收益在这个维度上是干净的。**
今晚早些时候修掉的 1022 倍 fee 高估是量纲问题（`12efd38`），
与本项是两个独立的高估源；这一项当前恰好没有发生。

`in_range_fraction` 的实现把「无价格读数」的样本**跳过并计入 skipped**，
既不算在区间内也不算出区间，也不进分母——缺数据不等于出区间，
这个区分是对的，6 个跳过样本正是 `CHAIN_DEGRADED` 期间的记录。

## 三、接线的难点：`concentration_multiplier`

`effective_fee_ev` 的三个入参里，前两个都能算，第三个不行：

```python
"""concentration_multiplier MUST be supplied by the caller -- it depends on
range width and the liquidity distribution, which this module does not
estimate.  It only converts.  Any None input yields None (never 0)."""
```

集中度放大倍数取决于区间宽度与池内流动性分布，需要单独推导，
不是接线能顺带解决的。

**建议的接线方式**：先只接 `in_range_fraction` 这一半，
`concentration_multiplier` 取 `1.0` 并显式标记为「未估算」。
这样价格越界时费用会被正确折减，而集中度放大暂不计入——
方向上**低估收益**，是安全的一侧。真正估算放大倍数是后续独立工作。

## 四、为什么现在不改

`scripts/lp_rh_shadow_runner_v1_readonly.py` 正被 RH-02cl（T31 size interval）
改动，两包冲突。接线 spec 已备好，待 cl 落地后派发。

在此期间这份报告本身就是有价值的产出：它把「fee 有没有被 in-range 高估」
从一个悬而未决的疑问变成了一个有数字的结论。
