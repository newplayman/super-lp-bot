# 真实成本模型设计

- can estimate now: gas baseline、Quoter gasEstimate、quote slippage、route spread。
- requires probe: actual add/remove receipts、真实钱包结算成本。
- fixed cost: gas and tx overhead。
- proportional cost: slippage、route spread、balancing loss。
- recommended next script: `LP_REAL_COST_MODEL_PIPELINE_V1`
