# Meteora Bin Array Coverage 12/15 Plan — Stage C

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2`
- run_id: `20260603_150331`

## 0. 关键设计

```text
expansion_bounded     = true
max_coverage_arrays   = 15  (per spec "不得超过 15 arrays")
previous_max          = 9 (V6)
priority_pool         = SOL/USDC (bin_step=2, tight; needs widest coverage)
sanity_pool           = X/USDC (bin_step=100, wide; 12+ arrays not needed but won't break)
must_checkpoint_at_12 = true (auto-STOP if 12 achieves 2/2 SOL/USDC quote)
no_infinite_expansion = true (per spec "不得无限扩展")
```

## 1. 2 coverage tier 详解

### 1.1 coverage_12_arrays (FIRST EXPANSION TARGET; run this round)

| field | value |
|---|---|
| offsets | [-6, -5, -4, -3, -2, -1, 0, +1, +2, +3, +4, +5] |
| array_count | 12 |
| bin_count_estimated | 840 |
| pool 1 (SOL/USDC) range | **≈ 16.8% (12 × 64 × 0.02% = 15.36%)** |
| pool 2 (X/USDC) range | ≈ 76800% |
| expected RPC calls/pool | 12 |
| expected latency | 12s |
| public_rpc_risk | low-medium (V6: 33/42 single-account success) |
| expected | **4/4 quote success** |

### 1.2 coverage_15_arrays (CONDITIONAL; LAST tier per spec "max 15")

| field | value |
|---|---|
| offsets | [-7, -6, -5, -4, -3, -2, -1, 0, +1, +2, +3, +4, +5, +6, +7] |
| array_count | 15 |
| bin_count_estimated | 1050 |
| pool 1 range | **≈ 21.0% (15 × 64 × 0.02% = 19.2%)** — last chance for public RPC |
| pool 2 range | ≈ 96000% |
| expected RPC calls/pool | 15 |
| expected latency | 15s |
| public_rpc_risk | medium (15 consecutive reads; rate limit may kick in) |
| expected | 4/4 (or 2/4 if pool 1 still blocked) |

## 2. 执行顺序 + checkpoint

```
1. coverage_12_arrays (FIRST)
   ↓ if pool 1 10U AND 20U quote success → STOP, declare 12_arrays sufficient
2. coverage_15_arrays (only if 12 insufficient)
   ↓ if pool 1 quote success → STOP, declare 15_arrays sufficient
   ↓ if still blocked → STOP, declare insufficient, recommend paid_rpc_setup or pool2-only EV
3. STOP (per spec "max 15; 不得无限扩展")
```

## 3. 关键 insight: SOL/USDC vs X/USDC bin_step 决定 coverage 需求

| pool | bin_step | issue | minimum coverage for 10U-20U USDC swap |
|---|---|---|---|
| pool 1 (SOL/USDC) | **2** | TIGHT: each bin = 0.02% | need 12-15 arrays (16.8-21% range) |
| pool 2 (X/USDC) | **100** | WIDE: each bin = 1% | 3-5 arrays more than enough |

→ **pool 1 是瓶颈; pool 2 是 trivial** (V6: 6/6 quote at 5/7/9 arrays).

## 4. 硬规则 (per spec)

- max 15 arrays (硬规则, 不可扩展)
- if 15 arrays still blocked → STOP, recommend paid_rpc_setup OR pool2-only partial survival EV preview
- 不得无限扩展

## 5. 风险评估

| risk | mitigation |
|---|---|
| Public RPC rate limit at 12+ req/s sustained | V6 evidence: 33/42 single-account success; 12 req ≈ 1-2s; rate limit threshold likely 20+ req/s |
| 12_arrays still insufficient for pool 1 | Run 15_arrays in same script; 15_arrays covers 21% range |
| 15_arrays still insufficient | Document as paid_rpc_setup candidate; per spec hard cap |
| SDK swapQuote bin coverage needs >15 arrays | Out of scope per spec; would need paid RPC for GPA-based discovery |

## 6. 边界 (per spec)

- 不得超过 15 arrays
- 如果 15 arrays 仍失败，必须停止并推荐 paid RPC 或 pool2-only survival EV preview
- 不得无限扩展
- 不 fake quote success if blocked

## 7. 不在本阶段做

- ❌ 不执行任何 RPC (本阶段只 plan design)
- ❌ 不修改 EVM executor v2
- ❌ 不释放 v2 hard-disable

## 8. 安全断言

```text
this_stage_only_plan          = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 9. 下一阶段

进入 Stage D — PDA derivation for 12/15 arrays: 优先对 SOL/USDC pool 推导 12 arrays (5+7+12=24 rows); 若 12 仍 blocked 再 + 3 (15 max); X/USDC 只做 sanity (5 arrays).
