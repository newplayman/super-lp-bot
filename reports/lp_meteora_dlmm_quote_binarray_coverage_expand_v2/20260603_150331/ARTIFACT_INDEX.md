# Artifact Index — LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2

- run_id: `20260603_150331`
- report_dir: `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=0729ea8; pre-existing dirty files unrelated |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 10 upstream files from V6; V6 findings inherited; V7 objectives defined |
| `input_evidence_audit.json` | structured input audit; key_findings; known_pool_feed_full_addresses_from_v6_artifact |

## Stage C — 12/15 coverage plan

| artifact | description |
|---|---|
| `METEORA_BINARRAY_COVERAGE_12_15_PLAN_CN.md` | 12/15 arrays plan; max 15 hard rule; auto-checkpoint at 12 |
| `meteora_binarray_coverage_12_15_plan.json` | structured; per-tier details; checkpoint criteria; bin_step analysis |

## Stage D — PDA derivation 12/15

| artifact | description |
|---|---|
| `meteora_binarray_pda_12_15_derivation.csv` | per-row: pool / coverage_arrays / active_bin_id / bin_step / bin_array_index / bin_array_pubkey / neighbor_offset / derivation_success |
| `meteora_binarray_pda_12_15_derivation.json` | structured (32 rows; SOL/USDC 12+15, X/USDC 5) |

## Stage E — single-account read 12/15

| artifact | description |
|---|---|
| `meteora_single_account_read_12_15.csv` | per-row: pool / coverage_arrays / bin_array_pubkey / neighbor_offset / getAccountInfo_success / account_null / owner / data_len / rpc_error_type / latency_ms |
| `meteora_single_account_read_12_15.json` | structured (27 rows) |

## Stage F — bin liquidity decode 12/15

| artifact | description |
|---|---|
| `meteora_bin_liquidity_decode_12_15.csv` | per-row: pool / coverage_arrays / bin_id / x_amount / y_amount / active_bin_distance / liquidity_available / decode_success |
| `meteora_bin_liquidity_decode_12_15.json` | structured (1540 rows) |

## Stage G — SOL/USDC quote smoke v4

| artifact | description |
|---|---|
| `meteora_sol_usdc_quote_smoke_v4.csv` | per-row: pool / coverage_arrays / notional / token_in / token_out / quote_success / amount_out_raw / coverage_sufficient / invalid_reason |
| `meteora_sol_usdc_quote_smoke_v4.json` | structured (4 rows; 0/4 success) |

## Stage H — combined quote readiness v2

| artifact | description |
|---|---|
| `METEORA_COMBINED_QUOTE_READINESS_V2_CN.md` | 6 tables judged; 3 ready / 3 partial; pool 2 ready for partial EV |
| `meteora_combined_quote_readiness_v2.json` | structured; v7_results_summary; judgments; per_spec_hard_rule_15_max |

## Stage I — next-stage decision

| artifact | description |
|---|---|
| `METEORA_COVERAGE_EXPAND_V2_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 selected (partial, pool 2 only) |
| `meteora_coverage_expand_v2_next_stage_decision.json` | structured; selection_rationale; alternative_PAID_RPC |

## Stage J — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; coverage_12_attempted=true; coverage_12_success_count=12; coverage_15_attempted=true; coverage_15_success_count=15; bin_liquidity_decode_success_count=1540; sol_usdc_10u_quote_success=false; sol_usdc_20u_quote_success=false; x_usdc_quote_still_success=true; quote_success_count_total=0; quote_attempt_count_total=4; minimum_coverage_required="≥15_arrays"; can_enter_full_survival_ev_preview=false; can_enter_partial_survival_ev_preview=true; paid_rpc_required=true; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage K — tests + safety scan

(pending)

## Stage L — git publish

(pending)

## Source script (added in this round)

| file | purpose |
|---|---|
| `scripts/lp_meteora_dlmm_binarray_coverage_expand_v2_readonly.js` | read-only probe; 12/15 arrays PDA + read + decode + SOL/USDC quote; auto-checkpoint at 12 |
