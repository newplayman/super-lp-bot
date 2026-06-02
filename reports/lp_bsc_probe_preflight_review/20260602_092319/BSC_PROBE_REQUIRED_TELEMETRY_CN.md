# 10/20U Probe 必须记录的数据字段

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- phase: E
- 范围：spec only，本轮不创建任何 production 表

## Entry（mint 时一次性）

```text
timestamp_utc
block_number
pool_address
token0 / token1 / symbols / decimals
fee_tier_raw
tick_current_at_mint
sqrtPriceX96_at_mint
tickLower / tickUpper
liquidity_amount_added
token0_amount_added (signed int256)
token1_amount_added (signed int256)
notional_usd (planned + actual)
quote_before_mint:
  amount_in, amount_out
  sqrtPriceX96_after, tick_after
  gas_estimate
  quote_method = PancakeSwap V3 QuoterV2
expected_slippage_bps
expected_gas_price_gwei
expected_gas_units
expected_gas_cost_usd
approval_tx_hash_if_any
approval_amount_set
mint_or_increaseLiquidity_tx_hash
tokenId  (来自 NFT Transfer event；这是 actual_fee 数据的核心)
initial_feeGrowthInside0_X128 / X1
initial_tokensOwed0 / 1
```

## Hold（30s 周期采样）

```text
timestamp_utc
block_number
current_tick / current_sqrtPriceX96
position_liquidity
feeGrowthInside0_X128 / X1
tokensOwed0 / 1
in_range  (current_tick in [tickLower, tickUpper])
mark_to_market_token0 / token1 / usd
exit_quote_token0_out / token1_out  (QuoterV2 read-only)
fee_velocity_5m_count / volume_usd
```

## Exit（一次性收尾）

```text
exit_decision_reason   (S1..S10 之一 或 human_manual)
exit_block_number
decreaseLiquidity_tx_hash
collect_tx_hash
final_tokensOwed0/1 (collect 前)
collected_token0_actual / collected_token1_actual
swap_back_required
swap_back_quote_token_in / out
swap_back_quote_amount_in / out
swap_back_quote_drift_vs_mint_bps
swap_back_tx_hash_if_any
post_exit_token0_balance / token1_balance
realized_pnl_usd
actual_fee_accrual_usd  (这就是本 probe 的核心收获)
actual_fee_accrual_token0 / token1
gas_spent_total_units / usd
total_cost_usd
net_pnl_usd
hold_duration_seconds
revoke_tx_hash
revoke_confirmed
```

## DB schema 提案（仅 proposal，本轮不创建）

命名约定：`lp_probe_*_v1`，与生产 `lpbot.*` 表完全隔离。

### `lp_probe_preflight_review_v1`

存储每次 preflight review 包（含本审查包本身）。

```sql
review_id UUID PRIMARY KEY
run_id TEXT NOT NULL
stage TEXT NOT NULL
candidate_pool TEXT NOT NULL
candidate_pair TEXT NOT NULL
candidate_fee_tier INT NOT NULL
candidate_notional_usd NUMERIC NOT NULL
candidate_hold_window TEXT NOT NULL
review_packet JSONB NOT NULL
dry_run_builder_allowed_next BOOL NOT NULL
human_approval_required BOOL NOT NULL DEFAULT true
human_approval_received BOOL NOT NULL DEFAULT false
human_approval_at TIMESTAMPTZ NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `lp_probe_execution_ledger_v1`

每次实际执行的 probe 一行（仅在未来获批执行时写入）。

```sql
probe_id UUID PRIMARY KEY
review_id UUID NOT NULL REFERENCES lp_probe_preflight_review_v1(review_id)
wallet_address TEXT NOT NULL
pool_address / token0 / token1 / fee_tier / tick_lower / tick_upper
notional_usd_planned NUMERIC NOT NULL
notional_usd_actual NUMERIC NULL
mint_tx_hash / token_id / approval_tx_hash / approval_amount
entry_block_number / exit_block_number
decrease_tx_hash / collect_tx_hash / swap_back_tx_hash / revoke_tx_hash
exit_decision_reason
realized_pnl_usd / actual_fee_accrual_usd / gas_spent_total_usd / net_pnl_usd
hold_duration_seconds
created_at / completed_at
```

### `lp_probe_position_fee_trace_v1`

hold 期间周期采样：`PRIMARY KEY (probe_id, sample_at)`。

### `lp_probe_exit_trace_v1`

exit 时一次性快照：`probe_id` PK FK 到 execution_ledger。

## 强制要求

- 表名命名空间 `lp_probe_*_v1`，**绝不**直接写到 `lpbot.positions` / `lpbot.shadow_*` / 其他生产表
- 表创建脚本必须独立 PR，独立审批，独立 migration 编号
- 本审查包不创建任何表 — 仅 schema proposal

## 安全

```text
tables_created_this_round       = false
wallet_or_tx_touched            = false
can_run_probe_now               = false
tiny_canary_allowed             = no
edge_proven                     = no
```
