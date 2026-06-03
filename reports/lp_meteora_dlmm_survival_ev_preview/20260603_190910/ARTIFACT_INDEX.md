# Meteora Survival EV Preview — Artifact Index

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- branch: `feat/supabase-postgres-deployment`
- head_before: `3065d23`

## 1. 本目录 artifact 清单 (11 required + 1 verification)

| # | name | type | phase | purpose |
|---|---|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | md | B | input 审计（14 上游文件） |
| 2 | `input_evidence_audit.json` | json | B | 同上 (json) |
| 3 | `METEORA_PARTIAL_SURVIVAL_SCOPE_CN.md` | md | C | partial scope freeze (X/USDC only) |
| 4 | `meteora_partial_survival_scope.json` | json | C | 同上 (json) |
| 5 | `METEORA_SURVIVAL_EV_INPUTS_CN.md` | md | D | model input build (168 cells) |
| 6 | `meteora_survival_ev_inputs.json` | json | D | 同上 (json) |
| 7 | `METEORA_FEE_CAPTURE_PROXY_CN.md` | md | E | fee capture proxy (126 rows; heuristic) |
| 8 | `meteora_fee_capture_proxy.csv` | csv | E | 同上 (csv) |
| 9 | `meteora_fee_capture_proxy.json` | json | E | 同上 (json) |
| 10 | `METEORA_SOLANA_COST_MODEL_CN.md` | md | F | cost model (3 scenarios) |
| 11 | `meteora_solana_cost_model.csv` | csv | F | 同上 (csv) |
| 12 | `meteora_solana_cost_model.json` | json | F | 同上 (json) |
| 13 | `METEORA_SURVIVAL_EV_PREVIEW_CN.md` | md | G | EV preview (168 cells) |
| 14 | `meteora_survival_ev_preview.csv` | csv | G | 同上 (csv) |
| 15 | `meteora_survival_ev_preview.json` | json | G | 同上 (json) |
| 16 | `METEORA_10_20U_PREFLIGHT_IMPLICATION_CN.md` | md | H | 10/20U preflight answer |
| 17 | `meteora_10_20u_preflight_implication.json` | json | H | 同上 (json) |
| 18 | `METEORA_SURVIVAL_EV_NEXT_STAGE_DECISION_CN.md` | md | I | next-stage decision |
| 19 | `meteora_survival_ev_next_stage_decision.json` | json | I | 同上 (json) |
| 20 | `FINAL_VERDICT.json` | json | Z | 终判 |
| 21 | `ONEPAGE_CN.md` | md | Z | 一页纸 summary |
| 22 | `ARTIFACT_INDEX.md` | md | — | 本文件 |

## 2. 输入文件 (上游 V7 + V4 + V3 + V8 prior)

| source | path |
|---|---|
| V7 final | `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/FINAL_VERDICT.json` |
| V7 6 表 | `.../20260603_150331/METEORA_COMBINED_QUOTE_READINESS_V2_CN.md` + json |
| V7 quote smoke | `.../20260603_150331/METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md` + json |
| V7 bin liq | `.../20260603_150331/METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md` + json |
| V4 pool | `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_POOL_SNAPSHOT_CN.md` + json |
| V4 fee | `.../134202/METEORA_FEE_SNAPSHOT_CN.md` + json |
| V3 quote | `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/meteora_quote_smoke_v3_by_coverage.json` |
| V8 prior | `reports/lp_meteora_dlmm_survival_ev_preview/20260603_153736/FINAL_VERDICT.json` + inputs json |

## 3. 输出 schema 速查

### 3.1 `meteora_fee_capture_proxy.json`

```json
[{
  "pool_address": "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad",
  "hold_window": "15m",
  "fee_scenario": "low|medium|high",
  "notional_usd": 10|20|100|500|1000|2000,
  "base_fee_bps": 1.5,
  "max_fee_bps": 10.0,
  "assumed_volume_turnover_pct": 0.001|0.005|0.02,
  "assumed_volume_usd": number,
  "estimated_fee_capture_usd": number,
  "heuristic": true,
  "confidence": 0.3,
  "invalid_reason": "no actual on-chain volume; scenario-based proxy; mark heuristic"
}]
```

### 3.2 `meteora_solana_cost_model.json`

```json
[{
  "scenario": "low|realistic|conservative",
  "priority_fee_lamports": 1000|10000|100000,
  "per_tx_sol": number,
  "per_tx_usd": number,
  "round_trip_tx_count": 2,
  "round_trip_usd": number,
  "setup_sol": 0.00218928,
  "setup_usd": number,
  "recovery_usd": number,
  "total_cost_usd": number,
  "net_cost_usd": number,
  "sol_price_used": 130.0,
  "heuristic": true,
  "refundable": "partial",
  "applies_to_probe": false,
  "applies_to_scaled_notional": true,
  "confidence": 0.5,
  "invalid_reason": "SOL price heuristic; priority fee heuristic; rent heuristic; mark heuristic"
}]
```

### 3.3 `meteora_survival_ev_preview.json`

```json
[{
  "pool_address": "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad",
  "notional_usd": 10|20|100|500|1000|2000,
  "hold_window": "15m|30m|1h|2h|6h|24h|7d",
  "scenario": "zero_il_lvr|optimistic|realistic|conservative",
  "gross_fee_usd": number,
  "il_lvr_cost_usd": number,
  "total_cost_usd": number,
  "net_ev_usd": number,
  "net_ev_pct": number,
  "confidence": 0.4,
  "heuristic": true,
  "data_source": "V4+V6+V7+V8 heuristic; mark heuristic",
  "scope": "partial_pool2_only",
  "invalid_reason": "no actual volume / no realized IL; scenario-based heuristic"
}]
```

## 4. 关键数字（reproducible）

| metric | value |
|---|---|
| row_count | 168 |
| positive_zero_il_lvr_count | 0 |
| positive_optimistic_count | 0 |
| positive_realistic_count | 0 |
| positive_conservative_count | 0 |
| near_break_even_count (< 0, > -0.5) | 84 |
| best_net_ev_proxy_usd | -0.154 |
| best_net_ev_proxy_pct | -0.0077 |
| best_notional | 2000 |
| best_hold_window | 15m |
| best_scenario | zero_il_lvr |
| recommended_next_stage | LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1 |

## 5. 完整性 & 安全 invariant 速查

| invariant | value |
|---|---|
| scope | partial_pool2_only |
| included_pool_count | 1 |
| excluded_pool_count | 1 |
| can_run_probe_now | false |
| solana_wallet_or_keypair_touched | false |
| transaction_sent | false |
| edge_proven | "no" |
| tiny_canary_allowed | "no" |
| v2_line_count | 992 |
| v2_line_count_unchanged | true |
| v2_modified_by_this_task | false |
| send_hard_disable_still_active | true |
| manual_approval_required | true |

## 6. 复现步骤

```bash
# 1. (optional) re-generate the data-driven artifacts (deterministic)
python3 /tmp/gen_artifacts.py  # writes fee_capture_proxy + cost_model + ev_preview

# 2. validate
uv run --with pytest pytest -q tests/test_lp_meteora_dlmm_survival_ev_preview_v1.py
go test ./cmd/lpbot
```
