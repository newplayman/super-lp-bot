# 为什么不能 Canary

- edge_proven: `no`
- tiny_canary_candidate: `no`
- tiny_canary_allowed: `no`

- 没有通过任何完整 proof gate
- 没有可用 practical variant
- fee_minus_exit_cost 不能覆盖成本
- opportunity retention 太低
- false filter / missed profit 太高
- 仍有 overfit / data quality / leakage 修复历史
- tail risk 虽可被过滤，但过滤后策略不可实用
- live/canary 会把研究伪信号变成真实损失
