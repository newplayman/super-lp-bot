# EVM Chain RPC Readiness（只读）

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: C

## Base

| 字段 | 值 |
|---|---|
| chain | base |
| expected_chain_id | 8453 |
| rpc_present | yes |
| fallback_rpc_used | yes (env `BASE_RPC_PRIMARY` 未设置) |
| source | `public_fallback:base-rpc.publicnode.com` |
| host_hash | `1d9c12cd` |
| chain_id_read | 8453 |
| chain_id_match | yes |
| latest_block | 46,804,318 |
| rpc_readonly_ready | **yes** |
| confidence | medium (公共 endpoint；要 `high` 需 `BASE_RPC_PRIMARY` 注入付费 endpoint) |

## BSC

| 字段 | 值 |
|---|---|
| chain | bsc |
| expected_chain_id | 56 |
| rpc_present | yes |
| fallback_rpc_used | yes (env `BSC_RPC_PRIMARY` 未设置) |
| source | `public_fallback:bsc-rpc.publicnode.com` |
| host_hash | `5a701356` |
| chain_id_read | 56 |
| chain_id_match | yes |
| latest_block | 101,869,207 |
| rpc_readonly_ready | **yes** |
| confidence | medium |

## 说明

- 端点 URL **不打印**；只输出 8-char SHA-256 host hash。
- 两条链都 ready，本轮可继续 Phase D 余额审计。
- `env_keys` 检查的环境变量：BASE 用 `BASE_RPC_PRIMARY` / `LPBOT_BASE_RPC_URL` / `BASE_RPC_URL`；BSC 用 `BSC_RPC_PRIMARY` / `LPBOT_BSC_RPC_URL` / `BSC_RPC_URL` / `BNB_RPC_URL` / `RPC_BSC_URL`。均未设置 → fallback 到 publicnode。

## 安全

```text
calls used:          eth_chainId, eth_blockNumber (read-only)
calls forbidden:     eth_sendTransaction, eth_sendRawTransaction, anything signing
wallet_or_tx_touched = false
can_run_probe_now    = false
```
