# Artifact Index — LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1

- run_id: `20260603_153736`
- report_dir: `reports/lp_meteora_dlmm_survival_ev_preview/20260603_153736/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=3c72d3f; pre-existing dirty files unrelated |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 14 upstream files from V7+V4; V7 findings inherited; V8 objectives defined |
| `input_evidence_audit.json` | structured input audit; key_findings; this_stage_objectives; safety_locks_intact |

## Stage C — partial scope freeze

| artifact | description |
|---|---|
| `METEORA_PARTIAL_SURVIVAL_SCOPE_CN.md` | X/USDC included; SOL/USDC excluded with no_quote_data reason; honesty assertions |
| `meteora_partial_survival_scope.json` | structured; included_pools + excluded_pools; data_assets; missing_must_mark |

## Stage D — survival EV model input build

| artifact | description |
|---|---|
| `METEORA_SURVIVAL_EV_INPUTS_CN.md` | 168 cells (6×7×4); per-cell input values; missing data explicitly marked |
| `meteora_survival_ev_inputs.json` | structured; input_assets; model_dimensions; rows_per_cell_inputs; missing_must_mark |

## Stage E — fee capture proxy

| artifact | description |
|---|---|
| `METEORA_FEE_CAPTURE_PROXY_CN.md` | 126 rows; scenario-based; heuristic marked |
| `meteora_fee_capture_proxy.csv` | per-row: notional / hold_window / fee_scenario / assumed_volume / estimated_fee |
| `meteora_fee_capture_proxy.json` | structured |

## Stage F — cost model

| artifact | description |
|---|---|
| `METEORA_SOLANA_COST_MODEL_CN.md` | 3 rows; low/realistic/conservative; SOL_PRICE=$130 heuristic |
| `meteora_solana_cost_model.csv` | per-row: per_tx_sol / per_tx_usd / round_trip_usd / setup_usd / net_cost_usd |
| `meteora_solana_cost_model.json` | structured |

## Stage G — survival EV preview

| artifact | description |
|---|---|
| `METEORA_SURVIVAL_EV_PREVIEW_CN.md` | 168 cells computed; 0/168 positive; honest negative EV reported |
| `meteora_survival_ev_preview.csv` | per-row: notional / hold_window / scenario / gross_fee / il_lvr_cost / total_cost / net_ev / net_ev_pct / heuristic / data_source |
| `meteora_survival_ev_preview.json` | structured (168 rows) |

## Stage H — 10/20U preflight implication

| artifact | description |
|---|---|
| `METEORA_10_20U_PREFLIGHT_IMPLICATION_CN.md` | 6 operator questions answered; X/USDC 10/20U NOT worth; recommended feed expansion |
| `meteora_10_20u_preflight_implication.json` | structured; operator_questions_answered; summary_decision |

## Stage I — next-stage decision

| artifact | description |
|---|---|
| `METEORA_SURVIVAL_EV_NEXT_STAGE_DECISION_CN.md` | LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1 selected |
| `meteora_survival_ev_next_stage_decision.json` | structured; v3_to_v8_6_stage_progression; v8_key_findings; next_stage_responsibilities |

## Stage J — final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; scope=partial_pool2_only; included_pool_count=1; excluded_pool_count=1; survival_ev_model_ran=true; row_count=168; positive_*_count=0 (all scenarios); near_break_even_count=21; best_notional=2000; best_hold_window=15m; best_scenario=zero_il_lvr; best_net_ev_proxy_usd=-0.154; best_net_ev_proxy_pct=-0.0077; x_usdc_preflight_candidate=false; can_run_probe_now=false; solana_wallet_or_keypair_touched=false; transaction_sent=false; edge_proven=no; tiny_canary_allowed=no; recommended_next_stage=LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1 |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage K — tests + safety scan

(pending)

## Stage L — git publish

(pending)
