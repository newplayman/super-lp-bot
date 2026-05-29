# Repaired V2 Materialization

- repair_version: `v2_rpc_lineage_window`
- source: `shadow_outcome_labels_repaired` + read-only RPC decimals audit + lineage/mark sensitivity metadata
- target table: `shadow_outcome_labels_repaired_v2`

| Metric | Value |
| --- | ---: |
| rows_inserted | 50760 |
| rows_updated | 1827 |
| total_rows_for_version | 50760 |
| token_decimals_missing_before | 10847 |
| token_decimals_missing_after | 0 |
| usad_recovered_samples | 7873 |
| invalid_rate_24h_before_pct | 59.156152 |
| invalid_rate_24h_after_pct | 0.000000 |
| healthy_strict_valid_24h_before | 17278 |
| healthy_strict_valid_24h_after | 10178 |
| rerunnable_idempotent | yes |

- idempotency: the materialization uses deterministic `id = md5(decision_trace_id:horizon:repair_version)` and `ON CONFLICT DO UPDATE`.
- safety: original `shadow_outcome_labels` and `shadow_outcome_labels_repaired` are untouched.
