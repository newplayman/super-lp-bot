# AUDIT：有机成交量折减未接线——fee 当前高估约 11%（2026-09-11）

- 性质：只读实测。未改任何代码。
- 触发：`RH05_EVIDENCE_COMPLETE.md` 列「有机成交量验证：未做，PRD §10.3 要求
  区分 raw 与 organic」。核实后发现：**数据早已在采，只是没人用**。

## 一、数据齐全，接线为零

`reports/lp_rh/organic.db` 的 `rh_organic_windows` 有 **195 行**，
由 `scripts/lp_rh_organic_recorder_v1_readonly.py` 持续写入：

```
window_start_block, window_end_block, sample_time, provider,
n_events, n_unique_senders, top1_share, top5_share, hhi,
round_trip_share, total_volume, round_trip_volume,
concentration_excess_volume, organic_fraction, coverage_frac,
fetch_status, estimate_status, error
```

`grep -rn "organic" scripts/lp_rh_shadow_runner_v1_readonly.py
scripts/lp_rh_netcover_inputs_v1_readonly.py` → **无结果**。

这是本轮发现的**第五个「数据/模块就位但零引用」**。前四个是
T29 native gas reserve、T31 size interval、T34 gas estimator、
T37 in-range fraction，均已接线或在接（`104077e` / `ad8d27b` / `f04bef5` / RH-02cm）。

## 二、高估幅度：平均 11.42%，最差 34.8%

192 个 `estimate_status = COMPUTED` 的窗口，
2026-09-08T19:25 ~ 2026-09-11T08:03：

| 指标 | min | p50 | max | avg |
|---|---:|---:|---:|---:|
| `organic_fraction` | **0.7419** | 0.9026 | 0.9728 | **0.8975** |
| `round_trip_share` | 0.0235 | 0.0900 | 0.2325 | — |
| `n_unique_senders` | 75 | 106 | 170 | — |

`coverage_frac` 全部为 `1.0000`——窗口内事件全部取到，不是抽样估计。
另有 3 个窗口 `INPUTS_UNAVAILABLE`（占 1.5%），如实标注未计入统计。

runner 的手续费来自链上 `feeGrowthGlobal` 的增量，**那是全部成交产生的费用**，
包含往返套利与集中地址的非有机部分。按有机占比折算：

```
平均:  1 / 0.8975 - 1 = 11.42%  高估
最差:  1 / 0.7419 - 1 = 34.79%  高估
```

## 三、这是第三个独立的 fee 高估源

今晚已处理的两个：

| 源 | 状态 | 幅度 |
|---|---|---|
| `fee_growth` 量纲错误（乘 USD 名义值而非 `L_pos`） | 已修 `12efd38` | **1022 倍** |
| in-range 时长折算缺失 | 机制缺失，RH-02cm 在接 | 当前 **1.00x**（价格未越界） |
| **有机成交量折减缺失** | **未接线** | **当前 1.11x** |

三者互相独立，会叠乘。前两个已经处理，这一个是当前唯一正在生效的。

## 四、修正方向是保守的

今晚修正后的经济结论是 **LP 跑输持币**（`net_pnl` 为负，
`reports/ECONOMICS_corrected_20260909.md`）。接入有机折减会让 fee 再降约 11%，
**结论只会更负**。

所以这不是一个「可能推翻结论」的修正，而是一个「让已有结论更扎实」的修正——
方向安全，但不做就是在用一个已知偏高的数字。

## 五、接线要点（spec 待派，runner 当前被 RH-02cm 占用）

1. 按 `sample_time` 取**最接近且不晚于**该步的窗口，不要用最新窗口套全程
2. `estimate_status != "COMPUTED"` 或 `coverage_frac < 1` 的窗口 →
   **不折减并标记**，不要拿一个不可信的比例去乘
3. 取不到窗口 → 同样不折减并标记为 `ORGANIC_FRACTION_UNAVAILABLE`，
   **绝不默认 1.0 当作「全部有机」**——那正是本仓库 27 例静默假绿的形状
4. 折减后的 fee 与原始 fee 都要保留（`cost_components_json` 分别记录），
   便于回溯两者差异
