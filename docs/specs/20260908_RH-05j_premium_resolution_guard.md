# RH-05j：溢价序列的分辨率闸（信号低于数据源噪声地板时必须拒答）

## 背景

首次有效判定就暴露了缺陷，证据见
`reports/rh_pivot/20260907T124500Z/RH-05-research/PREMIUM_REGIME_FIRST_VALID_20260908.md`：

- **AMC**：参考价量化步长 40.1 bps、买卖价差 40.1 bps，实测溢价标准差仅 34.3 bps。
  **整个信号不到参考价的一个报价档位**，却被判成 `MEAN_REVERTING` 并给出
  `haircut = 0.00172` 这样一个具体数字。
- **SGOV**：34 个样本里参考价只有 1 个取值，溢价方差全部来自链价一侧，
  `PERSISTENT_OFFSET` 是同义反复。

模块当前**没有任何分辨率检查**，于是在数据不足以支撑结论时给出了看起来正常的分类。
这是本仓反复出现的那族缺陷：不抛异常、只在部分输入上给错答案。

## 只改一个模块，只加不减

改 `scripts/lp_rh_premium_series_v1_readonly.py`，测试追加进
`tests/test_lp_rh_premium_series_v1_readonly.py`。**现有 24 条测试一条不许改、不许删、
不许加 skip/xfail。** 若某条因本次变更失败，**停下来写明是哪条、为什么**，交主脑裁决。

### 1. `series_stats` 新增分辨率字段

`samples` 的每个元素**可选**带 `reference_bid` / `reference_ask`。新增返回字段：

- `n_distinct_reference`：参考价不同取值个数。
- `reference_quantum_bps`：相邻不同参考价的**最小步进**折算 bps
  （`min_step / median_reference_price * 10000`）。不同取值少于 2 个 → `None`。
- `reference_spread_bps`：`(ask - bid) / mid * 10000` 的中位数；缺 bid/ask → `None`。
- `resolution_floor_bps`：`(reference_quantum_bps or 0) + (reference_spread_bps or 0)`；
  **两者都为 `None` 时该字段为 `None`**（未知，不是 0）。

### 2. `premium_regime` 新增两个前置判定

在现有判定**之前**插入，顺序如下：

1. `n_distinct_reference is not None and n_distinct_reference < 2`
   → 返回 `"REFERENCE_CONSTANT"`。（SGOV 的情形：参考价不动，回复无从谈起。）
2. `resolution_floor_bps is not None and stdev_bps is not None
   and stdev_bps <= resolution_floor_bps`
   → 返回 `"INSUFFICIENT_RESOLUTION"`。（AMC 的情形：信号在噪声地板以下。）

`resolution_floor_bps` 为 `None`（无 bid/ask 也无足够取值）时**不得放行**，
按 `"INSUFFICIENT_RESOLUTION"` 处理——**无法证明信号高于噪声，就不许给分类**。

### 3. `lvr_haircut_frac` 对两个新 regime 返回 `None`

`REFERENCE_CONSTANT` 与 `INSUFFICIENT_RESOLUTION` 一律返回 `None`，**不是 0**。
未知损耗不等于无损耗。现有的
`MEAN_REVERTING → 按 stdev 计算`、`PERSISTENT_OFFSET → Decimal(0)`、
其余 `→ None` 三条**保持不变**，`LVR_COEFFICIENT_MODEL=0.50` 数值不得改。

## 新增测试（**≥12 条**）

- 参考价全窗口只有 1 个取值 → `premium_regime` 返回 `"REFERENCE_CONSTANT"`。
- 同上场景 `lvr_haircut_frac` 返回 `None`（**`is None` 断言，不是 0**）。
- **复现 AMC**：参考价只在 `2.495/2.505/2.515/2.525` 四档跳、bid/ask 相差 0.01、
  溢价 stdev 约 34 bps → `"INSUFFICIENT_RESOLUTION"`，haircut `None`。
  **这条是本包核心，直接对应实盘误判。**
- **复现 SPY**：参考价 34 个不同取值、步进 0.005/766.85、价差 0.03 →
  `resolution_floor_bps < 1`，regime **仍按原逻辑判定**（不被新闸误拦）。
  **这条防止修过头。**
- `stdev_bps` 恰好等于 `resolution_floor_bps` → 判 `INSUFFICIENT_RESOLUTION`（边界取闭区间）。
- `stdev_bps` 略大于地板 → 放行按原逻辑判定。
- 样本不带 bid/ask 且参考价取值 ≥2 但只有 2 个 →
  `reference_spread_bps is None`，`resolution_floor_bps` 只由量化项构成，闸仍生效。
- 完全无 bid/ask 且参考价取值不足 2 → `resolution_floor_bps is None` →
  判 `INSUFFICIENT_RESOLUTION`（**不许因为算不出地板就放行**）。
- `n_distinct_reference` / `reference_quantum_bps` / `reference_spread_bps` /
  `resolution_floor_bps` 四个字段在 `INPUTS_UNAVAILABLE` 与 `INSUFFICIENT_SAMPLES`
  两种 status 下均存在且为 `None`（结构稳定）。
- 系数核对：源码里 `0.50` 仍在，且不含 `0.25`/`0.75` 之类改写。
- 原有五种 regime 的返回值字符串**未被改名**（对每个都断言一次）。

## 不许动
不改其他脚本。不联网。金额与比率用 `Decimal`。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_premium_series_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥36 全绿（原 24 + 新增 ≥12）；全量 0 failed / 14 skipped；
`git diff --stat` 只含上述两个文件。两条命令尾部原样贴出。
