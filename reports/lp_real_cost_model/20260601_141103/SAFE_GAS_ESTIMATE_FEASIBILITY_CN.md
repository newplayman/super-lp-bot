# Safe Gas Estimate Feasibility

- `quoter_returned_gasEstimate` applies_to=`swap_route_quote_and_exit_conversion` can_execute_now=`yes` confidence=`medium` blocker=``
- `eth_estimateGas_dummy_from` applies_to=`mint_remove_collect_dry_estimate` can_execute_now=`no` confidence=`low` blocker=`may require realistic calldata and from context; keep future_probe_only in v1`
- `historical_gas_benchmark` applies_to=`mint_remove_collect` can_execute_now=`no` confidence=`low` blocker=`no trusted prior receipt corpus in current repo state`
- `static_configured_gas_units` applies_to=`mint_remove_collect_and_approval` can_execute_now=`yes` confidence=`low` blocker=`diagnostic only; must remain future_probe_only`
