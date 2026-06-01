# Real Cost Component Inventory

- `precise_quote_gas_estimate` source=`precise_quote_results.gas_estimate` available=`yes` future_probe_only=`no` confidence=`medium`
- `quote_slippage_and_route_spread` source=`precise_quote_results.estimated_slippage_pct` available=`partial` future_probe_only=`no` confidence=`low`
- `lp_add_gas` source=`static scenario gas units` available=`partial` future_probe_only=`yes` confidence=`low`
- `lp_remove_collect_gas` source=`static scenario gas units` available=`partial` future_probe_only=`yes` confidence=`low`
- `base_chain_gas_price` source=`eth_gasPrice + eth_feeHistory` available=`yes` future_probe_only=`no` confidence=`medium`
- `fixed_operational_cost` source=`diagnostic only` available=`partial` future_probe_only=`yes` confidence=`low`
