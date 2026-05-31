# 新策略优先级排序

排序目标已经固定为“最快拿到第一版证据”。

## 排序结果
| Rank | Hypothesis | Status | Reason |
| --- | --- | --- | --- |
| 1 | P0 | Risk-Aware Short-Hold LP | ACTIVE | 最快拿到第一版只读证据，且直接瞄准尾部损失 |
| 2 | P1 | Pool Regime Classifier | ACTIVE | 为 P0 提供前置筛选与分层，复用现有池级数据 |
| 3 | P2 | Fee-Velocity / Exit-Depth Spread Capture | ACTIVE | 保留备选收益路径，但不抢 P0 的尾部优先级 |
| 4 | H5 | Event-Risk Avoidance LP | DEFERRED | 更像过滤器，单独验证价值有限 |
| 5 | H4 | Range-Stability LP | DEFERRED | 与失败的长持有路径重叠度高，需要后验再谈 |
| 6 | H6 | Micro-Liquidity Exit-First LP | REJECT | 与 P2 高度重叠，且缺少独立可验证增量 |
| 7 | H7 | Negative Tail Quarantine First | REJECT | 这是政策层，不是独立 alpha 假设 |
