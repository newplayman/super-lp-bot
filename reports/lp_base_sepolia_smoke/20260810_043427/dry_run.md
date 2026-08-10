# Base Sepolia smoke dry-run（只读）

chainId=84532；full_contract_simulation_ready=False。

| stage | status |
|---|---|
| chain_id_assert | PASS |
| rpc_read_health | PASS |
| approve_exact_eth_call | PASS |
| mint_decrease_collect_revoke_eth_call | BLOCKED_CONTRACTS_NOT_CONFIGURED |
| sign_broadcast_receipt_ledger | NOT_EXECUTED_REQUIRES_COMMANDER_APPROVAL |

本轮仅 eth_chainId / eth_blockNumber / eth_getCode / eth_call；signed=false，broadcast_count=0。
