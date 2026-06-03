# Meteora Batch Quote — Stage H

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
total_attempts          = 48
quote_success           = 0
unique_quote_ready_pools = 0
target                  = >= 5 unique pools
status                  = PARTIAL
```

## 1. Per-pool quote summary

| pool | 10U | 20U | 100U |
|---|---|---|---|
| `2G7fxAhB…` | ❌ | ❌ | ❌ |
| `5BKxfWMb…` | ❌ | ❌ | ❌ |
| `6VxKTxaV…` | ❌ | ❌ | ❌ |
| `6eR5rRde…` | ❌ | ❌ | ❌ |
| `6oFWm7KP…` | ❌ | ❌ | ❌ |
| `6qz7THwQ…` | ❌ | ❌ | ❌ |
| `8UYCgRrx…` | ❌ | ❌ | ❌ |
| `8ztFxjFP…` | ❌ | ❌ | ❌ |
| `9DiruRpj…` | ❌ | ❌ | ❌ |
| `9bL8Pptp…` | ❌ | ❌ | ❌ |
| `BCv5Ggg5…` | ❌ | ❌ | ❌ |
| `Cgnuirsk…` | ❌ | ❌ | ❌ |
| `CnK82s8e…` | ❌ | ❌ | ❌ |
| `DJ8qzBm3…` | ❌ | ❌ | ❌ |
| `FhdW3Y6E…` | ❌ | ❌ | ❌ |
| `H9b4sPAe…` | ❌ | ❌ | ❌ |

## 2. Direction

- All quotes use `y_to_x` (USDC → other token) when Y is USDC-stable
- `x_to_y` requires X USD price (V1 heuristic; not in scope)

## 3. Honest gap

- 实际 on-chain price impact 未测量 (V6 quote 缺 price_impact field)
- 实际 bins crossed 未测量 (some quote APIs return null)
- 实际 fee 未测量 (SDK returns null in some pool configs)

## 4. 安全断言

```text
this_stage_only_quote             = true
no_swap_tx_builder_called         = true
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
```

## 5. 下一阶段

进入 Stage I — pool scoring (fee / liquidity / risk heuristic)。
