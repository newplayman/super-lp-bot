# Terminal-Inclusive Residual Audit

- source: `shadow_outcome_labels_repaired_terminal_v1`

## Residual Summary

| Horizon | total selected/intended_open | strict-valid count | non-strict count | non-strict rate % | non-strict selected count | non-strict top20 count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6h | 26275 | 24256 | 2019 | 7.684110 | 2019 | 816 |
| 24h | 24485 | 22480 | 2005 | 8.188687 | 2005 | 813 |

## Non-strict Reason Breakdown

| Horizon | reason | non-strict selected count | non-strict top20 count |
| --- | --- | ---: | ---: |
| 6h | entry_untrusted | 1935 | 419 |
| 6h | pool_mark_only | 84 | 0 |
| 24h | entry_untrusted | 1921 | 405 |
| 24h | pool_mark_only | 84 | 0 |

## Judgment

- residual non-strict 是否影响 proof，关键看 non-strict 是否仍进入 selected/top20。
- 如果 non-strict top20 仍非零，`reality_gate` 仍不能判 PASS。
