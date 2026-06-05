# Node Report: 6h (R0 read-only, partial_sample=True)

- node_stage: 6h
- run_id: 20260605_043726
- generated_at_utc: 2026-06-05T08:37:52Z
- partial_sample: **True**

## Gate

| 字段 | 值 |
|---|---|
| gate_status | **WARN_ACCEPTABLE** |
| gate_pass | False |
| can_continue_collection | True |
| can_enter_preflight_design | False |
| can_use_for_preflight | False |
| can_run_probe_now | **False** (locked false) |
| tiny_canary_allowed | **"no"** (locked no) |
| edge_proven | **"no"** (locked no) |
| wallet_or_tx_touched | **False** |
| transaction_sent | **False** |

## Coverage

| chain | observed | pool_count | reason |
|---|---|---|---|
| base | False | 0 | chain_not_observed_in_data_dir |
| bsc | False | 0 | bsc_chain_adapter_not_implemented_yet |
| solana | True | 20 | - |
| ethereum | False | 0 | chain_skipped_for_safety_mainnet_only_design_target |
| arbitrum | False | 0 | chain_skipped_for_safety_mainnet_only_design_target |
| optimism | False | 0 | chain_skipped_for_safety_mainnet_only_design_target |
| polygon | False | 0 | chain_skipped_for_safety_mainnet_only_design_target |

## Best Candidates (count=0)



## Rejected Candidates (count=20)

- solana/meteora_dlmm/<smoke_pool_meteora_dlmm_a> (?): no_quote_ready
- solana/orca_whirlpool/<smoke_pool_orca_whirlpool_a> (?): no_quote_ready
- solana/raydium_clmm/<smoke_pool_raydium_clmm_a> (?): no_quote_ready
- solana/raydium_cpmm/<smoke_pool_raydium_cpmm_a> (?): no_quote_ready
- solana/solana_stable/<smoke_pool_solana_stable_a> (?): no_quote_ready
- solana/meteora_dlmm/<smoke_pool_meteora_dlmm_a> (?): no_quote_ready
- solana/orca_whirlpool/<smoke_pool_orca_whirlpool_a> (?): no_quote_ready
- solana/raydium_clmm/<smoke_pool_raydium_clmm_a> (?): no_quote_ready
- solana/raydium_cpmm/<smoke_pool_raydium_cpmm_a> (?): no_quote_ready
- solana/solana_stable/<smoke_pool_solana_stable_a> (?): no_quote_ready
- solana/meteora_dlmm/<smoke_pool_meteora_dlmm_a> (?): no_quote_ready
- solana/orca_whirlpool/<smoke_pool_orca_whirlpool_a> (?): no_quote_ready
- solana/raydium_clmm/<smoke_pool_raydium_clmm_a> (?): no_quote_ready
- solana/raydium_cpmm/<smoke_pool_raydium_cpmm_a> (?): no_quote_ready
- solana/solana_stable/<smoke_pool_solana_stable_a> (?): no_quote_ready
- solana/meteora_dlmm/<smoke_pool_meteora_dlmm_a> (?): no_quote_ready
- solana/orca_whirlpool/<smoke_pool_orca_whirlpool_a> (?): no_quote_ready
- solana/raydium_clmm/<smoke_pool_raydium_clmm_a> (?): no_quote_ready
- solana/raydium_cpmm/<smoke_pool_raydium_cpmm_a> (?): no_quote_ready
- solana/solana_stable/<smoke_pool_solana_stable_a> (?): no_quote_ready

## Row counts

| 字段 | 值 |
|---|---|
| checkpoint_count_observed | 4 |
| checkpoint_count_expected | 6 |
| pool_snapshot_rows | 20 |
| quote_snapshot_rows | 120 |
| fee_velocity_rows | 100 |
| liquidity_distribution_rows | 20 |
| market_regime_rows | 28 |
| actual_fee_accrual_placeholder_rows | 0 (R0 = 0) |

## Recommended Next Action

**continue_collection_with_note**

> 节点报告 ≠ 批准实盘. R0 阶段无 actual fee. B 线需要 tokenId 实盘数据, 需用户单独批准.
