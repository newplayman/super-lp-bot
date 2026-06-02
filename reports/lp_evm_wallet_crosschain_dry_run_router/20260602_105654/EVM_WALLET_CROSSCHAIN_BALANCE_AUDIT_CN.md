# 跨链钱包余额审计

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: D
- wallet_address_masked: `0xb05b...d835`
- rpc: Base `publicnode (host_hash=1d9c12cd)` / BSC `publicnode (host_hash=5a701356)`

## 价格 anchor（从 V3 pool slot0 推导）

| anchor | 值 | 来源 |
|---|---|---|
| WETH USD | **$1,979.86** | Uniswap V3 USDC/WETH 0.05% slot0 (Base `0xd0b53d9277...`) |
| cbBTC USD | **$69,532.01** | Uniswap V3 cbBTC/USDC slot0 (Base `0x4e962bb3...`) |
| WBNB USD | **$679.90** | PancakeSwap V3 USDT/WBNB 0.01% slot0 (BSC `0x172fcd41...`) |
| USDC / USDT / DAI / BUSD | $1（假设） | stablecoin anchor |

## Base 链余额

| token | balance | ≈ USD |
|---|---|---|
| **ETH (native)** | 0.0000905 ETH | **$0.18** |
| **WETH** | 0.00247 WETH | **$4.89** |
| **USDC** | **21.77 USDC** | **$21.77** |
| USDT (Tether USD₮0) | 0 | $0.00 |
| cbBTC | 0 | $0.00 |
| DAI | 0 | $0.00 |
| **base_total_usd_proxy** | | **≈ $26.84** |

## BSC 链余额

| token | balance | ≈ USD |
|---|---|---|
| BNB (native) | 0 | $0.00 |
| WBNB | 0 | $0.00 |
| USDT | 0 | $0.00 |
| USDC | 0 | $0.00 |
| BUSD | 0 | $0.00 |
| CAKE | 0 | (无 USD anchor) |
| **bsc_total_usd_proxy** | | **$0.00** |

## 关键聚合

| 字段 | 值 |
|---|---|
| likely_funded_chain | **`base`** |
| base_native_eth_usd | $0.18 |
| base_tokens_usd_total | $26.67 |
| bsc_native_bnb_usd | $0.00 |
| bsc_tokens_usd_total | $0.00 |

## 10U / 20U readiness（基于硬阈值 $0.20 gas + $10 / $20 token-side）

| | base | bsc |
|---|---|---|
| ready for 10U | **false（gas $0.18 < $0.20，但仅差 $0.02）** | false（无任何资金） |
| ready for 20U | **false（gas $0.18 < $0.20；且 token side $26.67 vs 阈值 $20 OK）** | false |

### 解读

布尔标志说 false 是因为 **gas balance 比保守阈值 $0.20 少 $0.02**。但实际情况更微妙：

- **Base gas balance ≈ $0.18 = 9.0e-5 ETH。** Base mainnet 当前 gas 价 ≈ 0.05-0.1 gwei；round-trip (approve+approve+mint+decrease+collect+revoke+revoke ≈ 870k units) 在 0.1 gwei 下耗约 8.7e-5 ETH ≈ **$0.17**。技术上**够跑一次 LP 周期，但完全没缓冲**。
- **Base USDC + WETH 合计 ≈ $26.67**，足够 10U (USDC ~ $5 + WETH ~ $5) 甚至 20U (USDC ~ $10 + WETH ~ $10)。
- **BSC 全 0** — 没有 BSC 资金，BSC 候选**完全不可 dry-run**（即使做读余额已经确认到这一点，无 BNB ⇒ 连 read-only `eth_estimateGas(from=wallet)` 都会因 zero gas balance 退化）。

### 修正后的实用结论

```text
base_can_dry_run_with_wallet_address = yes BUT gas_balance is borderline
                                       (recommend topping up 0.0005 ETH ≈ $1 to ensure safe margin
                                        before any execution stage; this stage does NOT require it)
bsc_can_dry_run_with_wallet_address  = NO; wallet has no BSC funds at all
```

## 安全标记

```text
calls used: eth_getBalance, ERC20.balanceOf, ERC20.decimals, ERC20.symbol,
            pool.slot0 / token0 / token1 (read-only eth_call)
wallet_or_tx_touched = false
can_run_probe_now    = false
```

钱包地址在所有产物中以 `0xb05b...d835` 掩码呈现；CSV 也用同样的 mask。
