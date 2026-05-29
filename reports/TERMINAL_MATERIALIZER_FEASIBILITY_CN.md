# Terminal Materializer Feasibility

- source repaired table: `shadow_outcome_labels_repaired_terminal_v1`
- source tables checked: `shadow_position_marks`, `shadow_exit_decisions`, `shadow_exit_actions`, `shadow_decision_trace`
- explicit rule: `pool_mark_only` cannot enter proof
- explicit rule: `latest_before_exit_mark` cannot enter proof by default; at most it can be `reconstructed` with downgraded confidence

## Coverage by Candidate Source

| source | horizon | coverage_count | terminal_total | coverage_pct | confidence | proof_eligibility | bias_risk |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| closed_position_mark | 24h | 14047 | 14047 | 100.00% | medium | usable for proof only if explicitly marked closed/exited near exit time | moderate |
| closed_position_mark | 6h | 5683 | 5683 | 100.00% | medium | usable for proof only if explicitly marked closed/exited near exit time | moderate |
| exit_action_row | 24h | 14019 | 14047 | 99.80% | medium | action exists but does not itself prove settled position value | high |
| exit_action_row | 6h | 5655 | 5683 | 99.51% | medium | action exists but does not itself prove settled position value | high |
| exit_decision_row | 24h | 14047 | 14047 | 100.00% | medium | decision exists but does not itself prove settled position value | high |
| exit_decision_row | 6h | 5683 | 5683 | 100.00% | medium | decision exists but does not itself prove settled position value | high |
| latest_same_position_mark_before_exit | 24h | 14047 | 14047 | 100.00% | low | latest-before-exit is reconstructed and should not enter proof by default | high |
| latest_same_position_mark_before_exit | 6h | 5683 | 5683 | 100.00% | low | latest-before-exit is reconstructed and should not enter proof by default | high |
| same_position_mark_after_exit | 24h | 0 | 14047 | 0.00% | low | after-exit mark exists but current repaired table does not source terminal rows from it | high |
| same_position_mark_after_exit | 6h | 0 | 5683 | 0.00% | low | after-exit mark exists but current repaired table does not source terminal rows from it | high |

## Feasibility Judgment

- `closed_position_mark`: potentially usable, but only if the mark can be tied to the same position near exit time and the value fields are explicit.
- `exit_decision_row` and `exit_action_row`: useful for auditability, but insufficient alone to prove settled terminal value.
- `latest_same_position_mark_before_exit`: reconstructable but biased; keep out of strict proof.
- `same_position_mark_after_exit`: existence can support research, but current repaired table does not attribute terminal values to it.
- `pool_mark_only` remains disallowed for proof.
