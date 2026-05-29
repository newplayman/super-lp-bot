# Decision Trace Duplication Audit

## Dataset Duplication Stats

| dataset | horizon | unique decision_trace count | unique position count | avg trace / position | p50 trace / position | p90 trace / position | p99 trace / position | max trace / position |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clean_proof | 6h | 24229 | 32 | 757.16 | 366.00 | 2404.50 | 3225.06 | 3465 |
| clean_proof | 24h | 22453 | 30 | 748.43 | 341.50 | 2468.80 | 3240.54 | 3465 |
| future_clean | 6h | 18618 | 21 | 886.57 | 413.00 | 2307.00 | 2957.60 | 3110 |
| future_clean | 24h | 10178 | 7 | 1454.00 | 1436.00 | 2127.40 | 2133.34 | 2134 |
| terminal_clean | 6h | 5611 | 26 | 215.81 | 245.00 | 355.00 | 358.75 | 359 |
| terminal_clean | 24h | 12275 | 29 | 423.28 | 319.00 | 942.20 | 1302.44 | 1331 |

## Worst Positions

| position_id | decision_trace_count | selected_trace_count | top20_trace_count | first_decision_time | last_decision_time | open_time | exit_time | horizon | net_pnl_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shadow-pos-c5e8f94d64e82415136312e3 | 282 | 282 | 282 | 2026-05-24 14:17:21 UTC | 2026-05-25 06:00:47 UTC | 2026-05-24 14:17:23 UTC | 2026-05-25 06:00:54 UTC | 24h | -2.544001 |
| shadow-pos-2b1c5c39798221de81b22bb5 | 307 | 307 | 0 | 2026-05-23 10:50:19 UTC | 2026-05-23 23:06:57 UTC | 2026-05-23 10:50:23 UTC | 2026-05-23 23:08:02 UTC | 24h | -2.521978 |
| shadow-pos-842896745e4337f71da620a9 | 1229 | 1229 | 0 | 2026-05-22 07:52:26 UTC | 2026-05-23 07:50:29 UTC | 2026-05-21 06:50:11 UTC | 2026-05-23 07:51:02 UTC | 24h | -2.370946 |
| shadow-pos-b2b74e0686d4ef35496581ed | 894 | 894 | 0 | 2026-05-22 08:02:25 UTC | 2026-05-23 08:01:24 UTC | 2026-05-21 11:23:20 UTC | 2026-05-23 08:01:43 UTC | 24h | -2.227870 |

## Judgment

- proof_duplication_pollution = yes
- terminal_tail_concentration_main_driver = trace duplication + concentrated positions
