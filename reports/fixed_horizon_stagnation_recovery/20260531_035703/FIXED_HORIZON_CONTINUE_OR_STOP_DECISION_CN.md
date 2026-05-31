# FIXED_HORIZON_CONTINUE_OR_STOP_DECISION_CN

- completed_growth_status: GROWTH_STALLED
- new_position_generation_status: LOW_NEW_POSITION_FLOW
- position_reuse_status: REUSE_DOMINANT
- future_mark_coverage_status: LOW_FUTURE_MARK_COVERAGE
- tail_risk_status: 12H_FAIL_24H_INSUFFICIENT
- selected_decision: SHADOW_MARK_COVERAGE_FIX

## 选择理由
- 当前 completed 样本停滞不是单一原因：新增 position 偏少、reuse 占主导、24h future mark 覆盖接近空白同时存在 terminal/no_future_mark 语义错位。
- 12h canonical tail 仍为明显负值，24h 仍不足样本，单靠继续等待不能证明 edge。
- 由于 canonical strict proof 当前首先卡在 future mark / terminal 映射链路，优先动作落在 mark coverage 口径修复，而不是继续被动等样本。
