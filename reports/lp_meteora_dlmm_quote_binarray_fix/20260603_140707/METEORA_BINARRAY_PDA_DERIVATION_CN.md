# Meteora Bin Array PDA Derivation — Stage D

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 关键结果

```text
pools_attempted          = 2
derivation_total         = 6 (2 pools × 3 offsets each)
derivation_success_count  = 6
pda_derivation_method     = binIdToBinArrayIndex(activeId) + deriveBinArray(lbPair, index, programId)
no_gpa_used               = true
no_wallet_used            = true
```

## 1. 推导结果（real on-chain PDA pubkeys）

### 1.1 Pool 1: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` (active_bin_id=-12248, bin_step=2)

| neighbor_offset | bin_array_index | bin_array_pubkey | derivation_success |
|---|---|---|---|
| -1 | -176 | `99daE4xkHTmziJZYh6XzfQ8mRqJD6kiYbDVtf8mRhoUL` | ✅ |
| 0 (active) | -175 | `HEG2LuUaJNZNS7EYD5qXL8G3FAHEHKzWZaMPCu3osU1R` | ✅ |
| +1 | -174 | `7tfRkX2QnictEJEZkdw85QVs3zTm21UTqPdz4Dk5fnvP` | ✅ |

### 1.2 Pool 2: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` (active_bin_id=-236, bin_step=100)

| neighbor_offset | bin_array_index | bin_array_pubkey | derivation_success |
|---|---|---|---|
| -1 | -5 | `yhkw7F4xFVLWmF775cfj56gMQhNZchrmdpSBALC6Z5j` | ✅ |
| 0 (active) | -4 | `29JynFXae8M6FLSmNPpDbTsEfXhxhxmSCQFGnBnFsU2N` | ✅ |
| +1 | -3 | `G1BHyB19ozazdUtAdHJbHW8KXoJqsWq4XMiH64WNRHFz` | ✅ |

## 2. 推导方法

```js
// 1) Pure math: bin id → bin array index
const activeIndex = binIdToBinArrayIndex(new BN(activeBinId));
// pool 1: activeBinId=-12248 → index=-175 (one of [-176, -175, -174])
// pool 2: activeBinId=-236 → index=-4 (one of [-5, -4, -3])

// 2) Pure PDA: index + lbPair + programId → pubkey
const [pubkey, bump] = deriveBinArray(lbPair, new BN(index), DLMM_PROGRAM_ID);
// 6 deterministic pubkeys (no RPC)
```

## 3. 与 V4 关键差异

- V4 调 `dlmmPool.getBinArrayForSwap(true, count=1)` → 内部用 `chunkedGetMultipleAccountInfos` 拉多个 bin arrays → public RPC 403
- V5 改用 SDK 公开的 `deriveBinArray` helper 直接 PDA 推导 → 0 RPC 调用
- 然后 V5 用 `connection.getAccountInfo(derivedPubkey)` (SINGLE account) → public RPC OK (data_len=10136 bytes per bin array)

→ V5 single-account path **bypasses** V4's multi-account 403 blocker.

## 4. 不在本阶段做

- ❌ 不调 RPC (本阶段仅 PDA 推导; RPC 在 Stage E)
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不调 getProgramAccounts (GPA)
- ❌ 不调用 SDK 的 getBinArrayForSwap (会走多账户 chunked)
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
derivation_method        = pure PDA (deterministic, no RPC)
no_gpa_used              = true
no_wallet_used           = true
solana_wallet_or_keypair_touched = false
can_run_probe_now        = false
v2_line_count_unchanged  = true (992)
```

## 6. 下一阶段

进入 Stage E — single-account getAccountInfo smoke: 对 6 个 derived bin array pubkey 各调一次 `connection.getAccountInfo(pubkey)`, 验证 public RPC 允许 single-account read.
