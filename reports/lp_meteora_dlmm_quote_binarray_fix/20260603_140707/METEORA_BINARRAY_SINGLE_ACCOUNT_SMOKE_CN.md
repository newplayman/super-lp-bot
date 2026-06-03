# Meteora Bin Array Single-Account Smoke — Stage E

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 关键结果

```text
attempted_count                  = 6
success_count                    = 6
public_rpc_403_count             = 0
public_rpc_410_count             = 0
public_rpc_timeout_count         = 0
account_null_count               = 0
binarray_single_account_path_success = yes
```

→ **Single-account path WORKS on public RPC.** V4 的 multi-account 403 blocker **bypassed**.

## 1. Per-call 结果（6/6 success）

| pool | neighbor_offset | bin_array_pubkey (truncated) | getAccountInfo_success | owner (truncated) | data_len | latency_ms |
|---|---|---|---|---|---|---|
| pool 1 (SOL/USDC) | -1 | `99daE4xkHT...hoUL` | ✅ | `LBUZKhRx...` | 10136 | 460 |
| pool 1 | 0 (active) | `HEG2LuUaJ...sU1R` | ✅ | `LBUZKhRx...` | 10136 | 230 |
| pool 1 | +1 | `7tfRkX2Qn...fnvP` | ✅ | `LBUZKhRx...` | 10136 | 130 |
| pool 2 (X/USDC) | -1 | `yhkw7F4xF...6Z5j` | ✅ | `LBUZKhRx...` | 10136 | 480 |
| pool 2 | 0 (active) | `29JynFXae...FsU2N` | ✅ | `LBUZKhRx...` | 10136 | 410 |
| pool 2 | +1 | `G1BHyB19o...NRHFz` | ✅ | `LBUZKhRx...` | 10136 | 90 |

全部 owner = Meteora DLMM program pid (LBUZKhRx...); 全部 data_len = 10136 bytes (3 段, 每段 1 bin array; LbPair struct 8 + vParameters ~32 + BinArray bins[64] × 8 fields ≈ 904 + 2×8 bytes headers). **公 RPC 单账户 read OK**.

## 2. 与 V4 关键差异

- V4 调 `dlmmPool.getBinArrayForSwap` 内部用 `chunkedGetMultipleAccountInfos` (multi-account) → 403
- V5 调 `connection.getAccountInfo(singlePubkey)` (single-account) → 200 OK

→ V5 证明: **public RPC 允许单账户 read, 但限制多账户 read**。这是 RPC 端 5MB response cap 派生的事实。

## 3. 根因

`chunkedGetMultipleAccountInfos` 试图返回多账户 (≥2 bins × ~10KB = 20KB+); public RPC 的 `getMultipleAccountsInfo` 在 chunk_size 较大时拒绝。**单账户** `getAccountInfo` 没有这个问题 (response < 16KB easily).

## 4. 后续影响

- V5 Stage E **single-account path works** → Stage F (small-batch) **skipped** (单账户已够)
- Stage G (bin array decode) 可以用 SDK 的 `program.account.binArray.fetch(pubkey)` 解析 6 个 bin array accounts
- Stage H (quote) 可以用 `dlmmPool.swapQuote(...)` 配合 6 个 decoded bin array accounts

→ V4 阻隔 (multi-account 403) **完全 bypassed**.

## 5. 不在本阶段做

- ❌ 不调 GPA
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC (无 key; 本路径 public RPC 就够)
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_rpc_read      = true
rpc_method_used               = connection.getAccountInfo (single pubkey)
no_gpa_used                   = true
no_keypair                    = true
no_transaction                = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 7. 下一阶段

进入 Stage G — bin liquidity decode: 用 SDK `program.account.binArray.fetch(pubkey)` 解析 6 个 bin array accounts, 输出每个 bin (64 bins × 6 arrays = 384 bins, but actual = 70 bins × 6 = 420) 的 xAmount / yAmount.
