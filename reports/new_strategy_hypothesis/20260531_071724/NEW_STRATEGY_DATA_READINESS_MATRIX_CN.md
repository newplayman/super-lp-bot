# 新策略数据就绪矩阵

下面的矩阵按“是否足以支持下一阶段只读研究”来判定，而不是按是否足以直接交易来判定。

## 读数口径

- `READY`: 当前链路可直接支持下一阶段只读验证
- `PARTIAL`: 现有链路能覆盖一部分，但需要补充或约束
- `GAP`: 当前缺失过多，不能作为主证据
- `N/A`: 该项对该假设不是主输入

## 数据项矩阵
| Data item | P0 | P1 | P2 | Current status | Notes |
| --- | --- | --- | --- | --- | --- |
| price_move_5m / 15m / 30m | HIGH | HIGH | PARTIAL | P0 直接需要短窗尾部判断；P1 用于 regime 切换；P2 作为噪声过滤 |
| volume_change_15m / 30m / 1h | HIGH | HIGH | PARTIAL | 帮助识别流动性衰减与短持有尾部风险 |
| tvl_change_1h | HIGH | HIGH | PARTIAL | P0 / P1 都要；P2 需要 exit depth 上下文 |
| fee velocity | MEDIUM | HIGH | PARTIAL | P2 核心输入；P0 只作补充 |
| exit depth 10 / 20 / 50 USD | HIGH | HIGH | PARTIAL | P0 / P2 都需要，决定是否应该退出或规避 |
| top10_holder_pct | HIGH | HIGH | PARTIAL | P1 先分层；极端集中直接挡掉后续验证 |
| trader concentration | HIGH | HIGH | PARTIAL | P1 / P0 风险过滤器，避免把单边刷量误判为信号 |
| buyer / seller imbalance | MEDIUM | HIGH | PARTIAL | 辅助识别短窗市场结构，不应单独作为 alpha |
| future pool mark | HIGH | HIGH | PARTIAL | P0 必需的对照项之一，避免把终止样本误当可继续样本 |
| position mark | HIGH | HIGH | PARTIAL | 对照历史实现，但不再作为唯一主证明单位 |
| pool state snapshot | HIGH | HIGH | PARTIAL | P1 / P0 的共同上下文 |
| LP fee proxy | MEDIUM | HIGH | PARTIAL | P2 主要输入，帮助判断 spread capture 是否可能 |
| gas / slippage estimate | HIGH | HIGH | PARTIAL | P0 退出成本必须显式考虑 |
| terminal / exit event | HIGH | HIGH | PARTIAL | 用于区分 hold-to-horizon、risk-aware exit、quarantine |
| risk event labels | HIGH | HIGH | PARTIAL | 用于构造 counterfactual 与尾部解释 |
