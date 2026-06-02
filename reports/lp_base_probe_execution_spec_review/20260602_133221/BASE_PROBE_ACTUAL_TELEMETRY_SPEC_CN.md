# Base 10U Probe Actual Telemetry Schema (设计)

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: F
- run_id: `20260602_133221`
- wrote_to_production_tables: **false**（本轮仅 design）

## 5 个 schema proposals

| schema | 名称 | 用途 |
|---|---|---|
| Entry | `lp_probe_execution_ledger_v1` | 一次 probe 执行的入口记录（含 tokenId） |
| Hold | `lp_probe_hold_monitor_v1` | 每分钟 hold 状态（tick / fee / mtm） |
| Fee trace | `lp_probe_position_fee_trace_v1` | actual_position_fee lineage（feeds upstream real_fee_accrual） |
| Exit | `lp_probe_exit_trace_v1` | decreaseLiquidity + collect 退出记录 |
| PnL | `lp_probe_actual_pnl_v1` | 真实 PnL（fees + IL + gas + slippage） |

## Entry（lp_probe_execution_ledger_v1）

| 字段 | 类型 | 含义 |
|---|---|---|
| run_id | string | 本 run 目录的 run_id |
| session_id | string | 每次执行尝试唯一（re-approval = 新 session_id） |
| wallet | address | 0x + 40 hex（公开地址，非敏感） |
| chain / chain_id | string / uint64 | 'base' / 8453 |
| pool | address | 0x72ab388e... |
| token0 / token1 | address | WETH / USDC |
| fee_tier | uint24 | 100 |
| tick_lower / tick_upper | int24 | -200643 / -200243 |
| current_tick_at_entry | int24 | Step 0 重读 |
| current_sqrt_price_x96_at_entry | uint256 | Step 0 重读 |
| amount0_desired_wei | uint256 | 0 |
| amount1_desired_raw | uint256 | 10_000_000 (10U) 或 20_000_000 (20U) |
| amount0_actual_wei | uint256 | mint 后从 balance delta 算 |
| amount1_actual_raw | uint256 | 同上 |
| amount0_min_wei | uint256 | 0 |
| amount1_min_raw | uint256 | 9_949_999 / 19_899_999 |
| approve_tx_hash | bytes32 | 或 null（如果跳了 approve） |
| approve_block_number | uint64 | |
| approve_gas_used | uint64 | |
| mint_tx_hash | bytes32 | |
| mint_block_number | uint64 | |
| mint_gas_used | uint64 | |
| mint_effective_gas_price_wei | uint256 | |
| token_id | uint256 | ERC721 tokenId from NPM Transfer event |
| liquidity_at_entry | uint128 | |
| entry_block / entry_unix_seconds / entry_timestamp_iso | | |
| entry_gas_total_wei | uint256 | approve + mint |
| entry_gas_total_usd | decimal | |
| fee_growth_inside_0_last_x128_at_entry | uint256 | |
| fee_growth_inside_1_last_x128_at_entry | uint256 | |
| tokens_owed_0_at_entry | uint256 | |
| tokens_owed_1_at_entry | uint256 | |
| approved_phrase | string | 用户键入的完整审批短语（审计用） |
| approver_intent | string | 'notional=10 hold=15m' |
| fabrication_blocked | bool | true |
| wallet_or_tx_touched | bool | entry 时刻为 false；Step 1+ 后变 true |

## Hold（lp_probe_hold_monitor_v1）

每 60s 一次：

| 字段 | 类型 | 含义 |
|---|---|---|
| session_id | string | FK |
| minute_index | uint32 | 1-based |
| block_number | uint64 | |
| tick | int24 | sign-extended |
| sqrt_price_x96 | uint256 | |
| liquidity | uint128 | |
| fee_growth_inside_0_x128 | uint256 | |
| fee_growth_inside_1_x128 | uint256 | |
| tokens_owed_0 | uint256 | |
| tokens_owed_1 | uint256 | |
| usdc_quote_out_1usdc_in | uint256 | 1 USDC → ? WETH |
| weth_quote_out_0_001weth_in | uint256 | 0.001 WETH → ? USDC |
| mark_to_market_usd | decimal | tokensOwed 在当前 spot 的 USD 价值 |
| mtm_pnl_usd_vs_entry | decimal | |
| exit_quote_unavailable | bool | true → stop_exit_quote_unavailable |
| stop_condition_status | string | none / trigger:<id> / ok |

## Fee trace（lp_probe_position_fee_trace_v1）

每 5 min 一次；目的：**给 upstream real_fee_accrual 喂 actual_position_fee 数据**（lineage_missing 的解锁关键）：

| 字段 | 类型 | 含义 |
|---|---|---|
| session_id | string | FK |
| block_number | uint64 | |
| fee_growth_inside_0_x128 | uint256 | |
| fee_growth_inside_1_x128 | uint256 | |
| delta_fee_0_wei | uint256 | 相对上次 sample 的增量 |
| delta_fee_1_raw | uint256 | |
| delta_fee_0_usd | decimal | 在当前 spot 的 USD |
| delta_fee_1_usd | decimal | USDC 1:1 |
| pool_level_fee_proxy_for_comparison | decimal | 同一 block 来自 upstream real_fee_accrual 的 proxy（如果有） |

## Exit（lp_probe_exit_trace_v1）

| 字段 | 类型 |
|---|---|
| session_id | string |
| decrease_tx_hash / decrease_block_number / decrease_gas_used | |
| liquidity_removed | uint128（应 == entry） |
| collect_tx_hash / collect_block_number / collect_gas_used | |
| collected_token0_wei / collected_token1_raw | uint256 |
| exit_block / exit_unix_seconds / exit_timestamp_iso | |
| exit_gas_total_wei | uint256 |
| exit_gas_total_usd | decimal |

## Post-exit（lp_probe_post_exit_v1）

| 字段 | 类型 |
|---|---|
| session_id | string |
| usdc_revoke_tx_hash / usdc_revoke_block_number / usdc_revoke_gas_used | |
| usdc_allowance_post_revoke | uint256（应为 0） |
| weth_revoke_tx_hash / weth_revoke_block_number / weth_revoke_gas_used | (或 null) |
| weth_allowance_post_revoke | uint256（应为 0） |
| final_eth_native_wei / final_weth_wei / final_usdc_raw | uint256 |

## Actual PnL（lp_probe_actual_pnl_v1）

| 字段 | 类型 | 含义 |
|---|---|---|
| session_id | string | |
| entry_principal_usd | decimal | == notional |
| fees_collected_token0_wei | uint256 | |
| fees_collected_token1_raw | uint256 | |
| fees_collected_usd_total | decimal | fees_0 at exit spot + fees_1 |
| exit_principal_token0_wei | uint256 | from collect |
| exit_principal_token1_raw | uint256 | from collect |
| exit_principal_usd | decimal | at exit spot |
| impermanent_loss_usd_proxy | decimal | vs hold-and-sell baseline |
| lvr_proxy_usd | decimal | 0 for in-range 0.01% tier（占位） |
| slippage_cost_usd | decimal | entry + exit slippage from QuoterV2 vs actual |
| gas_cost_total_usd | decimal | entry + exit + revoke |
| net_pnl_usd | decimal | exit + fees - entry - gas - slippage - il |
| net_pnl_usd_il_excluded | decimal | 不含 IL（隔离 LP mechanics） |
| hold_duration_seconds | uint64 | |
| hold_duration_minutes | decimal | |
| success_status | string | success / halt_<id> / exit_immediate_<id> |
| halt_or_exit_reason_id | string | FK to Phase E stop_conditions.id |

## 本地落库（本 run 目录；**不**写 production 表）

```
entry.json
hold_<minute>.json
fee_trace_<sample>.json
exit.json
post_exit.json
actual_pnl.json
actual_pnl.csv
session_summary.md
```

**写 production 表必须由独立的、freeze 解冻后的、被批准 pipeline 做**。本轮不动 production 表。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
wrote_to_production_tables = false
```
