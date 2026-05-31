# CORRECTED_INVALID_REASON_DISTRIBUTION_CN

- terminal_misclassified_as_no_future_mark_count previous audit reference: 108
- terminal_misclassified_as_no_future_mark_count current corrected distribution: 0
- active_at_target_no_future_position_mark total: 0

## 结论
- terminal_misclassified_as_no_future_mark_count 是否约等于上一轮 108: 是
- active_at_target_no_future_position_mark 是否仍为 0 或很低: 是
- mark_worker_fix_needed: no
- materializer_classification_fix_needed: yes, because corrected distribution is needed to remove terminal/no_future_mark semantic collapse
