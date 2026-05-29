# shadow_terminal_position_marks_repaired_v1 Materialization

- independent research table only; original tables unchanged
- strict timing audit result: the dominant valid source is an exact_at_exit same-position close mark, not a strict_before_exit or strict_after_exit mark
- 24h: strict_before_exit=0, exact_at_exit=14047, strict_after_exit=0
- 6h: strict_before_exit=0, exact_at_exit=5683, strict_after_exit=0
- rule: nearest same-position mark at_or_before_exit is the terminal candidate
- rule: valid only when at_or_before_exit distance <= 300 seconds
- rule: exit_decision must exist
- rule: exit_action or closed/exited status must exist
- rule: entry source must be trusted
- rule: pool_mark_only is not used

| horizon | terminal_mark_source | count |
| --- | --- | ---: |
| 24h | close_mark | 14047 |
| 6h | close_mark | 5683 |

## Validity Distribution

| horizon | valid_terminal_position_mark | count |
| --- | --- | ---: |
| 24h | false | 1772 |
| 24h | true | 12275 |
| 6h | false | 72 |
| 6h | true | 5611 |

## Invalid Reasons

| horizon | invalid_reason | count |
| --- | --- | ---: |
| 24h | NULL | 12275 |
| 24h | entry_untrusted | 1745 |
| 24h | missing_terminal_value | 27 |
| 6h | NULL | 5611 |
| 6h | entry_untrusted | 45 |
| 6h | missing_terminal_value | 27 |
