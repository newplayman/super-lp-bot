# Tier B Trader Concentration Fix V3

- targeted_pool_count: 16
- trader_fix_success_count: 7
- repeated_no_swap_logs_count: 5
- unsupported_pool_id_count: 4

重点结果：
- `0x4e962bb3889bf030368f56810a9c96b83cb3e778` 保持成功的链上 trader attribution。
- `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` 与 `0x26e263efdc91f0d3279e2ec2bd58a7ca5c2fce62` 连续两轮 `no_swap_logs`。
- 多个长 `pool_id` 仍然是 `unsupported_pool_id`，没有继续升格的价值。
