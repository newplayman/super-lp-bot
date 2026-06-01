# Fee Accrual Contract ABI Inventory

- `NonfungiblePositionManager` `positions(tokenId)` access=`eth_call` read_only_safe=`yes` status=`usable_if_token_id_exists`
- `V3Pool` `slot0() / ticks(int24) / feeGrowthGlobal{0,1}X128()` access=`eth_call` read_only_safe=`yes` status=`usable`
- `NonfungiblePositionManager` `Collect / IncreaseLiquidity / DecreaseLiquidity / Mint / Burn logs` access=`eth_getLogs` read_only_safe=`yes` status=`usable_if_position_lineage_exists`
- `Router / PositionManager` `mint / increaseLiquidity / decreaseLiquidity / collect / burn / approve` access=`transaction` read_only_safe=`no` status=`rejected`
