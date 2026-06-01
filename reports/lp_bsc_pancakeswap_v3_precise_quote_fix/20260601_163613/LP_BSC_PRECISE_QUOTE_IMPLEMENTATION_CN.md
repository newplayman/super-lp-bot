# LP BSC PancakeSwap V3 精确 quote 实施

- 脚本: `scripts/lp_bsc_pancakeswap_v3_precise_quote_v1_readonly.py`
- 方法: `quoteExactInputSingle((tokenIn,tokenOut,fee,amountIn,sqrtPriceLimitX96))` 静态调用 quoterV2
- fallback: 仅在静态调用失败时进行 pool_math_fallback（用于可用性对照）
- notionals: `20/100/500/1000/2000`
- 双向方向: `token0_to_token1`, `token1_to_token0`
- 禁止: swap/mint/burn/send_tx/wallet/signature。
