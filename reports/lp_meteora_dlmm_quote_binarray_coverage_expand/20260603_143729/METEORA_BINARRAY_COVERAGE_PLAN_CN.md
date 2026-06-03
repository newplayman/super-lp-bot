# Meteora Bin Array Coverage Expansion Plan — Stage C

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键设计

```text
expansion_bounded     = true
max_coverage_arrays   = 9
must_checkpoint       = true (per tier)
no_infinite_expansion = true (per spec "不得无限扩展")
```

## 1. 4 个 coverage tier 详解

### 1.1 coverage_3_arrays (V5 baseline; not run this round)

| field | value |
|---|---|
| offsets | [-1, 0, +1] |
| array_count | 3 |
| bin_count_estimated | 210 |
| pool 1 (bin_step=2) range | ≈ 4.2% (3 × 64 × 0.02% = 3.84%) |
| pool 2 (bin_step=100) range | ≈ 19200% |
| expected RPC calls/pool | 3 |
| expected latency | 3s |
| public_rpc_risk | low |
| V5 result | pool 1 blocked, pool 2 success; **2/4** |

### 1.2 coverage_5_arrays (FIRST EXPANSION TARGET; run this round)

| field | value |
|---|---|
| offsets | [-2, -1, 0, +1, +2] |
| array_count | 5 |
| bin_count_estimated | 350 |
| pool 1 range | **≈ 7.0% (5 × 64 × 0.02% = 6.4%)** — should unlock 10U-20U USDC swap |
| pool 2 range | ≈ 32000% |
| expected RPC calls/pool | 5 |
| expected latency | 5s |
| public_rpc_risk | **low** (V5: 6/6 single-account success; no rate limit yet) |
| expected | **4/4** quote success |

### 1.3 coverage_7_arrays (CONDITIONAL; only if 5_arrays insufficient)

| field | value |
|---|---|
| offsets | [-3, -2, -1, 0, +1, +2, +3] |
| array_count | 7 |
| bin_count_estimated | 490 |
| pool 1 range | ≈ 9.8% (7 × 64 × 0.02% = 8.96%) |
| expected RPC calls/pool | 7 |
| expected latency | 7s |
| public_rpc_risk | low-medium (rate limit possible at ~10 req/s sustained on public RPC) |
| expected | 4/4 quote success |

### 1.4 coverage_9_arrays (CONDITIONAL; LAST tier per spec "不得无限扩展")

| field | value |
|---|---|
| offsets | [-4, -3, -2, -1, 0, +1, +2, +3, +4] |
| array_count | 9 |
| bin_count_estimated | 630 |
| pool 1 range | ≈ 12.6% (9 × 64 × 0.02% = 11.52%) |
| expected RPC calls/pool | 9 |
| expected latency | 9s |
| public_rpc_risk | medium (rate limit) |
| expected | 4/4 quote success (or paid RPC if still blocked) |

## 2. 执行顺序 + checkpoint

```
1. coverage_5_arrays (FIRST)
   ↓ if pool 1 quote success → STOP, declare 5_arrays sufficient
2. coverage_7_arrays (only if 5 insufficient)
   ↓ if pool 1 quote success → STOP, declare 7_arrays sufficient
3. coverage_9_arrays (only if 7 insufficient)
   ↓ if pool 1 quote success → STOP, declare 9_arrays sufficient
   ↓ if still blocked → declare insufficient, document paid_rpc_setup candidate
```

## 3. 关键 insight: bin_step 决定 coverage 需求

| pool | bin_step | issue |
|---|---|---|
| pool 1 (SOL/USDC) | 2 | **TIGHT**: each bin = 0.02% price; 3 arrays = 4.2% range; need 5+ arrays for 10U-20U USDC swap |
| pool 2 (X/USDC) | 100 | **WIDE**: each bin = 1% price; 1 array = 64% range; 3 arrays = 192% range; 5+ arrays = overkill but OK |

→ **pool 1 is the bottleneck; pool 2 is trivial** (already works in V5).

## 4. 风险评估

| risk | mitigation |
|---|---|
| Public RPC rate limit at 5+ req/s sustained | V5 evidence: 6/6 single-account success; rate limit threshold likely 10+ req/s |
| 5_arrays still insufficient for pool 1 | Run 7_arrays in same script; 7_arrays covers 9.8% range |
| 9_arrays still insufficient | Document as paid_rpc_setup candidate; this is the spec's "honest blocker" exit |
| SDK swapQuote bin coverage needs >9 arrays | Out of scope; would need paid RPC for GPA-based discovery |

## 5. 边界 (per spec)

- 不得无限扩展: 5 → 7 → 9 is the max
- 每个 tier 必须 checkpoint: if sufficient, stop; if not, expand
- paid_rpc_setup only if 9_arrays fails (NOT before)
- 不 fake quote success if blocked

## 6. 不在本阶段做

- ❌ 不执行任何 RPC (本阶段只 plan design)
- ❌ 不修改 EVM executor v2
- ❌ 不释放 v2 hard-disable

## 7. 安全断言

```text
this_stage_only_plan          = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 8. 下一阶段

进入 Stage D — expanded PDA derivation: 先推 5 arrays (per pool = 10 PDA pubkeys), 试 quote; 不够再扩 7, 9.
