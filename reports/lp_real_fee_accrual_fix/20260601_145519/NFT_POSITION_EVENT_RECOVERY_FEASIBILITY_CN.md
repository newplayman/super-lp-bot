# NFT Position Event Recovery Feasibility

- `NonfungiblePositionManager IncreaseLiquidity` can_query_now=`no` recover_token_id=`partial` blocker=`manager_contract_unknown_and_owner_unknown`
- `NonfungiblePositionManager DecreaseLiquidity` can_query_now=`no` recover_token_id=`partial` blocker=`manager_contract_unknown_and_owner_unknown`
- `NonfungiblePositionManager Collect` can_query_now=`no` recover_token_id=`partial` blocker=`manager_contract_unknown_and_no_position_owner`
- `ERC721 Transfer / NFPM Transfer` can_query_now=`no` recover_token_id=`partial` blocker=`owner_address_missing_and_manager_unknown`
- `Pool Mint / Burn` can_query_now=`partial` recover_token_id=`no` blocker=`pool_events_do_not_encode_nft_token_id`
- `Existing DB event tables` can_query_now=`yes` recover_token_id=`no` blocker=`candidate pools absent from canary tables and position_marks token_id empty`
- `External RPC eth_getLogs bounded` can_query_now=`partial` recover_token_id=`partial` blocker=`no bounded owner-linked source for tokenId`
