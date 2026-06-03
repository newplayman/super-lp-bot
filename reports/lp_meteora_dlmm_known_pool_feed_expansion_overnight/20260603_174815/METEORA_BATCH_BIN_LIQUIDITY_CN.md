# Meteora Batch Bin Liquidity — Stage G

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
pools_attempted                  = 16
bins_decoded                     = 0
bins_with_liquidity              = 0
pools_with_near_active_liquidity = 0
pools_with_sparse_liquidity      = 0
```

## 1. Coverage plan

- Start with 5 arrays
- Upgrade to 9 if no liquidity in initial
- Upgrade to 15 (cap) if still no liquidity
- Spec hard cap: 15 arrays (per V7); 不无限扩展

## 2. Decode method

- Single-account `getAccountInfo(bin_array_pubkey)`
- BinArray layout: header 80 bytes + 70 bins × 96 bytes
- xAmount at offset bin*96+8 (u64 LE)
- yAmount at offset bin*96+16 (u64 LE)

## 3. 安全断言

```text
this_stage_only_decode            = true
no_gpa                            = true (single-account only)
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
```

## 4. 下一阶段

进入 Stage H — quote batch (10U/20U/100U)。
