# RH-04d：持有期扫描与换腿成本口径复核（离线可测）

## 背景（本包直接源自主脑刚跑出的第一条经济结论）

`reports/rh_pivot/20260907T124500Z/RH-04b/FIRST_CLOSED_LOOP.md` 实测：目标池 WETH/USDG（fee=100，TVL $31.9M）、仓位 $50、持有 168h 时，**进出各 $4.70 换腿成本合计占仓位 18.8%**，即使 fee APR 给到 900% 仍 NetCover 0.909 不过闸；实测真实费率年化 27.34% 对应 NetCover ≈ 0.028。

B1 §9.5 的旧结论：**固定成本 ≈ 2×池费档、几乎不随仓位变化；持有期才是主导杠杆**。本包把这条量化。

## 只新建两个文件

1. `scripts/lp_rh_horizon_sweep_v1_readonly.py`（≤280 行）
   - import `lp_rh_netcover_inputs_v1_readonly.assemble_rh_clmm_inputs`、`lp_netcover_engine_v1_readonly.apply_netcover_gate`、`lp_swap_cost_model_v1_readonly.clmm_token0_value_fraction`。**只调用不修改。**
   - `HORIZONS_HOURS = (24, 168, 720, 1220)`（PRD §10.1 的有限情景）。
   - `sweep_horizons(evidence, *, position_usd: Decimal, horizons=HORIZONS_HOURS) -> list[dict]`：每个持有期跑一次装配+引擎，返回 `[{"horizon_hours", "fee_ev_usd", "fixed_cost_usd", "netcover", "netcover_pass", "required_fee_apr_pct"}]`。
     - `fixed_cost_usd` = `entry_cost_usd + exit_cost_usd + gas_usd`（**不随持有期变化的部分**）。
     - `required_fee_apr_pct`：反解「使 NetCover = 1.0 所需的 fee APR」。用二分或解析解；**若 `fee_ev` 对 APR 非线性则用二分**，收敛容差 0.01%。任一输入缺失 → 该项为 `None`，**不得填 0**。
   - `fixed_cost_share(evidence, *, position_usds=(50, 500, 5000)) -> list[dict]`：验证 B1 §9.5 的「固定成本几乎不随仓位变化」。返回每个仓位的 `fixed_cost_usd` 与 `fixed_cost_pct_of_position`。**若固定成本确实近似恒定，`fixed_cost_usd` 在三个仓位上应接近；若它随仓位线性增长，说明成本模型把全额本金当换腿额——那是 PRD §11.3 明令禁止的。**
   - `conversion_cost_audit(evidence, *, position_usd, range_pcts=(1, 5, 10, 20, 50)) -> list[dict]`：**复核 $4.70 是否高估**。对不同区间宽度调 `clmm_token0_value_fraction`，看换腿份额如何变化，返回 `[{"range_pct", "token0_value_fraction", "implied_swap_notional_usd", "entry_cost_usd"}]`。区间越宽，两腿越均衡，需换腿的份额应越小。**这是诊断，不下结论。**
   - `main()`：`--evidence-json --position-usd --out`，不联网。
2. `tests/test_lp_rh_horizon_sweep_v1_readonly.py`（≤250 行，≥14 测试）
   - **核心断言**：同一 evidence 下，`fixed_cost_usd` 在四个持有期上**完全相同**（Decimal 精确相等）——固定成本不随时间变化。
   - `fee_ev_usd` 随持有期**单调递增**且近似线性（720h 的 fee_ev ≈ 168h 的 4.29 倍，容差 5%）。
   - `required_fee_apr_pct` 随持有期**单调递减**（持有越久，所需 APR 越低）。
   - 用 FIRST_CLOSED_LOOP 的真实参数回归：`position_usd=50`、`horizon=168`、`fee_apr=900` → `netcover` 落在 0.90–0.92；`fee_apr=5000` → `netcover_pass is True`。
   - `fixed_cost_share`：三个仓位的 `fixed_cost_usd` 若近似恒定则断言两两相差 <5%；**若实际随仓位线性增长，测试必须如实失败并在断言消息里写明「成本模型可能把全额本金当换腿额」**——不要为了让测试过而放宽。
   - `conversion_cost_audit`：`token0_value_fraction` 随 `range_pct` 增大而**趋近 0.5**（两腿均衡）；`range_pct=1` 与 `range_pct=50` 的 `entry_cost_usd` 应显著不同。
   - 任一必需输入缺失 → 该项 `None`，`required_fee_apr_pct` 也为 `None`，**断言不是 0**。
   - 反解自洽性：把 `required_fee_apr_pct` 回代进 `sweep_horizons`，得到的 `netcover` 应在 1.0 ± 0.01。

## 不许动
不改任何现有脚本/测试/六常量；不联网；不写活库；不碰 `lp_rh_collector_v1_readonly.py`（生产运行中）与其它 worker 正在写的文件。金额用 `Decimal`。不要用 TaskCreate/TaskUpdate。单次 Write ≤120 行，写完 `ast.parse` 自检。

## 验收
`pytest tests/test_lp_rh_horizon_sweep_v1_readonly.py -q` 全绿且 ≥14；全量 0 failed / 14 skipped；`git diff --stat` 为空。
