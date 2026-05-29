# Position Lifecycle Materialization

- research_table = `shadow_position_lifecycle_proof_v1`

- rows_inserted = 68

- source_tables = shadow_outcome_labels_repaired_terminal_v1, terminal_clean_enriched_research_v1, shadow_decision_trace, positions

- materialization_unit = one row per position_id + horizon lifecycle



| horizon | total_rows | future_rows | terminal_rows | invalid_rows |
| --- | --- | --- | --- | --- |
| 6h | 35 | 6 | 26 | 3 |
| 24h | 33 | 1 | 29 | 3 |
