# RH-04e：in-range 时长折算（把全区间上界变成真实收益）

## 背景

主脑 09:1x 实测的 `feeGrowthGlobal` 年化 27.34% 是**全区间头寸的上界**。集中流动性头寸只在价格落在其 `[tick_lower, tick_upper)` 内时才计费；出区间时收益为 **0**，但库存风险仍在。PRD §10.1 明令「在远离现价的『合理价格』摆区间也不一定赚费：可能完全不活跃，或在价格跳变时被单向成交；此类收益必须按**真实在区间时长**计算」。

这是 STOCK 与 CORE 进入 Shadow 前的最后一块拼图。活库 `reports/lp_rh/scanner.db` 已有 **1966 条真实价格样本**（9 小时，15 秒间隔）可直接用作时间序列。

## 只新建两个文件

1. `scripts/lp_rh_in_range_v1_readonly.py`（≤280 行）
   - `tick_from_price(price_human, *, dec0, dec1) -> int`：反算 tick。**必须先按精度归一再取对数**（今天两个 bug 都出在这——见 `COST_MODEL_PRICE_SCALE_BUG.md`）。
   - `in_range_fraction(samples, *, tick_lower, tick_upper, dec0, dec1) -> dict`：
     样本是 `[{"sample_time","reference_mid"}]`。返回
     `{"total_samples","in_range_samples","fraction","first","last","excursions": [{"start","end","duration_secs","side"}]}`。
     - `side` 取 `"BELOW"` / `"ABOVE"`（价格跌破下界还是升破上界）——PRD §10.3 的「跌破下界不得下移区间」需要这个区分。
     - `reference_mid` 为 `None` 的样本**跳过并计数**，不当作 out-of-range（缺数据 ≠ 出区间）。
   - `effective_fee_ev(*, full_range_fee_ev: Decimal, in_range_fraction: Decimal, concentration_multiplier: Decimal) -> Decimal`：
     `full_range_fee_ev × in_range_fraction × concentration_multiplier`。**`concentration_multiplier` 必须由调用方显式提供**，不得在本模块内假设——它取决于区间宽度与流动性分布，模块只做折算不做估计。任一入参为 `None` → 返回 `None`。
   - `range_scan(samples, *, center_tick, widths_ticks: Sequence[int], dec0, dec1) -> list[dict]`：对多个区间宽度扫描 in-range 比例，返回 `[{"width_ticks","tick_lower","tick_upper","fraction","excursion_count"}]`。**这是回答「区间该多宽」的实证工具**，宽区间 in-range 高但单位流动性费率低，窄区间反之。
   - `main()`：`--db`（只读）`--tick-lower --tick-upper --dec0 --dec1 --out`。不写活库、不联网。
2. `tests/test_lp_rh_in_range_v1_readonly.py`（≤250 行，≥16 测试）
   - **精度归一**：`tick_from_price(Decimal("2490.58"), dec0=18, dec1=6)` 应落在 −198200 ~ −198100（主脑实测 tick=−198160）；若实现漏了精度缩放会得到完全不同的值，测试必须失败。
   - 全部样本在区间内 → `fraction == 1`，`excursions` 为空。
   - 全部在区间外 → `fraction == 0`，1 个 excursion。
   - 一半在内一半在外 → `fraction == Decimal("0.5")`。
   - **跌破下界与升破上界分别标 `BELOW` / `ABOVE`**，各一个测试。
   - 多段进出 → `excursions` 数量正确，每段 `duration_secs` 正确。
   - `reference_mid=None` 的样本**跳过计数**，不计入 out-of-range：构造 10 个样本其中 3 个 None、7 个在区间内 → `fraction == 1`（分母是 7 不是 10），`skipped == 3`。**这条是关键：缺数据不得被当成出区间。**
   - `effective_fee_ev`：`full=Decimal("100")`、`fraction=Decimal("0.5")`、`multiplier=Decimal("4")` → 200；任一为 `None` → 返回 `None`（断言不是 0）。
   - `range_scan`：宽度递增时 `fraction` **单调不减**（更宽的区间不可能更少时间在内）。
   - **真实数据回归**：从活库读最近 500 个样本，用主脑实测的当前 tick 构造 ±100 / ±500 / ±2000 tick 三个区间，断言 `fraction` 单调不减且 ±2000 的 fraction > ±100 的。

## 不许动
不改任何现有脚本/测试；不写活库（采集器正在写，只读打开）；不联网。金额与比率用 `Decimal`。不要用 TaskCreate/TaskUpdate。单次 Write ≤120 行，写完 `ast.parse` 自检。

## 验收
`pytest tests/test_lp_rh_in_range_v1_readonly.py -q` 全绿且 ≥16；全量 0 failed / 14 skipped；`git diff --stat` 为空；跑完后活库行数不变。
