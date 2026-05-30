# Tier B Priority Data Fix V2

- processed_pool_count: 16
- gt_or_dex_stability_partial_count: 11
- trader_fix_success_count: 7
- exit_depth_available_count: 16
- holder_available_count: 12
- pools_with_counterfactual_support: 0

本轮只补 one-field-away / two-fields-away / HIGH 优先池。结果是：
- `0x4e962b...` 的 trader concentration 已能通过只读链上日志补齐，但 stability 仍只有 partial。
- `0x72ab38...`、`0x26e263...` 仍是 `no_swap_logs`，无法补齐 trader concentration。
- 其余已处理池多数能拿到 exit depth 与部分稳定性快照，但 `tvl_change_1h` / `15m-30m` 稳定性仍不完整。

因此没有池子达到 `SHADOW_ONLY_DATA_READY` 或 `RESEARCH_CANDIDATE`。
