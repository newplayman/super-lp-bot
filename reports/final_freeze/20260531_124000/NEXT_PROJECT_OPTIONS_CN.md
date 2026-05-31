# 下一阶段选择

- primary: `STOP_LP_RESEARCH_NOW`
- secondary: `NEW_DATA_PIPELINE_FIRST`

- `STOP_LP_RESEARCH_NOW`: P0/P1/P2 都没有 practical candidate
- `NEW_DATA_PIPELINE_FIRST`: 先补 fee/depth/holder/trader/entry-safe 高频数据
- `NEW_STRATEGY_HYPOTHESIS_DESIGN_REPEAT`: 完全重开题，避开已有失败路径
- `NON_LP_STRATEGY_RESEARCH`: 转向非 LP 方向，例如纯扫描/异常检测
- `PRODUCTION_INFRA_CLEANUP_ONLY`: 不继续研究，只做工程清理
