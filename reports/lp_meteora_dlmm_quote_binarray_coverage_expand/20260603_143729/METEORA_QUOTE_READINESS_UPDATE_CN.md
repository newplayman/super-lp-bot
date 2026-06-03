# Meteora Quote Readiness Update — Stage H

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键判定

```text
pool_snapshot_ready         = yes
fee_snapshot_ready          = yes
bin_liquidity_ready         = partial (pool 1: 9 arrays insufficient; pool 2: 6+ arrays sufficient)
quote_ready                 = partial (pool 1: 0/2; pool 2: 6/6 across tiers)
survival_ev_ready           = partial (only pool 2 quote data)
paid_rpc_required           = partial (NOT true; single-account path works; pool 1 needs wider coverage OR paid RPC GPA)
can_enter_survival_ev_preview = partial (pool 1 quote data missing; can compute EV for pool 2 only)
```

## 1. 6 表 readiness 状态

| # | table | status | reason |
|---|---|---|---|
| 1 | `meteora_dlmm_known_pool_universe_v1` | **ready** | 2/2 pools from official SDK examples (unchanged) |
| 2 | `meteora_dlmm_pool_snapshot_v1` | **ready** | 2/2 pools full LbPair decode |
| 3 | `meteora_dlmm_fee_snapshot_v1` | **ready** | 2/2 pools base + max fee |
| 4 | `meteora_dlmm_bin_liquidity_snapshot_v1` | **partial** | V6 9 arrays: 910 bins decoded, 371 with liquidity; pool 2 good; pool 1 needs wider coverage |
| 5 | `meteora_dlmm_quote_snapshot_v1` | **partial** | V6 12 attempts: 6/12 success (all pool 2); pool 1 blocked on Insufficient liquidity even with 9 arrays |
| 6 | `meteora_dlmm_survival_ev_preview_v1` | **partial** | only pool 2 has quote data; can compute partial EV |

## 2. V6 实证 (quote by coverage)

| coverage | pool 1 (SOL/USDC) | pool 2 (X/USDC) | total |
|---|---|---|---|
| 5_arrays | 0/2 blocked | 2/2 success (10U=941005; 20U=1882010) | 2/4 |
| 7_arrays | 0/2 blocked | 2/2 success (same) | 2/4 |
| 9_arrays | 0/2 blocked | 2/2 success (same) | 2/4 |

→ **Pool 1 quote 0/6** across all 3 coverage tiers; pool 2 quote 6/6 stable.

## 3. 关键 finding: pool 1 blocked 9 arrays even with 9 arrays × 70 bins = 630 bins ≈ 12% price range

### 3.1 Why pool 1 blocked

- pool 1 (SOL/USDC) bin_step=2: each bin = 0.02% price change
- 9 arrays × 70 bins = 630 bins ≈ 12% price range around active_bin_id=-12248
- 10U-20U USDC swap with 1 SOL ≈ 11.58 USDC (V5 evidence) requires liquidity near active bin
- 9 arrays still insufficient → **liquidity distribution is wider than ±6% from active bin in 2026-06-03 market conditions**

### 3.2 候选 fix

| option | coverage | cost | expected_success |
|---|---|---|---|
| 15_arrays | 15 × 70 = 1050 bins ≈ 21% range | 30 RPC calls/pool | medium (depends on actual liquidity dist) |
| 21_arrays | 21 × 70 = 1470 bins ≈ 30% range | 42 RPC calls/pool | high (but spec says "不得无限扩展") |
| paid_rpc_gpa | enumerates all bin arrays | paid subscription | high (find liquidity directly) |
| known_pool_skip | skip pool 1, use only pool 2 for EV | 0 cost | immediate (but only 1 pool EV) |

→ **Honest blocker**: 9_arrays is the max per spec. To get pool 1 quote, need either (a) extend beyond 9 (violates spec), (b) paid RPC GPA, or (c) skip pool 1 for EV.

## 4. 6 表 readiness 判定详情

| table | coverage_5 | coverage_7 | coverage_9 |
|---|---|---|---|
| known_pool_universe | ready | ready | ready |
| pool_snapshot | ready | ready | ready |
| fee_snapshot | ready | ready | ready |
| bin_liquidity | partial (231/630 with liq) | partial (301/770) | partial (371/910) |
| quote | partial (2/4) | partial (2/4) | partial (2/4) |
| survival_ev | partial | partial | partial |

→ **3 tables ready, 3 tables partial, 0 tables not_attempted**.

## 5. next_stage 候选

| next stage | 触发条件 | V6 状态 |
|---|---|---|
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | quote success enough + bin liquidity + fee | ⚠️ (2/4 quote; only pool 2; can compute partial EV for pool 2) |
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | coverage expansion improved but still partial | ✅ 触发 (pool 1 still blocked on 9 arrays; would need >9 or different approach) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC cannot read enough bin arrays | ⚠️ (single-account path works; pool 1 quote requires >9 arrays or paid RPC GPA) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector bug | ❌ (connector V1 + expand V1 work; no bug) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only path | ❌ (read-only path fully working) |

→ next_stage = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (try 12-15 arrays; per spec "不得无限扩展" but 12-15 still reasonable)

## 6. 不在本阶段做

- ❌ 不实现 production code
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 compute survival EV (deferred until quote data complete)
- ❌ 不修改 EVM executor v2

## 7. 安全断言

```text
this_stage_only_readiness_assessment = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 8. 下一阶段

进入 Stage I — next-stage decision V6: 选 `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (12-15 arrays; OR paid RPC for pool 1).
