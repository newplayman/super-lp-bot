# Meteora Pool Chain Verification — Stage E

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
verified                = 16
rejected                = 0
verified_target         = >= 10
status                  = PASS
meteora_dlmm_program    = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
```

## 1. Verification criteria

每个 candidate 都做：
- `getAccountInfo(pool_address)` (single-account; not GPA)
- `owner == Meteora DLMM program` AND `data_len == 904` (LbPair account size)
- 只有同时满足两个条件才被 `selected_for_sdk_decode = true`

## 2. Reason for rejections

| reason | count |
|---|---|
| owner_not_meteora_dlmm | (动态统计见 csv) |
| account_null | (动态统计见 csv) |
| data_len_mismatch | (动态统计见 csv) |

## 3. 安全断言

```text
this_stage_only_chain_verify       = true
no_keypair                         = true
no_signer                          = true
no_tx                              = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
v2_line_count_unchanged            = true
```

## 4. 下一阶段

进入 Stage F — SDK decode batch (DLMM.create + getActiveBin + getFeeInfo).
