# M0 integration smoke — SOL evidence index

原 `PENDING_SOL_SMOKE` 承载位已由验收官真实输出替换。WP-10 已完成；本文件仅保留兼容索引，避免旧链接失效。

## Tracked evidence

- 完整验收：`SOL_ACCEPTANCE_20260808.md`
- 机器可读摘要：`evidence_20260808/acceptance_summary.json`
- Solana tick-0 heartbeat：`evidence_20260808/solana_runner_heartbeat_tick0.json`
- Solana final state：`evidence_20260808/solana_runner_final_state.json`

## Boundary

- live scanner：`screened=736 top=1 resolved=1 scored=1 accepted=0`；live allocation 为空且 deployed=0。
- Base WETH-USDC 与 Solana SPYx-USDC 的非空 allocation 均明确为 `fixture_only_not_live_vetted`，只用于集成接线验证。
- Solana runner 已完成真实 Orca account-state 1-tick，并进入 23 字段与 SQLite gate 路径；`n_swaps=0`、fees=0，不冒充 swap/fee evidence。
- 实现后最终测试：`2660 passed, 14 skipped in 37.51s`；collect：`2674 tests collected in 1.06s`。
- 14d shadow 未启动，§12.0 gate=`FAIL`，M1 未授权。
