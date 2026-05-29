# Tier C Sample Gap Audit

- proof_unit: position_lifecycle
- focus: why Tier C candidate pools have zero position_lifecycle samples

## Findings

- All 4 shadow-OOS-allowed Tier C pools were scanned into `shadow_decision_trace`.
- None were ever selected into the shadow candidate set.
- None produced `intent_open=true`.
- None produced `open_shadow_position` or `reuse_shadow_position`.
- Therefore the gap is upstream of lifecycle collection: the pools are visible, but never enter the shadow open path.

## Gap Classification

- entered_shadow_universe: yes
- entered_scanner_candidate_set: no as selected shadow candidates
- blocked_by_risk_gate: no direct evidence; the pools never reached selected/intended-open stage
- no_entry_signal: yes
- lifecycle_collector_missing_coverage: no evidence; there are no position ids to collect

## Per-Pool Evidence

| pool_id | verdict | trace_count | selected_count | intent_open_count | open_or_reuse_count | last_score | max_score | latest_stage | latest_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830 | MICRO_CANDIDATE | 7277 | 0 | 0 | 0 | 35.9554 | 48.5629 | candidate_filtered | not ranked in top 4 candidates for this tick |
| 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | WATCH | 925 | 0 | 0 | 0 | 39.0357 | 44.4467 | candidate_filtered | not ranked in top 4 candidates for this tick |
| 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa | WATCH | 519 | 0 | 0 | 0 | 32.9057 | 32.9057 | candidate_filtered | not ranked in top 4 candidates for this tick |
| 0x82dbe18346a8656dbb5e76f74bf3ae279cc16b29 | WATCH | 6714 | 0 | 0 | 0 | 44.1710 | 51.1203 | candidate_filtered | not ranked in top 4 candidates for this tick |

## Interpretation

- The current shadow pipeline is score-ranked and only evaluates a limited top candidate slice each tick.
- These Tier C pools are present in the raw shadow universe, but they stay below the current shadow selection cutoff and below the 60-point shadow open threshold.
- Because `selected=false`, `intent_open=false`, and `final_action=skip`, no Tier C position_lifecycle rows can be created.
- REJECT pools are excluded by research policy and should not be tracked for sample accumulation.

## Read-Only Sample Accumulation Plan

- Track only MICRO_CANDIDATE + WATCH pools.
- Exclude REJECT pools from sample accumulation.
- horizons: 15m / 30m / 1h / 2h / 6h
- proof unit: position_lifecycle
- required evidence before any Tier C tail assessment: at least one Tier C candidate pool must generate shadow positions, marks, and exit decisions.
- until then, reports stay in SAMPLE_INSUFFICIENT state.
