# Base 钱包余额 + Allowance 刷新

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: E
- run_id: `20260602_112400`
- wallet_address_masked: `0xb05b...d835`
- frozen_pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`
- rpc: `https://base-rpc.publicnode.com` (host_hash=`7d4aef4d`)

## Block 锁定

| 字段 | 值 |
|---|---|
| block_number | **46807131** |
| block_hex | `0x2ca385b` |
| block_tag | `latest` |
| 相对 Phase D 差 | +59 blocks（足够 fresh） |

## 余额 (eth_getBalance + ERC20.balanceOf)

### Native ETH（gas）

| 字段 | 值 |
|---|---|
| raw | 90,470,751,043,807 wei |
| human | **0.000090470751 ETH** |
| ≈ USD | $0.18 (按 upstream anchor $1,981.12/WETH) |

### WETH (token0)

| 字段 | 值 |
|---|---|
| raw | 2,470,131,003,793,800 |
| human | **0.0024701310037938 WETH** |
| ≈ USD | **$4.89** (anchor $1,979.86) |

### USDC (token1)

| 字段 | 值 |
|---|---|
| raw | 21,774,783 |
| human | **21.774783 USDC** |
| ≈ USD | **$21.77** (anchor $1) |

合计 **$26.84**（与 upstream router Phase D 一致，未变动）

## Allowance (ERC20.allowance)

### WETH → uni_v3_npm_base (`0x03a520b3...`)

| 字段 | 值 |
|---|---|
| raw | 2,470,131,003,793,800 |
| human | **0.0024701310037938 WETH** |
| 与余额关系 | **正好 = WETH 余额**（典型 ApproveExact 旧痕迹，余额未变） |
| 10U mint 是否够 | **no**（10U LP 需 ≈0.00253 WETH；allowance 0.00247 < 0.00253） |
| 结论 | **10U / 20U 都需新一次 `approve(NPM, exact_amt)` for WETH** |

### USDC → uni_v3_npm_base

| 字段 | 值 |
|---|---|
| raw | 5,000,000 |
| human | **5.0 USDC** |
| 10U mint 是否够 | **yes**（10U LP 需 ≈ $5 USDC） |
| 20U mint 是否够 | **no**（20U LP 需 ≈ $10 USDC） |
| 结论 | **10U 不需新 approve USDC；20U 需新 approve USDC** |

## ApproveExact 预测

| notional | WETH | USDC | 备注 |
|---|---|---|---|
| **10U** | 需新 approve 0.00253e18 WETH | **无需** | ApproveExact（不 ApproveMax） |
| **20U** | 需新 approve 0.00506e18 WETH | 需新 approve 10e6 USDC | ApproveExact（不 ApproveMax） |

**ApproveMax 政策守住 invariant #9**。任何 mint 之前先 `approve(NPM, exact_amt)`；mint 完成后 `approve(NPM, 0)` 撤销（invariant #10 强制）。

## 调用类型

- `eth_chainId`
- `eth_blockNumber`
- `eth_getBalance(wallet, latest)`
- `eth_call balanceOf(wallet)` × 2
- `eth_call allowance(wallet, NPM)` × 2

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
fabrication_blocked  = true
```

未发送 `eth_sendTransaction` / `eth_sendRawTransaction`，未创建 signer。
