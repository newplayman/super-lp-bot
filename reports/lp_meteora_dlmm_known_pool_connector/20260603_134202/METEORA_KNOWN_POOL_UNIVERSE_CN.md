# Meteora Known Pool Universe — Stage D

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键结果

```text
total_pools_considered  = 3 (all from official SDK example files)
selected_for_snapshot   = 2
skipped                 = 1 (not on mainnet)
all_pools_from_official = true
fabricated_pools        = 0
```

## 1. 已知池列表

| pool_address | source | source_file | mainnet_verified | selected_for_snapshot | previous_smoke_status |
|---|---|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | official SDK example | `swap_quote.ts` | ✅ | ✅ | verified_v3 |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | official SDK example | `fetch_lb_pair_lock_info.ts` | ✅ | ✅ | verified_v3 |
| `3W2HKgUa96Z69zzG3LK1g8KdcRAWzAttiLiHfYnKuPw5` | official SDK example | `example.ts` | ❌ | ❌ | skipped_not_on_mainnet |

## 2. 来源（3 个官方 SDK example files）

| 池 | URL | confidence |
|---|---|---|
| pool 1 | `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/swap_quote.ts` | high |
| pool 2 | `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/fetch_lb_pair_lock_info.ts` | high |
| pool 3 (skipped) | `https://raw.githubusercontent.com/MeteoraAg/dlmm-sdk/main/ts-client/src/examples/example.ts` | high |

## 3. mainnet 验证 (V3 + V4 实测)

每条候选 pool 在 `https://solana.publicnode.com` 跑 `getAccountInfo`:
- 期望 owner = `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`
- 期望 data_len = 904

**结果** (V4 re-check via `DLMM.create` SDK):
- pool 1 ✅ (owner + bin_step=2 + token mints + active bin + reserves decoded)
- pool 2 ✅ (owner + bin_step=100 + token mints + active bin + reserves decoded)
- pool 3 (从 V3 已知) ❌ (getAccountInfo returned null)

## 4. 不在本阶段做

- ❌ 不编造任何 pool (per spec "不得新增非官方来源 pool")
- ❌ 不使用 memory-only pool list
- ❌ 不包括没主网验证的 pool (除标记 skipped)
- ❌ 不读 keypair
- ❌ 不构造 transaction

## 5. 安全断言

```text
all_pools_from_official_source    = true
fabricated_pools                  = 0
mainnet_verified_count            = 2
skipped_count                     = 1
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
v2_line_count_unchanged           = true (992)
```

## 6. 下一阶段

进入 Stage E — pool snapshot materialization: 对 2 个 selected pools 用 SDK read-only decode 输出结构化快照.
