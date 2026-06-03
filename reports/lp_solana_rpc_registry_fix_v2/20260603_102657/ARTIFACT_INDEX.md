# Artifact Index — LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2

- run_id: `20260603_102657`
- report_dir: `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/`

## Stage A — workspace safety

| artifact | description |
|---|---|
| (no artifact file) | git fetch + branch + status + log; HEAD=2ca2ab6; pre-existing dirty files unrelated to this task |

## Stage B — input evidence audit

| artifact | description |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 14 upstream files audited; V1 findings inherited; V2 objectives defined |
| `input_evidence_audit.json` | structured input audit; key_findings; this_stage_objectives; safety_locks_intact |

## Stage C — Meteora DLMM SDK / API source discovery

| artifact | description |
|---|---|
| `METEORA_DLMM_SDK_API_SOURCE_DISCOVERY_CN.md` | npm `@meteora-ag/dlmm` v1.9.10; github MeteoraAg/dlmm-sdk; API dlmm-api.meteora.ag 404 on all paths |
| `meteora_dlmm_sdk_api_source_discovery.json` | structured; 6 sources verified (SDK package, DLMM class, getLbPairs, DLMM.create, swapQuote example, lock_info example), 1 unknown (API) |

## Stage D — Meteora DLMM read-only discovery path decision

| artifact | description |
|---|---|
| `METEORA_DLMM_READONLY_DISCOVERY_PATH_DECISION_CN.md` | 3 paths evaluated: public_rpc_gpa (not feasible), paid_rpc_gpa (recommended, needs operator key), official_sdk_api (partial, decode only) |
| `meteora_dlmm_readonly_discovery_path_decision.json` | structured; selected_path=paid_rpc_gpa; fallback=official_sdk_api; connector_ready_if_path_available=false (still needs paid RPC key) |

## Stage E — Meteora DLMM minimal read-only smoke

| artifact | description |
|---|---|
| `METEORA_DLMM_MINIMAL_READONLY_SMOKE_CN.md` | known-pool read path verified (pool 5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF; owner=Meteora DLMM; data_len=904; latency=199ms); struct fields need full SDK |
| `meteora_dlmm_minimal_readonly_smoke.json` | structured; smoke_success=true (partial); discovery_path_used=known_pool; struct_fields_extracted=false |
| `meteora_dlmm_minimal_readonly_smoke.csv` | per-field table |

## Stage F — Raydium CPMM mainnet pid fix

| artifact | description |
|---|---|
| `RAYDIUM_CPMM_MAINNET_PID_FIX_CN.md` | V2 re-verified: cp-swap declare_id pid not on mainnet (V1) AND not on devnet (V2 new); devnet pid also null; both pids null on both networks |
| `raydium_cpmm_mainnet_pid_fix.json` | structured; verified=false; status=deferred; alternative_sources_probed (raydium-amm-v3=CLMM, raydium-sdk-v2=no hardcode, README=no pid, official docs=no pid) |

## Stage G — Lifinity pid decision

| artifact | description |
|---|---|
| `LIFINITY_PID_DECISION_CN.md` | V2 re-probed: docs.lifinity.io 200 but SPA; all 9 subpaths 404; base58 43-44 char matches 0; lifinity github org has 5 repos but ALL non-DEX; all third-party lifinity forks unverifiable |
| `lifinity_pid_decision.json` | structured; status=deferred; reason=official_source_unavailable; does_not_block_p0_p1=true |

## Stage H — Registry v3

| artifact | description |
|---|---|
| `SOLANA_PROGRAM_ID_REGISTRY_V3_CN.md` | merged V1 + V2; Meteora DLMM Q4 upgraded partial→yes; Meteora DLMM Q5 partial; Raydium CPMM unchanged; Lifinity unknown→deferred |
| `solana_program_id_registry_v3.csv` | 6-protocol table with v1→v2 delta |
| `solana_program_id_registry_v3.json` | structured registry v3 |

## Stage I — Next-stage decision

| artifact | description |
|---|---|
| `SOLANA_RPC_REGISTRY_FIX_V2_NEXT_STAGE_DECISION_CN.md` | 5 options evaluated; selected LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT |
| `solana_rpc_registry_fix_v2_next_stage_decision.json` | structured decision; selection_rationale; remaining_blockers; next_stage_responsibilities |

## Stage J — Final verdict

| artifact | description |
|---|---|
| `FINAL_VERDICT.json` | status=WARN; meteora_dlmm_sdk_api_source_discovery_ran=true; meteora_dlmm_discovery_path_decided=true; meteora_dlmm_minimal_smoke_ran=true; meteora_dlmm_minimal_smoke_success=true (partial); raydium_cpmm_pid_fixed=false; lifinity_status=deferred; recommended_next_stage=LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT |
| `ONEPAGE_CN.md` | one-page summary |
| `ARTIFACT_INDEX.md` | this file |

## Stage K — tests + safety scan

(pending — will be in `tests/test_lp_solana_rpc_registry_fix_repeat_v2.py` and report by stage L)

## Stage L — git publish

(pending)
