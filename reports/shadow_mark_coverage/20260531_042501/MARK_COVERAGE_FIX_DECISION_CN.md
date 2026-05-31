# MARK_COVERAGE_FIX_DECISION_CN

- terminal_misclassified_as_no_future_mark_count: 108
- active_no_future_mark_count: 0
- pool_mark_only_counterfactual_count: 0
- mark_worker_fix_needed: no
- materializer_classification_fix_needed: yes
- recommended_next_stage: MATERIALIZER_INVALID_REASON_CLASSIFICATION_FIX

## 判断
- 是否真的需要修 mark worker: 否
- 是否只是 invalid_reason 分类错位: 是
- active_at_target no future mark 的数量是否足以构成 mark coverage bug: 否
- terminal_before_target 仍应从 clean proof 中剔除，不应并入 clean proof。
- pool_mark_only 只能保留为 counterfactual，不能并入 clean proof。
- 是否继续 fixed-horizon 有意义: 有，但前提是先修 mark coverage / invalid_reason 语义
