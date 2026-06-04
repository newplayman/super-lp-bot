# Orca Pool Chain Verification — Stage F

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
candidate_count          = 75
verified_pool_count      = 75   (100% verify success)
owner_mismatch_count     = 0
data_len_mismatch_count  = 0    (所有池 data_len = 653 bytes)
account_null_count       = 0
rpc_error_count          = 0
duplicate_count          = 0
selected_for_sdk_decode  = 75
```

## 1. 验证规则

```text
program_id = whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc (Orca Whirlpools)
data_len   = 653 bytes (实际链上测量, V1 早 stage 估计 800+ 不准)
commitment = confirmed
encoding   = base64
```

任何 owner != program_id 或 data_len < 600 → reject。

## 2. 75 个真实 Orca Whirlpool 池 (按 fee_rate_bps / vol24h 排)

完整 75 行见 `orca_pool_chain_verification.csv`。前 20 预览 (数据从 collection metadata):

| rank | pool | name | tick_spacing | fee_bps | tvl | vol24h |
|---|---|---|---|---|---|---|
| 1 | (待 G 后) | SOL/USDC | 64 | 30 | high | high |
| 2 | (待 G 后) | SOL/USDC | 4 | 4 | high | high |
| ... | | | | | | |

## 3. 结构性发现

所有 75 个 Orca pool 链上 data_len **统一 = 653 bytes**。这是 Orca Whirlpool account 大小。SDK 8.0.0 + IDL 与该大小一致。

所有 75 个 owner 全部 = Orca Whirlpools program, 没有 mislabel。

## 4. 安全断言

```text
chain_verify_method = getAccountInfo via public RPC
no_keypair_loaded   = true
no_signer_constructed = true
no_transaction_sent = true
solana_wallet_or_keypair_touched = false
```

## 5. 下一阶段

进入 Stage G — Whirlpool account decode via @orca-so/whirlpools 8.0.0 SDK (tokenMintA/B, tickSpacing, feeRate, liquidity, sqrtPrice, tickCurrentIndex)。
