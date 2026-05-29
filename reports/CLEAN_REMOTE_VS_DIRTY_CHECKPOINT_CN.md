# Clean Remote vs Dirty Checkpoint

- dirty checkpoint: `/opt/lpbot/lp-bot-v3/reports/shadow_outcomes/20260528_0814_readonly_audit`
- clean remote snapshot: `/opt/lpbot/lp-bot-v3-origin-check/reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902`
- comparison basis: dirty = `shadow_outcome_labels_repaired`; clean = `shadow_outcome_labels_repaired_v2`

## Gate-level comparison

| Metric | Dirty Checkpoint | Clean Remote repaired_v2 | Delta / Note |
| --- | --- | --- | --- |
| coverage_gate | PASS | PASS | unchanged |
| data_quality_gate | FAIL | PASS | strict-valid invalid rate cleared to 0 in both horizons |
| reality_gate | FAIL | FAIL | improved but still blocked |
| edge_proven | no | no | unchanged |
| tiny_canary_allowed | no | no | unchanged by instruction and failed reality gate |

## Horizon metrics

| Horizon | Metric | Dirty Checkpoint | Clean Remote repaired_v2 | Delta |
| --- | --- | ---: | ---: | ---: |
| 6h | invalid_rate % | 25.495675 | 0.000000 | -25.495675 |
| 24h | invalid_rate % | 59.156152 | 0.000000 | -59.156152 |
| 6h | strict_valid_count | 18611 | 18618 | +7 |
| 24h | strict_valid_count | 17278 | 10178 | -7100 |
| 6h | selected_strict_valid_count | 18611 | 18618 | +7 |
| 24h | selected_strict_valid_count | 17278 | 10178 | -7100 |
| 6h | reality_auditable_count | 13866 | 18618 | +4752 |
| 24h | reality_auditable_count | 7057 | 10178 | +3121 |
| 6h | pct_signal | better | better | unchanged |
| 24h | pct_signal | better | better | unchanged |

## Failure-family comparison

| Failure family | Dirty Checkpoint | Clean Remote repaired_v2 | Note |
| --- | ---: | ---: | --- |
| metadata_trust failures (strict-valid scope) | significant enough to fail repaired v1 research path | 0 | repaired_v2 clears strict-valid metadata trust blockers |
| position_id join failures (strict-valid scope) | concentrated in stale-pool audit | 0 | strict-valid scope cleared, but residual selected-scope gaps remain |
| stale_mark failures (strict-valid scope) | concentrated in WETH/USDC and cbBTC pools | 0 | strict-valid scope cleared, but selected-scope `pool_mark_only` remains dominant |

## Remaining selected-scope blockers in clean remote repaired_v2

| Horizon | invalid_reason_repaired | Samples |
| --- | --- | ---: |
| 6h | mark_window_too_narrow | 5683 |
| 6h | missing_position_id | 84 |
| 24h | mark_window_too_narrow | 14047 |
| 24h | missing_position_id | 84 |

## Interpretation

1. repaired_v2 solved the earlier decimals/metadata trust contamination in the strict-valid scope.
2. `USAD` is no longer the primary blocker. It is materially recovered in repaired_v2 and no longer drives strict-valid invalid rate.
3. The dominant blocker has shifted to mark coverage semantics: `pool_mark_only` / `mark_window_too_narrow`.
4. Position lineage is a secondary blocker now, limited to a small residual set (`missing_position_id`, `missing_strategy_epoch`, `ambiguous_multiple_positions`).
5. 24h strict-valid shrank because repaired_v2 is stricter about future position mark requirements; this is a quality tightening, not a silent regression in scoring.
