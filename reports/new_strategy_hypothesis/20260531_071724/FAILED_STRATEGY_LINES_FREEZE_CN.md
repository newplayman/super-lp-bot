# 已失败策略线冻结

本轮设计只基于既有只读证据，不重新开启已经被证明不适合继续投入的主线。

## 冻结结论

| 线索 | 状态 | 冻结原因 |
| --- | --- | --- |
| current_full_strategy | FAIL | position-level tail 不过线，terminal / lifecycle tail risk 不可接受，decision_trace 旧口径已失效 |
| fixed_horizon_position_lifecycle | STOP / PAUSE | recent OOS 仍不足，12h/24h 证据链不稳定，无法继续按旧结构推进 |
| intent_lifecycle_signal_chasing | PAUSE / STOP | 信号不足且曾出现重复计数与 DQ 偏差，不能继续作为主线 |
| tier_b_batch | PAUSE | 当前 batch 无可继续推进候选，样本与门槛都不支持继续扩展 |
| tier_c_shadow_research | BATCH_REJECTED | holder / trader concentration 极端，未形成可继续 OOS 的研究候选池 |

## 冻结原则

1. 旧的长持有 fixed-horizon 主线不再作为第一优先。
2. intent lifecycle 相关材料只保留为研究证据，不再作为主结论。
3. Tier B / Tier C 当前 batch 结论冻结，等新 discovery 或市场变化再重开。
4. 不把任何冻结线重新包装成 canary 候选。
5. `tiny_canary_allowed = no`。
