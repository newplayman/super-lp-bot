# Metadata 缺口策略

- 不猜 token symbol，无法解析时保留 address
- token address 无法解析 -> 用 address 替代 symbol
- fee tier unknown -> unknown
- pool_type unknown -> 不进入 precise quote
- BSC token decimals 使用 ERC20 decimals 只读查询
- token symbol 可读则记录，不可读则 unknown
- metadata_confidence in [high, medium, low]
- 所有 unknown 不自动补齐
