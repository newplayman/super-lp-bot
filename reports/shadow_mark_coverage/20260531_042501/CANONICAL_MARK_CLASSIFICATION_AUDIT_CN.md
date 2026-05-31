# CANONICAL_MARK_CLASSIFICATION_AUDIT_CN

- `6h` total=68 completed=43 no_future_mark=26 terminal_before_target=25 horizon_not_mature=0 pool_mark_only=0 active_no_future=0 terminal_misclassified=25
- `12h` total=68 completed=42 no_future_mark=28 terminal_before_target=26 horizon_not_mature=0 pool_mark_only=0 active_no_future=0 terminal_misclassified=26
- `24h` total=68 completed=10 no_future_mark=60 terminal_before_target=57 horizon_not_mature=1 pool_mark_only=0 active_no_future=0 terminal_misclassified=57

## 结论
- `no_future_mark` 是否包含大量 terminal_before_target: 是
- `no_future_mark` 是否包含 pool_mark_only: 否
- 24h 缺口是否主要由 terminal_before_target 构成: 是
- 是否存在 active_at_target 但真的没有 future position mark: 否
- 是否是 mark worker 漏写: 当前证据不足
- 是否是 materializer invalid_reason 分类顺序有问题: 是
