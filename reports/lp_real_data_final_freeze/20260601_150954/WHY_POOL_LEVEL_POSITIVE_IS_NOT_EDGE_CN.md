# 为什么 Pool-Level Positive 不等于 Edge

- pool-level fee 口径描述的是池子整体手续费流，不是某个 LP NFT position 的实际 fee accrual。
- simulated fee 只是模型替代项，它可以做方向性诊断，但不能替代真实 position fee。
- actual position fee 需要至少这些要素同时存在：
  - `tokenId`
  - `tickLower / tickUpper`
  - `liquidity`
  - `feeGrowthInside`
  - `tokensOwed`
- 当前 real-data reopen 线结论是：
  - `token_id_recovered_count = 0`
  - `usable_actual_position_count = 0`
  - `actual_fee_positive_proxy_count = 0`
  - `pool_level_fee_positive_proxy_count = 6`
- 因为没有 tokenId，就不能把池级 fee 正信号映射到某个真实 LP 仓位。
- 所以这 6 个 positive proxy 只能作为 watch / diagnostic，不构成 edge，也不能支持 probe、canary 或 live。

