# INTENT_VS_POSITION_LIFECYCLE_COMPARISON_CN

- intent lifecycle 明显扩大样本数，解决了 position reuse 导致的 position-level 样本不足。
- 但它引入新的 bias：bucketed counterfactual + pool-mark exit 近似。
- 如果去重策略失守，它会退化成 decision_trace 重复计数，因此仍需强 anti-duplication gate。
- 在 research-only 口径下，值得继续研究。
