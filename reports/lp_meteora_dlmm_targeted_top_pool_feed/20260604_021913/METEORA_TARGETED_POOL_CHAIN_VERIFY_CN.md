# Meteora Targeted Pool Chain Verify — Stage E

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 关键结果

```text
candidate_count            = 60
verified_pool_count        = 56
owner_mismatch_count       = 4   (实际是其它 AMM，DexScreener dexId 标错)
data_len_mismatch_count    = 0
account_null_count         = 0
rpc_error_count            = 0
duplicate_count            = 0
selected_for_sdk_decode    = 56  (全部 verified)
```

## 1. 验证规则

```text
program_id = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo (Meteora DLMM)
data_len   = 904 bytes (LbPair struct)
commitment = confirmed
encoding   = base64
```

任何 owner != program_id 或 data_len != 904 → reject。

## 2. 拒绝的 4 个 (实际不是 Meteora DLMM)

| pool_address | 实际 owner | 实际协议 |
|---|---|---|
| `Hdh5jVfUktsw` | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | **Raydium CPMM** |
| `BnztueWcXv93` | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | **Raydium CPMM** |
| `7EJSgV2pthhD` | `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` | **Orca Whirlpool** |
| `5NQTw1WqVEt6` | `Eo7WjKq67rjJQSZxS6zYkapzY3eMj6Xy8X5EQVn5UaB` | **Orca Whirlpool** |

DexScreener 错误地把这些池标成 `dexId=meteora`（因为 URL 包含 `meteora` 字样）。链上验证过滤掉了它们。这印证了 spec "B 类 source 必须 chain verify" 的要求。

## 3. 56 个 Meteora DLMM 真实池 (selected_for_sdk_decode)

按 vol24h 排前 20：

| rank | pool_address | name | vol24h | reserve |
|---|---|---|---|---|
| 1 | `5rCf1DM8LjKTz5gBRKJBQzu` | SOL/USDC | 31,425,809 | 2,754,655 |
| 2 | `7tSbDdxxUPMi` | USDC/SOL | 17,799,151 | 123,337 |
| 3 | `ANCx141SujgV` | HYPE/USDC | 14,663,540 | 3,874,428 |
| 4 | `BGm1tav58oGc` | SOL/USDC | 11,065,853 | 3,410,714 |
| 5 | `9ToMYnmEeYKc` | ZEC/USDC | 10,696,518 | 1,670,659 |
| 6 | `9SMp4yLKGtW9` | PUMP/USDC | 9,616,387 | 1,640,728 |
| 7 | `81GpCm4d13y8` | HYPE/SOL | 5,839,613 | 1,553,909 |
| 8 | `4vQaxcqAyJFc` | HYPE/USDC | 5,827,275 | 1,359,746 |
| 9 | `6oQ9wVex4mKZ` | HYPE/SOL | 5,498,985 | 291,198 |
| 10 | `6F4rVnmVc1A2` | HYPE/USDC | 5,223,231 | 485,120 |
| 11 | `F2BstVuVWqBn` | HYPE/USDC | 5,011,811 | 136,761 |
| 12 | `Hz1EtXTGaFEt` | cbBTC/SOL | 4,713,737 | 134,736 |
| 13 | `3C5YE97HADPD` | TRUMP/USDC | 3,941,374 | 3,752,595 |
| 14 | `HDhWhQCBrSh9` | cbBTC/SOL | 3,101,074 | 112,110 |
| 15 | `7ubS3GccjhQY` | cbBTC/USDC | 2,466,776 | 621,987 |
| 16 | `HTvjzsfX3yU6` | SOL/USDC | 2,316,310 | 366,214 |
| 17 | `8ztFxjFPfVUt` | USELESS/SOL | 2,206,360 | 447,246 |
| 18 | `FhdW3Y6Ea6hX` | wNEAR/USDC | 2,179,929 | 830,208 |
| 19 | `GeUkx21Vc6yg` | MUSK/USDC | 2,171,212 | 271,738 |
| 20 | `6qz7THwQvcjF` | BP/USDC | 1,886,987 | 147,762 |

(完整 56 行见 `meteora_targeted_pool_chain_verify.csv`)

## 4. 安全断言

```text
chain_verify_method       = getAccountInfo via public RPC
no_keypair_loaded         = true
no_signer_constructed     = true
no_transaction_sent       = true
solana_wallet_or_keypair_touched = false
verified_pool_count       = 56
target_verified_pool_count (>=10) = met
```

## 5. 下一阶段

进入 Stage F — 用 @meteora-ag/dlmm SDK 对 56 个池做 full LbPair decode，重点 base_fee_bps / max_fee_bps / bin_step / active_bin。
