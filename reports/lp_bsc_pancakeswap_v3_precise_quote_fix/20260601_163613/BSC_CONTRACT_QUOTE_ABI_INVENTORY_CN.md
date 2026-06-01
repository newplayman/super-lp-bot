# BSC PancakeSwap V3 Quote ABI 资产清单

- `quoteExactInputSingle((address,address,uint24,uint256,uint160))` 采用 quoterV2 eth_call 静态调用。
- 禁止 router/swap/mint/burn/collect 等执行路径。
- 无 wallet 私钥/签名依赖。
