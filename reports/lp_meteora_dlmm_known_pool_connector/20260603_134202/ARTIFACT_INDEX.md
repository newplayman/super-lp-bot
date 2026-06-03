# Artifact Index — LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1

- run_id: `20260603_134202`
- report_dir: `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=fa4e5e4; pre-existing dirty files unrelated |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 14 upstream files from V3; V3 findings inherited; V4 objectives defined; full pool addresses from V3 artifact |
| `input_evidence_audit.json` | structured input audit; key_findings; known_pool_feed_full_addresses_from_v3_artifact |

## Stage C — connector script

| artifact | description |
|---|---|
| `scripts/lp_meteora_dlmm_known_pool_connector_v1_readonly.js` | reusable Node.js script; --mode snapshot/quote-smoke/all; --known-pool-feed; --output-dir; --run-id; --rpc-url-redacted-source |

## Stage D — known pool universe

| artifact | description |
|---|---|
| `METEORA_KNOWN_POOL_UNIVERSE_CN.md` | 3 candidates (2 selected + 1 skipped not on mainnet); all from official SDK examples |
| `meteora_known_pool_universe.csv` | per-pool CSV with source / source_file / source_confidence / selected_for_snapshot |
| `meteora_known_pool_universe.json` | structured feed |

## Stage E — pool snapshot

| artifact | description |
|---|---|
| `METEORA_POOL_SNAPSHOT_CN.md` | 2/2 pools full LbPair decode via SDK; real on-chain state |
| `meteora_pool_snapshot.csv` | 2 rows with token mints, decimals, bin_step, active_bin, price, reserves, fees |
| `meteora_pool_snapshot.json` | structured per-pool snapshot |

## Stage F — fee snapshot

| artifact | description |
|---|---|
| `METEORA_FEE_SNAPSHOT_CN.md` | 2/2 pools base + max via SDK getFeeInfo |
| `meteora_fee_snapshot.csv` | 2 rows with base_fee_bps + max_fee_bps + source_method + confidence |
| `meteora_fee_snapshot.json` | structured per-pool fee |

## Stage G — bin liquidity attempt

| artifact | description |
|---|---|
| `METEORA_BIN_LIQUIDITY_SNAPSHOT_CN.md` | 0/2 success; 403 on public RPC; root cause documented |
| `meteora_bin_liquidity_snapshot.csv` | 2 rows with bin_array_attempted=true, bin_array_success=false, blocker documented |
| `meteora_bin_liquidity_snapshot.json` | structured per-pool bin_liquidity attempt |

## Stage H — quote snapshot attempt

| artifact | description |
|---|---|
| `METEORA_QUOTE_SNAPSHOT_CN.md` | 0/4 quote success; depends on bin arrays; same blocker as G |
| `meteora_quote_snapshot.csv` | 4 rows (2 pools × 2 notionals); all blocked; honest |
| `meteora_quote_snapshot.json` | structured per-attempt quote |

## Stage I — connector readiness matrix

| artifact | description |
|---|---|
| `METEORA_CONNECTOR_READINESS_MATRIX_CN.md` | 6 tables judged; 3 ready / 2 blocked_public_rpc / 1 blocked_missing_quote |
| `meteora_connector_readiness_matrix.json` | structured readiness; judgments (connector_readonly_ready, quote_ready, etc.) |

## Stage J — next-stage decision

| artifact | description |
|---|---|
| `METEORA_KNOWN_POOL_CONNECTOR_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT selected |
| `meteora_known_pool_connector_next_stage_decision.json` | structured decision; entry_conditions_for_known_POOL_READONLY_CONNECTOR_V1_now_satisfied; v3_to_v4_improvements |

## Stage K — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; known_pool_connector_built=true; known_pool_count=2; pool_snapshot_success_count=2; fee_snapshot_success_count=2; bin_liquidity_snapshot_success_count=0; quote_snapshot_success_count=0; connector_readonly_ready=true; quote_ready=false; survival_ev_ready=false; needs_paid_rpc=true; needs_known_pool_feed_expansion=false; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage L — tests + safety scan

(pending)

## Stage M — git publish

(pending)

## Source script (added in this round)

| file | purpose |
|---|---|
| `scripts/lp_meteora_dlmm_known_pool_connector_v1_readonly.js` | reusable read-only connector (this round) |
