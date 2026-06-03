# Artifact Index — LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1

- run_id: `20260603_130532`
- report_dir: `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=4099b13; pre-existing dirty files unrelated to this task |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 11 upstream files audited; V2 findings inherited; V3 objectives defined |
| `input_evidence_audit.json` | structured input audit; key_findings; this_stage_objectives; safety_locks_intact |

## Stage C — isolated SDK env audit

| artifact | description |
|---|---|
| `METEORA_DLMM_SDK_PACKAGE_AUDIT_CN.md` | npm view + install @meteora-ag/dlmm@1.9.10 in /tmp; 152 packages; repo root untouched; no wallet-adapter dep |
| `meteora_dlmm_sdk_package_audit.json` | structured audit; has_dlmm_create/get_active_bin/swap_quote/get_fee_info/bin_array_helpers all=true; wallet_related_imports_used=false |

## Stage D — known-pool feed freeze

| artifact | description |
|---|---|
| `METEORA_DLMM_KNOWN_POOL_FEED_CN.md` | 3 candidate pools (all from official SDK examples); 2 mainnet_verified; 1 skipped (3W2HKgUa not on mainnet) |
| `meteora_dlmm_known_pool_feed.csv` | per-pool CSV with source / source_url / source_confidence / onchain_data_len / selected_for_sdk_smoke |
| `meteora_dlmm_known_pool_feed.json` | structured feed; policy fields; mainnet_verified method |

## Stage E — SDK known-pool read-only smoke

| artifact | description |
|---|---|
| `METEORA_DLMM_SDK_KNOWN_POOL_SMOKE_CN.md` | 2/2 pools full LbPair decode via @meteora-ag/dlmm@1.9.10; real on-chain state for SOL/USDC + X/USDC |
| `meteora_dlmm_sdk_known_pool_smoke.json` | structured smoke results; smoke_success=true; bin_array + lock_info blocked (403/410) |

## Stage F — SDK quote smoke (read-only)

| artifact | description |
|---|---|
| `METEORA_DLMM_SDK_QUOTE_SMOKE_CN.md` | 0/4 quote success; root cause = getBinArrayForSwap 403/410 on public RPC; swapQuote SDK is wired |
| `meteora_dlmm_sdk_quote_smoke.json` | structured quote results; 4/4 blocked at getBinArrayForSwap |
| `meteora_dlmm_sdk_quote_smoke.csv` | per-attempt CSV |

## Stage G — known-pool connector schema v1

| artifact | description |
|---|---|
| `METEORA_DLMM_KNOWN_POOL_CONNECTOR_SCHEMA_CN.md` | 6 tables design; 14/14 field coverage; data_confidence honest |
| `meteora_dlmm_known_pool_connector_schema.json` | structured schema; per-table fields + types + fk + notes; v3_known_works + v3_known_blockers |

## Stage H — paid RPC vs known-pool feed decision

| artifact | description |
|---|---|
| `METEORA_DLMM_DISCOVERY_STRATEGY_DECISION_CN.md` | 3 paths evaluated; known_pool_feed_sdk_decode selected for Phase 2A; paid_rpc_gpa for Phase 2B |
| `meteora_dlmm_discovery_strategy_decision.json` | structured decision; alternative_decision; phase_2A_responsibilities; phase_2B_responsibilities |

## Stage I — next-stage decision

| artifact | description |
|---|---|
| `METEORA_DLMM_SDK_FEASIBILITY_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 selected |
| `meteora_dlmm_sdk_feasibility_next_stage_decision.json` | structured decision; entry_conditions_for_KNOWN_POOL_READONLY_CONNECTOR_V1; v2_to_v3 improvements |

## Stage J — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; sdk_package_audit_ran=true; sdk_install_or_pack_success=true; known_pool_feed_ready=true; known_pool_smoke_ran=true; known_pool_smoke_success=true; quote_smoke_ran=true; quote_smoke_success=false; connector_schema_ready=true; recommended_near_term_path=known_pool_feed_sdk_decode; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage K — tests + safety scan

(pending — will be in `tests/test_lp_meteora_dlmm_sdk_connector_feasibility_v1.py` and report by stage L)

## Stage L — git publish

(pending)

## Source scripts (added in this round)

| file | purpose |
|---|---|
| `scripts/lp_meteora_dlmm_sdk_known_pool_smoke_v1_readonly.js` | SDK known-pool read-only smoke (DLMM.create + getActiveBin + getFeeInfo + getBinArrayForSwap + getLbPairLockInfo) |
| `scripts/lp_meteora_dlmm_sdk_quote_smoke_v1_readonly.js` | SDK quote smoke (swapQuote via binArrays; honest failure on public RPC) |
