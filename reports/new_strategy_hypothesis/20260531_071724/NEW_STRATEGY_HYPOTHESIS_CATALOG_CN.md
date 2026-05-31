# 新策略假设目录

本轮采用“最快拿到第一版证据”的排序目标，固定优先级如下：

1. P0: Risk-Aware Short-Hold LP
2. P1: Pool Regime Classifier
3. P2: Fee-Velocity / Exit-Depth Spread Capture

排序原则：

- 优先最快拿到第一版只读证据。
- 优先复用现有数据链路。
- 优先解释并规避已失败路径。
- 优先验证短持有 + 风险优先退出是否压低负尾。
- 不追求 median 好看，先看 p10 / p5 / p1 是否改善。
- 全部结论仍为 research-only，不允许 canary。

## 假设清单
| Hypothesis | Priority | Status | Primary proof unit | Why it is / is not selected |
| --- | --- | --- | --- | --- |
| P0 | Risk-Aware Short-Hold LP | ACTIVE | pool_window / intent_window | 最快拿到第一版只读证据，验证风险优先退出是否压低尾部损失 |
| P1 | Pool Regime Classifier | ACTIVE | pool_state_window | 为 P0 提供前置筛选，按池状态而非长持有结果分层 |
| P2 | Fee-Velocity / Exit-Depth Spread Capture | ACTIVE | fee_velocity_window / exit_depth_window | 保留为备选收益路径，但优先级低于尾部风险验证 |
| H4 | Range-Stability LP | DEFERRED | pool_window | 与 P0 重叠度高，单独验证收益较弱，容易回到被证明失败的长持有叙事 |
| H5 | Event-Risk Avoidance LP | DEFERRED | risk_event_window | 更像过滤器而不是完整策略，需并入 P0 / P1 才有研究价值 |
| H6 | Micro-Liquidity Exit-First LP | REJECT | exit_depth_window | 与 P2 强重叠且当前数据链路不足以证明独立价值 |
| H7 | Negative Tail Quarantine First | REJECT | quarantine_window | 这是风控政策层，不是独立 alpha 假设，不能单独作为策略主线 |
