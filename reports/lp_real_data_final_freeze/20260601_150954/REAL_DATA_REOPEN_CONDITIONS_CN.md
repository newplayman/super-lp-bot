# Future Reopen Conditions

未来只有同时满足下列条件，real-data reopen 才值得重开：

1. 有真实 LP position `tokenId`
2. 有 actual position fee accrual
3. 有 `feeGrowthInside / tokensOwed / Collect` 事件
4. 有 precise quote + tick-liquidity + real cost
5. 至少一个池在 actual-fee 或高置信 fee 下接近 break-even
6. 有严格 probe preflight
7. 用户手动批准

补充约束：

- 没有 tokenId 的 pool-level positive 只能作为 watch
- 不能作为实盘依据
- 不能直接 probe

