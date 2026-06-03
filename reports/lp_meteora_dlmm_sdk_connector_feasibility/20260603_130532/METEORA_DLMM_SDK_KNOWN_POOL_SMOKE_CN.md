# Meteora DLMM SDK Known-Pool Read-Only Smoke — Stage E

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`

## 0. 关键结果

```text
smoke_attempted                = true
smoke_success                  = true (DLMM.create succeeded for 2/2 pools; full struct decode)
pools_attempted                = 2
pools_full_decode              = 2
pools_bin_array_lookup         = 0/2 (blocked on public RPC 403; needs paid RPC or known_bin_array_index)
pools_lock_info                = 0/2 (blocked on RPC 410; needs paid RPC)
sdk_package                    = @meteora-ag/dlmm@1.9.10
cluster                        = mainnet-beta
rpc_url_used                   = https://solana.publicnode.com (primary) + https://api.mainnet-beta.solana.com (fallback)
confidence                     = 0.85
```

## 1. 真实链上 decoded state (V3 mainnet 实际)

### 1.1 Pool A: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` (from `swap_quote.ts`)

| field | value | type |
|---|---|---|
| pool_address | `5BKxfWMb...baqyF` | string |
| pool_owner | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | pubkey (= Meteora DLMM program) |
| token_x | `So11111111111111111111111111111111111111112` | pubkey (= Wrapped SOL) |
| token_y | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | pubkey (= USDC) |
| token_x_decimals | 9 | int |
| token_y_decimals | 6 | int |
| bin_step | 2 | u16 |
| active_bin_id | -12248 | i32 |
| active_bin_price | 0.086349257542837731428 | Decimal (1 SOL ≈ 11.58 USDC) |
| active_bin_x_amount | 0 | u64 |
| active_bin_y_amount | 0 | u64 |
| fee_base_bps | 0.02 | % |
| fee_max_bps | 10 | % |
| fee_protocol_bps | null | (SDK returned undefined) |
| reserve_x_amount | 49468352994 | u64 (= 49.47 SOL in raw) |
| reserve_y_amount | 1064410439 | u64 (= 1064.41 USDC in raw) |
| liquidity_fields_available | true | — |
| bin_array_lookup | blocked (403) | n/a (needs paid RPC) |
| lock_info_lookup | blocked (410) | n/a (needs paid RPC) |
| latency_ms_total | 8725 | — |

### 1.2 Pool B: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` (from `fetch_lb_pair_lock_info.ts`)

| field | value | type |
|---|---|---|
| pool_address | `9DiruRpj...Fz2ad` | string |
| pool_owner | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | pubkey (= Meteora DLMM program) |
| token_x | `FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P` | pubkey (= 6-dec token; identity not in our scope) |
| token_y | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | pubkey (= USDC) |
| token_x_decimals | 6 | int |
| token_y_decimals | 6 | int |
| bin_step | 100 | u16 |
| active_bin_id | -236 | i32 |
| active_bin_price | 0.095533521620978319249 | Decimal (1 X ≈ 0.0955 USDC) |
| active_bin_x_amount | 59299208888 | u64 (= 59.30 X in raw) |
| active_bin_y_amount | 1661806709 | u64 (= 1661.81 USDC in raw) |
| fee_base_bps | 1.5 | % |
| fee_max_bps | 10 | % |
| fee_protocol_bps | null | — |
| reserve_x_amount | 101593140348172 | u64 |
| reserve_y_amount | 2200122802740 | u64 |
| liquidity_fields_available | true | — |
| bin_array_lookup | blocked (403) | n/a (needs paid RPC) |
| lock_info_lookup | blocked (410) | n/a (needs paid RPC) |
| latency_ms_total | 7498 | — |

## 2. SDK methods called (read-only, per spec)

| method | call site | result |
|---|---|---|
| `DLMM.create(connection, PublicKey, {cluster:"mainnet-beta"})` | per-pool | success for 2/2 |
| `dlmmPool.lbPair.binStep` | direct field | success |
| `dlmmPool.tokenX.publicKey` | direct field | success |
| `dlmmPool.tokenY.publicKey` | direct field | success |
| `dlmmPool.tokenX.mint.decimals` | direct field | success |
| `dlmmPool.tokenY.mint.decimals` | direct field | success |
| `dlmmPool.tokenX.amount` | direct field | success |
| `dlmmPool.tokenY.amount` | direct field | success |
| `dlmmPool.getActiveBin()` | per-pool | success for 2/2 |
| `dlmmPool.getFeeInfo()` | per-pool | success for 2/2 |
| `dlmmPool.getBinArrayForSwap(true, 1)` | per-pool | blocked on public RPC (403 / 410) |
| `dlmmPool.getLbPairLockInfo()` | per-pool | blocked on public RPC (410 "disabled") |

## 3. 公开 RPC 限制 (real finding)

| method | publicnode 状态 | mainnet-beta 状态 |
|---|---|---|
| `getMultipleAccountsInfo` (DLMM.create 内) | OK | OK |
| `getAccountInfo` (lock info 内部) | OK | OK |
| extra `getProgramAccounts` (bin_array_derive) | 403 blocked | 410 disabled |
| extra `getMultipleAccounts` (lock info) | 410 disabled | 410 disabled |

→ **getBinArrayForSwap** 和 **getLbPairLockInfo** 在 public RPC 上**不可用** (per-tenant restrictions). 同样情况 V1 / V2 已观察到: 公共 RPC 不支持某些 "non-default" methods.

→ **Conclusion**: Stage E smoke 成功 (DLMM.create + getActiveBin + getFeeInfo + reserve fields); quote smoke (Stage F) **会** 失败, 因为 quote 需要 binArrays, 而 binArrays 拉取在 public RPC 上被 403/410 阻断.

## 4. 真实数据价值

两个 pool 都给出了**完整**结构化 on-chain state:
- LbPair fields (bin_step, active_id, status, etc.)
- token mints + decimals
- reserves (X / Y)
- fee params
- active bin price (real market data)
- active bin per-side amounts

这正是 Stage G (connector schema) 设计的 6 张表所需要的 raw data。quote smoke 受 bin array 阻断是预期内的 (per V1 GPA blocker); **不**代表 connector 不可行, 而是 quote 需要 paid RPC 或先验 bin array index。

## 5. 严格只读边界 (本轮已遵守)

```text
× 未 instantiate Keypair
× 未调用任何 pos-create / tx-builder / swap / open_lp / close_lp / collect_fee method
× 未 import @solana/wallet-adapter-*
× 未调用 sendTransaction
× 未签名
× 未构造 transaction
× 未启动 live/canary/paper
× repo root 不动
× npm install 仍在 /tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID}/
× smoke script 在 repo scripts/; 但**只**调 read-only methods
```

## 6. 安全断言

```text
smoke_read_only        = true
no_keypair_used        = true
no_signer_used         = true
no_wallet_adapter      = true
no_transaction_built   = true
no_sendTransaction     = true
solana_wallet_or_keypair_touched = false
transaction_sent       = false
can_run_probe_now      = false
v2_line_count_unchanged = true (992)
```

## 7. 下一阶段

进入 Stage F — quote smoke (10U/20U). **预期**: quote **会** 受 bin_array 403/410 阻断; 我们仍然跑 SDK swapQuote, capture 实际 error, 然后进入 Stage H strategy decision.
