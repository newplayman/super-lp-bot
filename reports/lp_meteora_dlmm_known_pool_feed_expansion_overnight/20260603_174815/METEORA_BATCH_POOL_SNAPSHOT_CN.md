# Meteora Batch Pool Snapshot — Stage F

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
decoded                = 16/16
decode_target          = >= 10
status                 = PASS
sdk_used               = @meteora-ag/dlmm@1.9.10
cluster                = mainnet-beta
methods                = DLMM.create + getActiveBin + getFeeInfo
```

## 1. Per-pool summary

| pool | base_fee_bps | max_fee_bps | bin_step | active_bin | token_x | token_y | decode | confidence |
|---|---|---|---|---|---|---|---|---|
| `5BKxfWMb…` | 0.02 | 10 | None | -12248 | `So1111…` | `EPjFWd…` | ✅ | 0.85 |
| `9DiruRpj…` | 1.5 | 10 | None | -238 | `FUAfBo…` | `EPjFWd…` | ✅ | 0.85 |
| `6eR5rRde…` | 2 | 10 | None | -411 | `HfAFNs…` | `So1111…` | ✅ | 0.85 |
| `H9b4sPAe…` | 2.5 | 10 | None | -255 | `Axhcwf…` | `EPjFWd…` | ✅ | 0.85 |
| `6qz7THwQ…` | 0.25 | 10 | None | -1651 | `BPxxfR…` | `EPjFWd…` | ✅ | 0.85 |
| `CnK82s8e…` | 1 | 10 | None | -317 | `FeMbDo…` | `So1111…` | ✅ | 0.85 |
| `9bL8Pptp…` | 1 | 10 | None | -271 | `DnnmrZ…` | `So1111…` | ✅ | 0.85 |
| `8ztFxjFP…` | 0.2 | 10 | None | 173 | `Dz9mQ9…` | `So1111…` | ✅ | 0.85 |
| `2G7fxAhB…` | 2 | 10 | None | -518 | `CPV5ki…` | `So1111…` | ✅ | 0.85 |
| `Cgnuirsk…` | 0.2 | 10 | None | 5 | `5UUH9R…` | `So1111…` | ✅ | 0.85 |
| `FhdW3Y6E…` | 0.2 | 10 | None | -2931 | `3ZLekZ…` | `EPjFWd…` | ✅ | 0.85 |
| `6oFWm7KP…` | 0.05 | 10 | None | -9083 | `DezXAZ…` | `So1111…` | ✅ | 0.85 |
| `BCv5Ggg5…` | 0.1 | 10 | None | -1756 | `SKRbvo…` | `So1111…` | ✅ | 0.85 |
| `6VxKTxaV…` | 2 | 10 | None | -482 | `9gnq7q…` | `So1111…` | ✅ | 0.85 |
| `DJ8qzBm3…` | 1 | 10 | None | -430 | `6SjVTj…` | `So1111…` | ✅ | 0.85 |
| `8UYCgRrx…` | 1 | 10 | None | -263 | `33eum8…` | `So1111…` | ✅ | 0.85 |

## 2. Honest gaps (heuristic-marked)

- `bin_step` 字段在某些 SDK 调用中可能为 null；标记 `invalid_reason` 而不是 0
- `reserve_x_raw` / `reserve_y_raw` 未在此 stage 提取（V1 简化为 null；后续 stage 可加 vault account 读取）
- `volatility_accumulator` SDK v1.9.10 不暴露 (V4 已记录)
- `protocol_fee_bps` SDK v1.9.10 不暴露 (V4 已记录)

## 3. 安全断言

```text
this_stage_only_decode            = true
no_signer                         = true
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
v2_line_count_unchanged           = true
```

## 4. 下一阶段

进入 Stage G — bin array read/decode (5/9/15 arrays; single-account path)。
