# shadow_terminal_position_marks_repaired_v1 Design

This is a research-layer design only. It does not modify any original table.

## Table Purpose

Provide a position-level terminal mark surface that is separate from `shadow_outcome_labels` and separate from `shadow_position_marks`, so strict proof can distinguish:

- audited position exit marks
- audited close marks
- high-confidence reconstructed terminal marks
- invalid terminal rows that must stay out of proof

## Proposed Fields

| field | type | note |
| --- | --- | --- |
| position_id | text | required |
| decision_trace_id | text | required |
| horizon | text | required |
| exit_time | bigint | terminal anchor time |
| exit_reason | text | copied from exit audit path |
| exit_action | text | copied from exit audit path |
| terminal_value_usd | numeric | required for valid rows |
| terminal_fee_usd | numeric | optional |
| terminal_gas_usd | numeric | optional |
| terminal_net_pnl_usd | numeric | required for valid rows |
| terminal_net_pnl_pct | numeric | required for valid rows |
| terminal_mark_source | text | one of `position_exit_mark`, `close_mark`, `high_confidence_reconstructed`, `pool_mark_only`, `only_pre_target_mark`, `missing_terminal_value` |
| terminal_mark_confidence | text | `high`, `medium`, `low`, `none` |
| valid_terminal_position_mark | boolean | strict proof gate |
| invalid_reason | text | populated when invalid |

## Valid Rows

`valid_terminal_position_mark = true` only if `terminal_mark_source` is one of:

- `position_exit_mark`
- `close_mark`
- `high_confidence_reconstructed`

and all of the following are present:

- `position_id`
- `decision_trace_id`
- `exit_time`
- `terminal_value_usd`
- `terminal_net_pnl_usd`
- `terminal_net_pnl_pct`

## Invalid Rows

The following must remain invalid for proof:

- `pool_mark_only`
- `only_pre_target_mark`
- `missing terminal value`

## Research Rule

Even when a row is reconstructed, it should be tagged `high_confidence_reconstructed` only when distance to exit is very small and the lineage from exit decision/action to the same position is explicit.
