# 真实 fee accrual 方案设计

- before probe: pool globals、ticks、swap logs 可 read-only 获取。
- requires actual LP NFT: `positions(tokenId)`、`tokensOwed0/1`、exact position range lineage。
- simulated from historical positions: pool-level fee velocity proxy 与历史区间近似。
- cannot know without owning position: exact unclaimed fees、exact feeGrowthInside deltas。
- recommended next script: `LP_REAL_FEE_ACCRUAL_PIPELINE_V1`
