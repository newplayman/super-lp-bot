# Input Evidence Audit — Stage B

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- branch: `feat/supabase-postgres-deployment`
- head_before: `3065d23`

## 0. 审计结论

```text
previous_stage               = LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2
previous_status              = WARN
previous_run_id              = 20260603_150331
previous_commit              = 3c72d3f
recommended_next_stage_prev  = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
can_enter_full_survival_ev_preview   = false
can_enter_partial_survival_ev_preview = true
x_usdc_quote_still_success   = true
sol_usdc_quote_success       = false
minimum_coverage_required    = ">=15_arrays (per spec 'max 15; 不得无限扩展'; pool 1 still blocked at 15)"
can_run_probe_now            = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed          = "no"
v2_line_count_unchanged      = true
```

本审计覆盖 14 个上游输入文件（V7 + V4 + V3 复用）以及 1 个本轮复用的 prior survival EV preview（20260603_153736，commit 3065d23）。所有文件均存在；无 missing file。Missing **data**（volume / realized IL / realized slippage / 实际 priority fee / 实际 rent）将在 Stage D 显式标记 `missing` / `heuristic`，**不填充 0**。

## 1. 上游文件审计 (14 files, all present)

### 1.1 来自 V7 (`lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331`)

| # | file | 用途 | 状态 |
|---|---|---|---|
| 1 | `FINAL_VERDICT.json` | V7 终判：partial EV allowed; pool1 blocked at 15 | OK |
| 2 | `ONEPAGE_CN.md` | V7 摘要 | OK |
| 3 | `METEORA_COMBINED_QUOTE_READINESS_V2_CN.md` | 6 表 readiness 判定 | OK |
| 4 | `meteora_combined_quote_readiness_v2.json` | 同上 (json) | OK |
| 5 | `METEORA_QUOTE_READINESS_UPDATE_CN.md` | quote readiness 详细 | OK |
| 6 | `meteora_quote_readiness_update.json` | 同上 (json) | OK |
| 7 | `METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md` | 12 quote 详细 | OK |
| 8 | `meteora_quote_smoke_v3_by_coverage.json` | 12 quote (json) | OK |
| 9 | `METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md` | 12/15 arrays 1540 bins 详细 | OK |
| 10 | `meteora_expanded_bin_liquidity_decode.json` | 12/15 arrays 1540 bins (json) | OK |

### 1.2 来自 V4 (`lp_meteora_dlmm_known_pool_connector/20260603_134202`)

| # | file | 用途 | 状态 |
|---|---|---|---|
| 11 | `METEORA_POOL_SNAPSHOT_CN.md` | 2/2 LbPair decode | OK |
| 12 | `meteora_pool_snapshot.json` | bin_step / active_bin / reserves | OK |
| 13 | `METEORA_FEE_SNAPSHOT_CN.md` | 2/2 base/max fee | OK |
| 14 | `meteora_fee_snapshot.json` | base=0.02/1.5, max=10 | OK |

### 1.3 来自 V3 (`lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729`)

| # | file | 用途 | 状态 |
|---|---|---|---|
| 15 | `meteora_quote_smoke_v3_by_coverage.json` | V6 12 quote (复用) | OK |

### 1.4 来自 V8 (prior survival EV preview, commit 3065d23, RUN 20260603_153736)

| # | file | 用途 | 状态 |
|---|---|---|---|
| 16 | `FINAL_VERDICT.json` | V8 复判：168 cells, 0 positive | OK |
| 17 | `meteora_survival_ev_inputs.json` | input schema 复用 | OK |

## 2. Missing DATA (not files; per spec: mark 'missing' not 0)

- actual on-chain trading volume (we have not measured; per spec mark `missing` not 0)
- actual realized IL/LVR (we have not measured; mark `missing`)
- actual realized slippage (V6 quote has price_impact empty; mark `missing`)
- real token USDC supply (we use reserve_y_raw as proxy; mark `proxy`)
- actual Solana priority fee (per scenario proxy 1k/10k/100k microlamports)
- actual rent (per scenario proxy 0.00218928 SOL including token + position account)

## 3. Key V7 finding carried into this stage

- V7 hit spec hard cap of 15 arrays. Pool 1 (SOL/USDC) quote still blocked. Per spec: 'if 15 arrays 仍失败, 必须停止并推荐 paid RPC 或 pool2-only survival EV preview; 不得无限扩展'. V7 enforces this; this stage accepts partial scope (X/USDC only).
- V6 evidence: X/USDC quote 6/6 stable at 5/7/9 arrays (10U=941005 raw X; 20U=1882010 raw X). Reused unchanged in this stage.
- V6 evidence: X/USDC bin liquidity 231/280 bins with liquidity at 5_arrays. Reused unchanged.
- V4 evidence: base_fee_bps=1.5, max_fee_bps=10 for X/USDC. Reused unchanged.

## 4. This stage objectives

- freeze partial scope (X/USDC included; SOL/USDC excluded with no_quote_data)
- build survival EV model input (6 notionals × 7 hold_windows × 4 scenarios = 168 cells for X/USDC)
- construct scenario-based fee capture proxy (heuristic marked)
- construct Solana cost model (tx fee + rent + position cost; 3 scenarios)
- compute survival EV preview honestly (no fake success; mark missing data)
- answer 10/20U preflight implication (no probe)
- decide next stage (one of 5 allowed)

## 5. This stage does NOT (硬边界)

- compute EV for SOL/USDC (no_quote_data)
- represent partial EV as full EV
- load any keypair / private key / seed phrase / wallet adapter
- construct any transaction
- call sendTransaction or any signing method
- swap / open LP / close LP / collect fee / bridge
- start live/canary/paper
- write production positions
- overwrite shadow tables
- modify EVM executor v2
- release v2 hard-disable
- set `can_run_probe_now` to true
- set `tiny_canary_allowed` to yes
- hard-code any program id from model memory
- fill missing data with zero (per spec: must mark `missing`)

## 6. Safety locks intact

```text
can_run_probe_now                  = false
execution_allowed_now              = false
transaction_sent                   = false
wallet_or_tx_touched               = false
solana_wallet_or_keypair_touched   = false
tiny_canary_allowed                = "no"
edge_proven                        = "no"
manual_approval_required           = true
send_hard_disable_still_active     = true
v2_modified_by_this_task           = false
v2_line_count_unchanged            = true
```

## 7. 下一阶段

进入 Stage C — partial scope freeze (X/USDC only; SOL/USDC no_quote_data).
