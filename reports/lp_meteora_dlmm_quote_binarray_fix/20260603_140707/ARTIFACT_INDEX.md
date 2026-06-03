# Artifact Index — LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1

- run_id: `20260603_140707`
- report_dir: `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=1c3d8ea; pre-existing dirty files unrelated |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 14 upstream files from V4; V4 findings inherited; V5 objectives defined; full pool addresses from V4 artifact |
| `input_evidence_audit.json` | structured input audit; key_findings; known_pool_feed_full_addresses_from_v4_artifact |

## Stage C — SDK bin array helper audit

| artifact | description |
|---|---|
| `METEORA_BINARRAY_SDK_HELPER_AUDIT_CN.md` | 12 helpers audited; single-account path identified |
| `meteora_binarray_sdk_helper_audit.json` | structured; per-helper exists/requires_gpa/usable_for_single_account_path/notes |

## Stage D — bin array PDA derivation

| artifact | description |
|---|---|
| `METEORA_BINARRAY_PDA_DERIVATION_CN.md` | 6/6 deterministic pubkeys derived via binIdToBinArrayIndex + deriveBinArray (no RPC) |
| `meteora_binarray_pda_derivation.csv` | per-row: pool / active_bin_id / bin_step / bin_array_index / bin_array_pubkey / neighbor_offset / derivation_success |
| `meteora_binarray_pda_derivation.json` | structured |

## Stage E — single-account getAccountInfo smoke

| artifact | description |
|---|---|
| `METEORA_BINARRAY_SINGLE_ACCOUNT_SMOKE_CN.md` | 6/6 success on public RPC; V4 multi-account blocker **BYPASSED** |
| `meteora_binarray_single_account_smoke.csv` | per-row: pool / bin_array_pubkey / neighbor_offset / getAccountInfo_attempted / success / owner / data_len / rpc_error_type |
| `meteora_binarray_single_account_smoke.json` | structured |

## Stage F — small-batch getMultipleAccounts smoke

| artifact | description |
|---|---|
| (no artifact) | Stage F skipped because Stage E had full success |

## Stage G — bin liquidity decode

| artifact | description |
|---|---|
| `METEORA_BIN_LIQUIDITY_DECODE_CN.md` | 420 bins decoded via SDK program.account.binArray.fetch |
| `meteora_bin_liquidity_decode.csv` | per-row: pool / bin_array_pubkey / bin_id / x_amount / y_amount / liquidity_available / decode_success |
| `meteora_bin_liquidity_decode.json` | structured |

## Stage H — quote smoke v2

| artifact | description |
|---|---|
| `METEORA_QUOTE_SMOKE_V2_CN.md` | 2/4 quote success (V1-V4 all 0%); pool 2 10U/20U quotes real; pool 1 blocked on tight bin_step |
| `meteora_quote_smoke_v2.csv` | per-row: pool / notional_usd / token_in / token_out / amount_in_raw / quote_success / amount_out_raw / fee / invalid_reason |
| `meteora_quote_smoke_v2.json` | structured |

## Stage I — paid RPC requirement decision

| artifact | description |
|---|---|
| `METEORA_PAID_RPC_REQUIREMENT_DECISION_CN.md` | paid_rpc_required=partial; single-account path works; extension to 5-7 arrays on public RPC sufficient |
| `meteora_paid_rpc_requirement_decision.json` | structured; v5_evidence_summary; decision; alternative_to_paid_rpc; if_paid_rpc_decision_yes |

## Stage J — next-stage decision

| artifact | description |
|---|---|
| `METEORA_QUOTE_BINARRAY_FIX_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT selected |
| `meteora_quote_binarray_fix_next_stage_decision.json` | structured; v3_to_v5_improvements; next_stage_responsibilities; must_not |

## Stage K — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; binarray_helper_audit_ran=true; binarray_pda_derivation_ran=true; binarray_pda_success_count=6; single_account_smoke_ran=true; single_account_smoke_success_count=6; bin_liquidity_decode_success_count=420; quote_smoke_ran=true; quote_smoke_success_count=2; paid_rpc_required=partial; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage L — tests + safety scan

(pending)

## Stage M — git publish

(pending)

## Source script (added in this round)

| file | purpose |
|---|---|
| `scripts/lp_meteora_dlmm_binarray_single_account_probe_v1_readonly.js` | read-only probe: PDA derivation + single-account getAccountInfo + bin array decode + quote smoke v2 |
