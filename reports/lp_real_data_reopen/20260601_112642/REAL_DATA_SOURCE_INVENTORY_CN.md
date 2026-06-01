# 真实数据源总览

| data_source_name | category | source_type | wallet | signature | tx | read_only_safe | available_now | priority | blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `NonfungiblePositionManager.positions(tokenId)` | `real_fee_accrual` | `contract_read` | `no` | `no` | `no` | `yes` | `partial` | `P2` | `tokenId_unknown_without_real_position_nft` |
| `UniswapV3Pool.slot0/liquidity/ticks/tickBitmap` | `v3_tick_liquidity` | `contract_read` | `no` | `no` | `no` | `yes` | `yes` | `P1` | `v3_pool_contract_mapping_needed` |
| `UniswapV3Pool.positions(positionKey)` | `real_fee_accrual` | `contract_read` | `no` | `no` | `no` | `yes` | `partial` | `P2` | `position_key_needs_owner_and_ticks` |
| `Mint/Burn/Collect/IncreaseLiquidity/DecreaseLiquidity logs` | `real_fee_accrual` | `event_logs` | `no` | `no` | `no` | `yes` | `partial` | `P2` | `actual_position_linkage_missing_without_tokenId_owner` |
| `Swap logs` | `real_fee_accrual` | `event_logs` | `no` | `no` | `no` | `yes` | `yes` | `P1` | `needs_pool_abi_and_window_selection` |
| `QuoterV2 static quote` | `precise_quote` | `rpc_call` | `no` | `no` | `no` | `yes` | `yes` | `P0` | `quoter_contract_mapping_by_protocol` |
| `Pool math fallback` | `precise_quote` | `existing_db` | `no` | `no` | `no` | `yes` | `yes` | `P1` | `approximation_only` |
| `External aggregator dry quote` | `precise_quote` | `external_api` | `no` | `no` | `no` | `yes` | `partial` | `P1` | `provider_selection_and_rate_limits` |
| `eth_feeHistory / gas oracle` | `real_cost_model` | `rpc_call` | `no` | `no` | `no` | `yes` | `yes` | `P1` | `needs_cost_scenario_policy` |
| `eth_estimateGas dry add/remove liquidity` | `real_cost_model` | `rpc_call` | `no` | `no` | `no` | `yes` | `partial` | `P2` | `requires_exact_calldata_and_position_params` |
| `Actual LP NFT fee accrual after probe` | `real_fee_accrual` | `future_probe_only` | `yes` | `yes` | `yes` | `no` | `no` | `REJECT` | `future_probe_only` |
| `Actual realized entry/exit receipts` | `real_cost_model` | `future_probe_only` | `yes` | `yes` | `yes` | `no` | `no` | `REJECT` | `future_probe_only` |
