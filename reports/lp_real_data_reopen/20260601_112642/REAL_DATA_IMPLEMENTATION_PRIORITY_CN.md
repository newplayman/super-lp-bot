# Real Data Implementation Priority

1. `LP_PRECISE_QUOTE_PIPELINE_V1`
2. `LP_V3_TICK_LIQUIDITY_PIPELINE_V1`
3. `LP_REAL_FEE_ACCRUAL_PIPELINE_V1`
4. `LP_REAL_COST_MODEL_PIPELINE_V1`
5. rerun virtual economics with real data

原因：当前最可行、最 read-only、安全且能直接改善 economics realism 的是 precise quote。
