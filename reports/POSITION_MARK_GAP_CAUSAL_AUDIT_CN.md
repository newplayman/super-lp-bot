# Position Mark Gap Causal Audit

- workspace: `/opt/lpbot/lp-bot-v3-origin-check`
- snapshot: `clean_remote_repaired_v2_20260528_0902`
- scope: `pool_mark_only` / `position_mark_outside_window` / `position_join_issue` in repaired_v2 selected+intended rows
- top20 definition: `NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) = 5`

## Category Summary

| Horizon | Root Cause Category | Count | Selected Count | Top20 Count | Median net_pnl_pct | P10 net_pnl_pct | Affected token pair | Affected pool_ids |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 6h | terminal_before_target | 5683 | 5683 | 1153 | 0.000000 | 0.000000 | cbBTC/USDC, cbBTC/WETH, USAD/USDT, WETH/USDC | 0x4e962bb3889bf030368f56810a9c96b83cb3e778, 0x6c561b446416e1a00e8e93e221854d6ea4171372, 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1, 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38, 0x9a993fc0eec60faaa0c391ff11b840ce16685150, 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 |
| 6h | position_join_issue | 84 | 84 | 0 | 0.000000 | 0.000000 | cbBTC/WETH | 0x6c561b446416e1a00e8e93e221854d6ea4171372, 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 |
| 24h | terminal_before_target | 14047 | 14047 | 2826 | 0.000000 | 0.000000 | cbBTC/USDC, cbBTC/WETH, USAD/USDT, WETH/USDC, 其他 | 0x4e962bb3889bf030368f56810a9c96b83cb3e778, 0x6c561b446416e1a00e8e93e221854d6ea4171372, 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1, 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38, 0x9a993fc0eec60faaa0c391ff11b840ce16685150, 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59, 0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 |
| 24h | position_join_issue | 84 | 84 | 0 | 0.000000 | 0.000000 | cbBTC/WETH | 0x6c561b446416e1a00e8e93e221854d6ea4171372, 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 |

## 50-row Sample

| decision_trace_id | position_id | horizon | target_time | nearest_before_mark_time | nearest_after_mark_time | position status at target | closed_at | shadow_exit_decision | shadow_exit_action | root cause category |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shadow-trace-1492834cddc097d690758a62 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:12:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-8cf95c36830c39a42e653296 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:14:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-9770ac3b610b5216108215cb | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:13:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-bf30a26f5604fc5a1247f9ab | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:16:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-c1d3db75d254bf446d988bba | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:17:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-fee43e0a58b3c7f3552c249d | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 10:15:43 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-05a493117207b3ea38cba270 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:24:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-070486ccf6250a6b3cc73aa2 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:34:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-0e44685f183076e5e5505995 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:42:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-11a054e66a8371b3c6a23f14 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:43:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-15070d121ecf99b50e40cd8c | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:08:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-1d961317839e0927288d7112 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:02:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-2342f9e7e528e9734a388c92 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 08:59:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-2d68dc5727cd6acb7839a760 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:06:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-2effcb868cb242734abc1ec9 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:17:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-333a3c25bbacd10f6fca8606 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:39:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-3538916805fe5419624a3f02 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:35:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-3a2eee85f8482a9b2f583d12 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:15:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-3e84e35b4bde173e779a73e3 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:32:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-3fd09f23e5431207c55aeead | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:41:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-46f414fe689fd5dfb0f69e52 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:01:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-479231e4d49d20e9f75346fa | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:44:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-4a67ecd3c8911c2ac17ab2ad | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:04:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-55191613a6fe7424fe1711b9 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:23:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-56876f0460e16fb81591f0eb | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:26:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-5fe21ec47c739f5bbcea1d4a | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:19:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-601f571cacf4562c3eb16ef8 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:40:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-610a865d90a26690673eb047 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:28:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-67efa10ee430fbc1497e404e | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:33:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-6858a000025e2afa157f8888 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 08:58:41 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-68a609a51ffdd4bdd144208a | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:03:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-6bc036c8e5090e64e0835733 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:20:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-74c70f00496d4f20238c5920 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:00:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-8270fcfa80aa7e4c78c6abd3 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:36:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-850ddef167a42b51ade77b69 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:05:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-86ffe1069f0a440e88826340 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:29:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-8e73f49c2018f7be4015063d | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:30:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-9034b6f7f7de3481fec1f9a0 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:18:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-9ff8ef94d0e9a62dfc635163 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:25:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-ac935604b3732bc0b5632667 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:13:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-ad6f2dd3bf92f5f037d21386 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:14:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-b6d237f002a3dbc56b78868c | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:09:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-bdb40a83c8bf16e9d118bec6 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:16:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-beaae61288357c62cc61a59b | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:38:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-c0b539a78c0f1b246060b788 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:12:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-cbb3a0d7168c94012eed8150 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:21:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-deed32ae939ef1bb687d85cd | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:37:40 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-e07fd1b0a7293a9cc8fab349 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:10:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-e764c29450698c55a8564cd6 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:07:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |
| shadow-trace-edd4e16d292209c69276b7a4 | shadow-pos-06eb7de3f0c56598add9777c | 24h | 2026-05-26 09:22:39 | 2026-05-25 18:02:10 |  | closed_before_target | 2026-05-25 18:02:10 | t | t | terminal_before_target |

## Judgment

- `future_mark_after_target_outside_window` 不是主类；当前 repaired_v2 失败样本的核心不是“future mark 太远”，而是 same-position future mark 根本不存在。
- `position_mark_missing = 0` 仍成立：大多数样本已有同一 position 的 pre-target mark。
- 当前主类已经进一步收敛为 `terminal_before_target`，不是 `active_at_target_no_future_mark`。
- 这说明主问题更接近“terminal outcome 语义未纳入 strict proof”，而不是“当前 active 持仓 mark writer 没跟上”。
