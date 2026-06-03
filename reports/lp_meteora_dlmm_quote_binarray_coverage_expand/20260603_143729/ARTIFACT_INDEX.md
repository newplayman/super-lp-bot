# Artifact Index — LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1

- run_id: `20260603_143729`
- report_dir: `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=202de5b; pre-existing dirty files unrelated |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 10 upstream files from V5; V5 findings inherited; V6 objectives defined; full pool addresses from V5 artifact |
| `input_evidence_audit.json` | structured input audit; key_findings; known_pool_feed_full_addresses_from_v5_artifact |

## Stage C — coverage expansion plan

| artifact | description |
|---|---|
| `METEORA_BINARRAY_COVERAGE_PLAN_CN.md` | 3/5/7/9 arrays tier design; cost + risk estimates; auto-checkpoint rules |
| `meteora_binarray_coverage_plan.json` | structured; per-tier details; checkpoint criteria; bin_step analysis |

## Stage D — expanded PDA derivation

| artifact | description |
|---|---|
| `METEORA_EXPANDED_BINARRAY_PDA_DERIVATION_CN.md` | 42/42 deterministic pubkeys (2 pools × 3 tiers × 5-9 offsets) |
| `meteora_expanded_binarray_pda_derivation.csv` | per-row: pool / coverage_arrays / active_bin_id / bin_step / bin_array_index / bin_array_pubkey / neighbor_offset / derivation_success |
| `meteora_expanded_binarray_pda_derivation.json` | structured |

## Stage E — expanded single-account read

| artifact | description |
|---|---|
| `METEORA_EXPANDED_SINGLE_ACCOUNT_READ_CN.md` | 33/42 success on public RPC; 0 403, 0 410; 9 account_null (un-initialized bin arrays) |
| `meteora_expanded_single_account_read.csv` | per-row: pool / coverage_arrays / bin_array_pubkey / neighbor_offset / getAccountInfo_success / owner / data_len / rpc_error_type |
| `meteora_expanded_single_account_read.json` | structured |

## Stage F — expanded bin liquidity decode

| artifact | description |
|---|---|
| `METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md` | 2310 bins decoded; 731 with liquidity; per-coverage breakdown |
| `meteora_expanded_bin_liquidity_decode.csv` | per-row: pool / coverage_arrays / bin_id / x_amount / y_amount / active_bin_distance / liquidity_available / decode_success |
| `meteora_expanded_bin_liquidity_decode.json` | structured (large file) |

## Stage G — quote smoke v3 by coverage

| artifact | description |
|---|---|
| `METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md` | 6/12 quote success; pool 2 6/6 stable; pool 1 0/6 blocked at all tiers |
| `meteora_quote_smoke_v3_by_coverage.csv` | per-row: pool / coverage_arrays / notional / token_in / token_out / quote_success / amount_out_raw / coverage_sufficient |
| `meteora_quote_smoke_v3_by_coverage.json` | structured |

## Stage H — quote readiness update

| artifact | description |
|---|---|
| `METEORA_QUOTE_READINESS_UPDATE_CN.md` | 6 tables judged: 3 ready / 3 partial; pool 1 quote still blocked on tight bin_step + 9 arrays insufficient |
| `meteora_quote_readiness_update.json` | structured; v6_results_summary by tier; minimum_coverage_required_by_pool; can_enter_survival_ev_preview=partial |

## Stage I — next-stage decision

| artifact | description |
|---|---|
| `METEORA_COVERAGE_EXPAND_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT selected; try 12-15 arrays next |
| `meteora_coverage_expand_next_stage_decision.json` | structured; v5_to_v6_quote_progress; v6_key_findings; next_stage_responsibilities |

## Stage J — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; coverage_plan_ready=true; expanded_pda_success_count=42; expanded_single_account_success_count=33; expanded_bin_liquidity_decode_success_count=2310; quote_smoke_success_count=6; sol_usdc_quote_success=false; x_usdc_quote_success=true; minimum_coverage_required=≥9_arrays; paid_rpc_required=partial; can_enter_survival_ev_preview=partial; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage K — tests + safety scan

(pending)

## Stage L — git publish

(pending)

## Source script (added in this round)

| file | purpose |
|---|---|
| `scripts/lp_meteora_dlmm_binarray_coverage_expand_v1_readonly.js` | read-only coverage expansion probe (5/7/9 arrays); PDA + read + decode + quote; auto-checkpoint |
