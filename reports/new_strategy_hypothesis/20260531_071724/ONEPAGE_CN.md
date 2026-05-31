# NEW_STRATEGY_HYPOTHESIS_DESIGN_V1

## 结论

已冻结失败线，并按“最快拿到第一版证据”的排序目标建立新假设目录。

## 固定排序

1. P0: Risk-Aware Short-Hold LP
2. P1: Pool Regime Classifier
3. P2: Fee-Velocity / Exit-Depth Spread Capture

## 关键判断

- long fixed-horizon 持有路径已冻结
- position lifecycle / intent lifecycle 继续作为旧主线的价值很低
- Tier B / Tier C 当前 batch 不进入主线
- 下一阶段只读研究优先验证短持有 + 风险优先退出是否压低尾部损失

## 状态

- `failed_lines_frozen = yes`
- `new_hypothesis_count = 7`
- `can_run_p0_readonly_now = yes`
- `tiny_canary_allowed = no`

## 下一步

进入 `RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1`
