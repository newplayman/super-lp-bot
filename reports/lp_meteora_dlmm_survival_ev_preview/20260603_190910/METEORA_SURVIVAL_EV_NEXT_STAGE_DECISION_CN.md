# Meteora Survival EV Next-Stage Decision — Stage I

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. 关键决定

```text
selected_next_stage          = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
recommended_next_stage       = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
default_when_no_explicit     = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
selected_status              = PASS (re-run reproduces V8 prior 20260603_153736)
```

## 1. Allowed next stages (per spec)

| # | stage | candidate? |
|---|---|---|
| 1 | `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` | **YES (selected)** |
| 2 | `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` | NO (negative) |
| 3 | `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | NO (deferrable) |
| 4 | `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_FIX_REPEAT` | NO (model is correct) |
| 5 | `STOP_LP_RESEARCH_NOW` | NO (read-only path still productive) |

## 2. Selection rationale

### 2.1 selected: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`

**POSITIVE.**

The V8 EV preview (re-run as 20260603_190910) reproduces the prior run (20260603_153736, commit 3065d23): X/USDC at 10–2000 USD notionals is structurally negative under all 4 scenarios (zero_il_lvr, optimistic, realistic, conservative). The root cause is **structural**:
- base fee = 1.5% (low for retail-scale LP)
- fixed cost = ~$0.16 per position (rent + tx)
- fee capture at 10–20 USD notional = 5+ orders of magnitude smaller than fixed cost

A different **pool** with a higher base fee (Meteora DLMM supports 5–30% base fees for some pools) or higher measured volume (Meteora UI top-pools list has pools with $1M+ 24h volume) would have a structurally different EV profile. The right next step is to **expand the pool feed** to find such pools.

### 2.2 not selected: `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1`

**NEGATIVE.**

V8 partial EV preview for 10/20U X/USDC shows **all 24 cells (4 scenarios × 6 notionals) negative**, even in the best case (10 USD / 15m / zero_il_lvr = -$0.156). Per spec hard rule: "10/20U X/USDC probe is NOT worth it under V8 EV model". Designing a probe for a known-negative-EV pool is wasted work.

### 2.3 not selected: `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`

**NEGATIVE (deferrable).**

SOL/USDC at 15 arrays (21% range, 1050 bins decoded) has 0 bins with liquidity. Paid RPC + GPA would find where SOL/USDC liquidity actually is. But:
- We don't know the cost-effectiveness.
- X/USDC alone is insufficient for full 2-pool EV; we need at least one positive-EV pool first.
- The known pool feed expansion (option 1) is the more direct path to finding positive EV.

Deferrable until feed expansion is exhausted.

### 2.4 not selected: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_FIX_REPEAT`

**NEGATIVE.**

V8 model is not buggy. Heuristic-marked inputs are explicit. Missing fields are marked `missing` / `heuristic`, not 0. The structural negative EV finding is reproducible across this re-run and the prior run. No fix_repeat needed.

### 2.5 not selected: `STOP_LP_RESEARCH_NOW`

**NEGATIVE.**

Read-only path is fully working:
- 7/8 stages of Solana read-only connector work done (V3–V8)
- 168 EV cells computed and verified
- Single-account path proven linearly scalable
- Pool fee/quote/liquidity snapshots all complete for the included pool

Not a structural failure. Better to expand feed than stop.

## 3. v3 to v8 6-stage progression

| stage | outcome |
|---|---|
| v3_FEASIBILITY | SDK path identified; smoke partial (0/4 quote); readiness matrix designed |
| v4_CONNECTOR_V1 | connector V1 built; pool/fee snapshot 2/2; bin/quote 0/2 / 0/4 (multi-account blocked) |
| v5_BINARRAY_FIX | single-account path PROVEN (6/6; 420 bins; 2/4 quote) |
| v6_COVERAGE_EXPAND | 5/7/9 arrays (33/42 single-account; 2310 bins; 6/12 quote; pool 2 stable 6/6) |
| v7_COVERAGE_EXPAND_V2 | 12/15 arrays (18/27 single-account; 1540 bins; 0/4 SOL/USDC at spec cap) |
| v8_SURVIVAL_EV_PREVIEW | partial X/USDC EV computed; 168 cells; 0 positive; **best -$0.156 (-0.0077%)**; recommended feed expansion |

This re-run (20260603_190910) reproduces V8 prior run (20260603_153736) finding: 168/168 cells negative, best case identical (within $0.001 rounding).

## 4. v8 key findings

- **partial_scope_x_usdc_only**: V8 frozen partial scope: X/USDC included; SOL/USDC excluded with no_quote_data.
- **168_ev_cells_all_negative**: X/USDC EV at 10–2000 USD notionals is structurally negative; even zero_il_lvr scenario with 2000 notional + 15m hold = -$0.154 (-0.0077%).
- **root_cause_low_fee_high_cost**: base_fee_bps=1.5 (low); assumed_volume 0.5% (medium; pessimistic); fixed cost ~$0.16 round-trip + setup; IL/LVR even at 0.1% = $2 on $2000.
- **honest_heuristic_marking**: All 126 fee_capture rows + 3 cost_model rows + 168 EV rows have heuristic=true; missing data marked `missing` not 0.

## 5. Next-stage responsibilities

`LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`:
- expand known pool feed to include 5–10 Meteora DLMM pools from human-curated list (Meteora UI top pools)
- OR expand to other AMM protocols (Raydium CLMM `CAMMCzo5`, Orca Whirlpools `whirLbMi`)
- use public RPC + single-account path (proven) for new pools
- re-run survival EV preview with expanded feed to find pools with positive EV
- do NOT use paid RPC (no key in this round)
- do NOT construct any transaction

## 6. Next stage must NOT (硬边界)

- execute probe on Solana
- send any tx
- load any keypair / private key / seed phrase
- construct signer
- auto bridge / auto swap
- modify EVM executor v2
- release v2 hard-disable
- set `can_run_probe_now` to true
- set `tiny_canary_allowed` to yes
- hard-code any program id from memory
- use paid RPC without operator key
- implement any position creation / addLiquidity / removeLiquidity / closePosition / claimFee / claimReward
- construct any transaction (even no-op)
- fabricate quote / EV / fee data when missing

## 7. This stage did NOT (硬边界)

- implement any production connector
- compute any quote
- load any keypair / private key
- send any transaction
- call any pos-create / tx-builder method
- modify any production table
- modify EVM executor v2

## 8. 安全断言

```text
can_run_probe_now                = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed              = "no"
edge_proven                      = "no"
v2_line_count_unchanged          = true
v2_line_count                    = 992
```

## 9. 下一阶段

进入 next stage — `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` (read-only; public RPC; no probe).
