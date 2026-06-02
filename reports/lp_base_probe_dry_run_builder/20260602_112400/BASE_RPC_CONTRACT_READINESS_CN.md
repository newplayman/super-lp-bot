# Base RPC + 合约 readiness

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: D
- run_id: `20260602_112400`
- wallet_address_masked: `0xb05b...d835`

## RPC endpoint

| 字段 | 值 |
|---|---|
| source | `public_fallback:https://base-rpc.publicnode.com` |
| env_keys 检查顺序 | `BASE_RPC_PRIMARY` → `LPBOT_BASE_RPC_URL` → `BASE_RPC_URL` |
| env 已设置 | **否**（`echo $BASE_RPC_PRIMARY` 空）；用 publicnode fallback |
| host_hash | `7d4aef4d` |
| 备注 | publicnode 是公共 endpoint；confidence=medium；`high` 需注入付费 endpoint |

## Chain 校验

| 字段 | 期望 | 观察 | 通过 |
|---|---|---|---|
| eth_chainId | 8453 (Base mainnet) | 8453 | ✓ |
| eth_blockNumber (latest) | — | **46807072** | observed |

## 合约 getCode 校验

| label | address | code_length_bytes | has_code | read_success |
|---|---|---|---|---|
| `pool_0x72ab388e` (本阶段冻结候选) | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | 22,962 | ✓ | ✓ |
| `uni_v3_npm_base` (NonfungiblePositionManager) | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` | 24,384 | ✓ | ✓ |
| `uni_v3_factory_base` | `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` | 24,535 | ✓ | ✓ |
| `uni_v3_quoter_v2_base` | `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a` | 8,273 | ✓ | ✓ |
| `weth_base` (canonical) | `0x4200000000000000000000000000000000000006` | 2,041 | ✓ | ✓ |
| `usdc_base` (canonical) | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` | 1,852 | ✓ | ✓ |

**all_contracts_have_code = true**

## 顶层 gate

```text
rpc_ready                  = true
all_contracts_have_code    = true
chain_id_match             = true
block_number_observed      = 46807072
```

## 已使用 RPC（read-only）

- `eth_chainId`
- `eth_blockNumber`
- `eth_getCode(to=<contract>, block=latest)` × 6 contracts

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
fabrication_blocked  = true     (RPC 失败时不编造合约地址/code)
```

未发送任何 `eth_sendTransaction` / `eth_sendRawTransaction`，未创建 signer。
