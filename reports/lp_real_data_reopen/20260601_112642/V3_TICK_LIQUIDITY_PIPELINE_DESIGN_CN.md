# V3 tick-liquidity 方案设计

- snapshot source: `slot0`, `liquidity`, `ticks`, `tickBitmap`, `observe`。
- capture width: current price 两侧约 `256` 个 initialized tick 为第一版基线。
- no lookahead: 只使用 entry-safe cutoff 前的窗口和调用时点快照。
- target: 更准确的 capacity / slippage / route feasibility。
- recommended next script: `LP_V3_TICK_LIQUIDITY_PIPELINE_V1`
