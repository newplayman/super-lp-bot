# Overnight Final Summary

- repaired_v2_materialization_complete: yes
- report_dir: `reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902`
- repair_version: `v2_rpc_lineage_window`

## Key Results

- 6h/24h invalid_rate before/after: see [VALID_ENTRY_OUTCOME_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/VALID_ENTRY_OUTCOME_CN.md)
- healthy strict-valid count before/after: see [VALID_ENTRY_OUTCOME_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/VALID_ENTRY_OUTCOME_CN.md)
- token_decimals_missing before/after: see [REPAIRED_V2_MATERIALIZATION_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/REPAIRED_V2_MATERIALIZATION_CN.md)
- position_id lineage success rate: see [POSITION_ID_REPAIR_AUDIT_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/POSITION_ID_REPAIR_AUDIT_CN.md)
- target-window sensitivity: see [TARGET_WINDOW_SENSITIVITY_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/TARGET_WINDOW_SENSITIVITY_CN.md)
- pct_signal: see [PNL_REALITY_AUDIT_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/PNL_REALITY_AUDIT_CN.md)
- gate result: see [GATE_CONCLUSION_CN.md](reports/shadow_outcomes/clean_remote_repaired_v2_20260528_0902/GATE_CONCLUSION_CN.md)
- tiny_canary_candidate: no
- tiny_canary_allowed: no

## Priority Blockers

1. 24h strict-valid invalid rate still above the 30% gate after repaired_v2.
2. Mark-window and future-mark gaps remain a dominant invalid bucket.
3. Position lineage is improved but not fully trusted for all strict-valid rows.
4. reality_gate remains blocked until trusted mark/lineage coverage is complete.
