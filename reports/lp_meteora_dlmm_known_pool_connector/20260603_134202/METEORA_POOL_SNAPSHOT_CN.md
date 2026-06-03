# Meteora Pool Snapshot — Stage E

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键结果

```text
pools_attempted         = 2
pools_decode_success    = 2 (100%)
pools_decode_failed     = 0
sdk_used                = @meteora-ag/dlmm@1.9.10
cluster                 = mainnet-beta
rpc_redacted_source     = <redacted_public_mainnet_beta_solana_com>
method                  = DLMM.create + helpers (read-only)
target_pool_snapshot_success_count = 2 (MET)
```

## 1. Pool 1: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF`

| field | value | type |
|---|---|---|
| token_x_mint | `So11111111111111111111111111111111111111112` | pubkey (Wrapped SOL) |
| token_y_mint | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | pubkey (USDC) |
| token_x_decimals | 9 | u8 |
| token_y_decimals | 6 | u8 |
| bin_step | 2 | u16 |
| active_bin_id | -12248 | i32 |
| active_price | 0.086349257542837731428 | decimal string (1 SOL ≈ 11.58 USDC) |
| reserve_x_raw | 49468352994 | u64 (raw lamports) |
| reserve_y_raw | 1064410439 | u64 (raw micro-USDC) |
| base_fee_bps | 0.02 | % |
| max_fee_bps | 10 | % |
| protocol_fee_bps | (not exposed by SDK getFeeInfo) | — |
| volatility_accumulator | (not extracted this round) | — |
| data_len | (not exposed by SDK at lbPair level) | — |
| owner_program | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | pubkey (= Meteora DLMM program) |
| sdk_decode_success | true | — |
| confidence | 0.9 | — |
| invalid_reason | (none) | — |

## 2. Pool 2: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad`

| field | value | type |
|---|---|---|
| token_x_mint | `FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P` | pubkey (6-dec token; identity not in our scope) |
| token_y_mint | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | pubkey (USDC) |
| token_x_decimals | 6 | u8 |
| token_y_decimals | 6 | u8 |
| bin_step | 100 | u16 |
| active_bin_id | -236 | i32 |
| active_price | 0.095533521620978319249 | decimal string (1 X ≈ 0.0955 USDC) |
| reserve_x_raw | 101593140348172 | u64 |
| reserve_y_raw | 2200122802740 | u64 |
| base_fee_bps | 1.5 | % |
| max_fee_bps | 10 | % |
| protocol_fee_bps | (not exposed by SDK getFeeInfo) | — |
| volatility_accumulator | (not extracted this round) | — |
| data_len | (not exposed by SDK at lbPair level) | — |
| owner_program | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | pubkey (= Meteora DLMM program) |
| sdk_decode_success | true | — |
| confidence | 0.9 | — |
| invalid_reason | (none) | — |

## 3. 缺失字段 (honest gap)

| 字段 | 缺失原因 | 后续 stage 处理 |
|---|---|---|
| `protocol_fee_bps` | V4 SDK `getFeeInfo()` returns `baseFeeRatePercentage` + `maxFeeRatePercentage` only; `protocolFeeBps` returned undefined in V3 + V4 (SDK bug or schema difference) | Stage F 标记为 (not exposed) |
| `volatility_accumulator` | V4 SDK reads `lbPair.vParameters.volatilityAccumulator` but value is u32, may not be exposed; needs `lbPair.vParameters` direct field access | Stage F 可重读 (low priority) |
| `data_len` | SDK doesn't expose raw data buffer at `lbPair` level; data_len verified in V2 (904 bytes via raw RPC) | N/A (already verified) |

## 4. 与 V3 一致性

V3 已知 pool smoke 2/2 full LbPair decode, V4 re-run 通过 connector 同样 2/2 success。**无新发现**, **无 regression**.

## 5. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不调用 pos-create / tx-builder
- ❌ 不 webfetch
- ❌ 不写 production positions
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
pool_snapshot_read_only   = true
pools_decode_success      = 2/2
solana_wallet_or_keypair_touched = false
transaction_sent          = false
can_run_probe_now         = false
v2_line_count_unchanged   = true (992)
```

## 7. 下一阶段

进入 Stage F — fee snapshot materialization (用 SDK getFeeInfo 抽 2/2 pools base/max fee).
