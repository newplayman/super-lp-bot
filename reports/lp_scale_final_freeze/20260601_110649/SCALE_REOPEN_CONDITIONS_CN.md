# LP Scale Economics 重启条件

只有以下条件成立，才值得重开这条新研究线：

1. 引入真实 LP fee accrual 数据
   - position-level fee growth
   - realized / unrealized fee
   - pool fee distribution

2. 引入更真实的 quote / route
   - route simulation
   - v3 tick / liquidity
   - aggregator dry quote
   - 全程 no signing

3. 引入更高置信度数据
   - holder / trader concentration
   - clean entry-safe snapshots
   - real gas / fixed cost measurements
   - exact pool type / exact LP range

4. 新策略假设必须重起炉灶
   - 不再从同一批池和同一套 proxy 出发
   - 必须先出现 `positive proxy` 或 `near break-even`
   - 然后才讨论 probe preflight

不满足上述条件时：

- 不建议继续当前数据和模型
- 不建议继续补参数
- 不建议继续 probe / canary / live
