# RH-02d：采集覆盖率审计与缺口归因（离线可测）

## 背景（源自主脑刚做的诊断）

`reports/rh_pivot/20260907T124500Z/COLLECTOR_PERIOD_DRIFT_FIX.md`：Stage A 覆盖率实测 89.9%（1726/1919），根因是每轮固定多出 1.4s 的周期漂移，已修复。但 PRD §21.1 要求「**数据覆盖率分母必须是计划应观测的窗口**，不能删掉坏窗口后报 100%」，且「关键状态未知时新增模拟仓位次数=0」。当前缺少一个能持续审计覆盖率、并把缺口**归因到具体原因**的模块——只知道丢了 194 个样本，不知道每个缺失窗口是因为什么。

## 只新建两个文件

1. `scripts/lp_rh_coverage_audit_v1_readonly.py`（≤280 行）
   - `analyze_gaps(sample_times: Sequence[str], *, expected_interval_secs: int, tolerance_ratio: Decimal = Decimal("1.5")) -> dict`：
     - 逐对计算间隔；`interval > expected * tolerance_ratio` 记为一个 gap。
     - 返回 `{"total_samples", "span_secs", "expected_samples", "coverage_ratio", "gaps": [{"start","end","duration_secs","missed_samples"}], "drift_secs_per_round", "systematic_drift": bool}`。
     - **`drift_secs_per_round`** = 中位间隔 − 期望间隔。`> 0.5s` 时 `systematic_drift=True`——这正是本次 89.9% 的成因，须能自动识别，不能只报总缺口。
   - `attribute_gaps(gaps, health_rows, *, window_secs=60) -> list[dict]`：把每个 gap 与 `rh_rpc_health` 行按时间对齐，归因到 `RPC_DEGRADED` / `RPC_EXIT_ONLY` / `PROCESS_RESTART` / `SYSTEMATIC_DRIFT` / `UNEXPLAINED`。**`UNEXPLAINED` 必须保留，不得强行归类**（PRD §8.4：不得把未知填成已知）。
   - `coverage_verdict(analysis, *, min_ratio=Decimal("0.99")) -> dict`：返回 `{"passed", "ratio", "shortfall_samples", "blockers", "remediation"}`。`remediation` 只能取 `EXTEND_OBSERVATION` / `FIX_DRIFT` / `INVESTIGATE_UNEXPLAINED`——**绝不能是「放宽门槛」**。
   - `evaluation_window_coverage(sample_times, *, window_start, window_end, expected_interval_secs) -> Decimal`：PRD §21.1「被选中用于收益评估的窗口」覆盖率。**分母是该窗口的计划样本数，不是该窗口实际样本数。**
   - `main()`：`--db`（只读打开活库）`--interval-secs --out`。不写活库、不联网。
2. `tests/test_lp_rh_coverage_audit_v1_readonly.py`（≤250 行，≥16 测试）
   - **分母定义**（最关键）：给 10 个样本、跨度 1 小时、间隔 15s → `expected_samples=240`、`coverage_ratio≈0.042`。**断言分母是 240 不是 10。**
   - **系统性漂移识别**：构造中位间隔 16.5s、无任何大 gap 的序列 → `systematic_drift is True`、`drift_secs_per_round≈1.5`，且 `gaps` 为空。**这是本次真实故障的形态：总覆盖率低但一个断档都没有。**
   - 构造 3 个真实 gap（每个 5 分钟）→ `gaps` 长度 3，`missed_samples` 各约 20。
   - `attribute_gaps`：gap 时间窗内有 `state='DEGRADED'` 的健康行 → 归因 `RPC_DEGRADED`；无任何对应行 → **`UNEXPLAINED`**，断言不被强行归入其它类。
   - `coverage_verdict`：ratio=0.899 → `passed False`、`remediation` 含 `FIX_DRIFT`；ratio=0.995 → `passed True`。
   - **`remediation` 永不含放宽门槛**：参数化遍历多种 ratio，断言返回值集合 ⊆ 三个允许值。
   - `evaluation_window_coverage`：窗口内实际 100 个样本、计划 240 个 → 返回 `≈0.417`；**若实现把分母写成 100 会得 1.0，测试必须失败**。
   - 真实数据回归：用 `COLLECTOR_PERIOD_DRIFT_FIX.md` 记录的数字（1726 样本 / 1919 计划 / 中位间隔 16.4s）构造输入，断言 `coverage_ratio≈0.899`、`systematic_drift is True`。

## 不许动
不改任何现有脚本/测试；不写活库（`reports/lp_rh/scanner.db` 只读打开，采集器正在写）；不联网。金额与比率用 `Decimal`。不要用 TaskCreate/TaskUpdate。单次 Write ≤120 行，写完 `ast.parse` 自检。

## 验收
`pytest tests/test_lp_rh_coverage_audit_v1_readonly.py -q` 全绿且 ≥16；全量 0 failed / 14 skipped；`git diff --stat` 为空；跑完后活库行数不变。
