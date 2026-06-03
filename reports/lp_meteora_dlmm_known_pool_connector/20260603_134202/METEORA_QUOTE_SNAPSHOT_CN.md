# Meteora Quote Snapshot Attempt — Stage H

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键结果

```text
pools_attempted          = 2
notionals_per_pool       = 2 (10U, 20U)
total_quote_attempts     = 4
quote_success_count      = 0
quote_blocked_count      = 4
blocker                  = 403 Forbidden on getBinArrayForSwap (per V3 + Stage G)
sdk_method               = dlmmPool.swapQuote (read-only; returns quote object; no tx)
no_quote_fabricated      = true
```

## 1. Per-attempt 结果

| pool | notional | token_in | token_out | quote_success | blocker |
|---|---|---|---|---|---|
| `5BKxfWMb...` | 10U | Y (USDC) | X (SOL) | ❌ | 403 on getBinArrayForSwap |
| `5BKxfWMb...` | 20U | Y (USDC) | X (SOL) | ❌ | 403 on getBinArrayForSwap |
| `9DiruRpj...` | 10U | Y (USDC) | X | ❌ | 403 on getBinArrayForSwap |
| `9DiruRpj...` | 20U | Y (USDC) | X | ❌ | 403 on getBinArrayForSwap |

## 2. 根因

`dlmmPool.swapQuote(inAmount, swapYtoX, allowedSlippage, binArrays, isPartialFill, maxExtraBinArrays)` 的第 4 个参数 `binArrays: BinArrayAccount[]` 必须在调用前**已填充**. SDK 唯一的 read-only 填充方式是 `dlmmPool.getBinArrayForSwap(swapYtoX, count)`, 而这被 public RPC 403 阻断 (per Stage G).

## 3. 替代 quote 路径

| 路径 | 描述 | 状态 |
|---|---|---|
| paid RPC (Helius / Triton / QuickNode) | 同样 SDK 调用, 更高 rate limit | needs operator key |
| known bin array index (从 cache / indexer) | 直接 `connection.getMultipleAccountsInfo([binArrayPubkey])` 拉 1 个账户, 不需要 GPA | needs operator input |
| 手动算 quote 不通过 SDK | 读 lbPair + 1 bin array 后用 `swapExactInQuoteAtBin` (SDK helper) 本地算 | needs at least 1 bin array |
| skip quote | data_confidence='blocked'; 不算 EV | current V4 state |

## 4. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不调用 pos-create / tx-builder (`dlmmPool.swap(...)` 之类)
- ❌ 不构造 transaction
- ❌ 不调用 sendTransaction
- ❌ 不 paid RPC (无 key)
- ❌ 不 fake quote (V4 honest finding: quote_success=false; amount_out_raw=null)
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
quote_attempted             = true
no_quote_fabricated        = true
quote_tx_builder_called    = false
solana_wallet_or_keypair_touched = false
transaction_sent          = false
can_run_probe_now         = false
v2_line_count_unchanged   = true (992)
```

## 6. 下一阶段

进入 Stage I — connector readiness matrix (6 表状态判定).
