# Meteora DLMM Known Pool Feed — Stage D

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`

## 0. 关键结果

```text
total_pools_considered  = 3 (all from official SDK example files)
mainnet_verified        = 2
skipped_not_mainnet     = 1
selected_for_sdk_smoke  = 2
all_pools_from_official = true
fabricated_pools        = 0
```

## 1. 已知池列表 (3 候选 / 2 mainnet verified / 2 selected)

| pool_address | source | source_file | mainnet_verified | onchain_data_len | selected_for_sdk_smoke | invalid_reason |
|---|---|---|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | official SDK example | `swap_quote.ts` | ✅ | 904 | ✅ | — |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | official SDK example | `fetch_lb_pair_lock_info.ts` | ✅ | 904 | ✅ | — |
| `3W2HKgUa96Z69zzG3LK1g8KdcRAWzAttiLiHfYnKuPw5` | official SDK example | `example.ts` | ❌ | 0 (null) | ❌ | not on mainnet |

## 2. 来源 (3 个官方 SDK example files)

### 2.1 `swap_quote.ts` → `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF`

- **URL**: `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/swap_quote.ts`
- **用途** in example: `DLMM.create(connection, poolAddress, {cluster: "mainnet-beta"})` + `getBinArrayForSwap` + `swapQuote`
- **confidence**: high (Level A; 官方 SDK example)
- **mainnet_verified**: ✅ (V2 re-confirmed + V3 re-confirmed this round)

### 2.2 `fetch_lb_pair_lock_info.ts` → `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad`

- **URL**: `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/fetch_lb_pair_lock_info.ts`
- **用途** in example: `DLMM.create(connection, poolAddress, {cluster: "mainnet-beta"})` + `getLbPairLockInfo`
- **confidence**: high (Level A; 官方 SDK example)
- **mainnet_verified**: ✅ (V3 新加的; 之前未在 V2 报告里)

### 2.3 `example.ts` → `3W2HKgUa96Z69zzG3LK1g8KdcRAWzAttiLiHfYnKuPw5` (skipped)

- **URL**: `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/example.ts`
- **用途** in example: `initializePositionAndAddLiquidityByStrategy` (写; **不**适合 read-only smoke)
- **confidence**: high (Level A source)
- **mainnet_verified**: ❌ (V3 重新检查: getAccountInfo returned null)
- **decision**: skipped (per spec "不得编造 pool" + "mainnet_verified required")

## 3. mainnet 验证 (V3 实测)

每条候选 pool 在 `https://solana.publicnode.com` (V1 verified primary endpoint) 跑 `getAccountInfo`:
- 期望 owner = `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` (Meteora DLMM program)
- 期望 data_len = 904 (LbPair struct)

**结果**:
- `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF`: owner=LBUZKhRxPF... data_len=904 ✓
- `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad`: owner=LBUZKhRxPF... data_len=904 ✓
- `3W2HKgUa96Z69zzG3LK1g8KdcRAWzAttiLiHfYnKuPw5`: getAccountInfo null (not on mainnet)

## 4. 与 V2 的关系

| 项 | V2 | V3 |
|---|---|---|
| smoke pool | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | 同样 (V2 smoke pool 沿用) |
| smoke pool count | 1 (stdlib-only Python 替代) | 2 (V3 用 full SDK on 2 pools) |
| feed 形态 | implicit (V2 smoke only) | explicit (V3 frozen feed CSV/JSON) |
| known-pool feed size | 1 | 2 |

## 5. 不在本阶段做

- ❌ 不编造任何 pool (per spec "不得编造 pool")
- ❌ 不使用 memory-only pool list
- ❌ 不包括没主网验证的 pool (除标记 skipped)
- ❌ 不读 keypair
- ❌ 不构造 transaction

## 6. 安全断言

```text
all_pools_from_official_source    = true
fabricated_pools                  = 0
mainnet_verified_count            = 2
skipped_count                     = 1
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
v2_line_count_unchanged           = true (992)
```

## 7. 下一阶段

进入 Stage E — SDK known-pool read-only smoke: 在 /tmp 隔离 env 用 full TypeScript SDK 跑 `DLMM.create` + `getActiveBin` + `getFeeInfo` + `getBinArrayForSwap` + `getLbPairLockInfo` on 2 个 known pools.
