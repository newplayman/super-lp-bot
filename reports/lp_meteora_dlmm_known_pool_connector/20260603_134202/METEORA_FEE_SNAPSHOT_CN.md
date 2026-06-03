# Meteora Fee Snapshot — Stage F

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键结果

```text
pools_attempted      = 2
pools_fee_available  = 2 (100%)
source_method        = dlmmPool.getFeeInfo() (synchronous, no extra RPC)
target               = base_fee_bps + max_fee_bps + dynamic_fee_components
```

## 1. Pool 1: `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF`

| field | value | notes |
|---|---|---|
| base_fee_bps | **0.02** | from `dlmmPool.getFeeInfo().baseFeeRatePercentage` |
| max_fee_bps | **10** | from `dlmmPool.getFeeInfo().maxFeeRatePercentage` |
| dynamic_fee_components | (not available) | SDK returns only base+max in this version; volatility_accumulator not exposed via this method |
| fee_info_available | true | — |
| source_method | dlmmPool.getFeeInfo() | — |
| confidence | 0.95 | high (sync call, no RPC) |
| invalid_reason | (none) | — |

## 2. Pool 2: `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad`

| field | value | notes |
|---|---|---|
| base_fee_bps | **1.5** | from `dlmmPool.getFeeInfo().baseFeeRatePercentage` |
| max_fee_bps | **10** | from `dlmmPool.getFeeInfo().maxFeeRatePercentage` |
| dynamic_fee_components | (not available) | same as pool 1 |
| fee_info_available | true | — |
| source_method | dlmmPool.getFeeInfo() | — |
| confidence | 0.95 | high (sync call, no RPC) |
| invalid_reason | (none) | — |

## 3. 缺失字段 (honest gap)

| 字段 | 缺失原因 |
|---|---|
| `protocol_fee_bps` | V3 + V4 SDK `getFeeInfo()` returns `baseFeeRatePercentage` + `maxFeeRatePercentage` only. `protocolFeeBps` field is `undefined` in v1.9.10. Future SDK versions may expose it. **Not blocking connector V1.** |
| `dynamic_fee_components` | SDK doesn't break out variable / volatility components in the high-level method. Need to read `lbPair.vParameters` directly: `volatility_accumulator`, `volatility_reference`, `last_update_timestamp`. Not implemented in V4; can be added in connector V1+. |
| `fee_bps_total` (combined) | Spec asks for "fee" but SDK doesn't return a single combined fee_bps. Use base_fee_bps as canonical "fee" for V1. |

## 4. 与 V3 一致性

V3 fee snapshot 2/2 pools available with same base/max values; V4 connector produces identical values via same SDK method. **无 regression**.

## 5. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不调用 pos-create / tx-builder
- ❌ 不 webfetch
- ❌ 不写 production positions
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
fee_snapshot_read_only     = true
pools_fee_available       = 2/2
solana_wallet_or_keypair_touched = false
transaction_sent          = false
can_run_probe_now         = false
v2_line_count_unchanged   = true (992)
```

## 7. 下一阶段

进入 Stage G — bin liquidity attempt: 用 SDK getBinArrayForSwap 尝试, 预期被 public RPC 403 阻断, 记录 blocker.
