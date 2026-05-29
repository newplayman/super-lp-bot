# Terminal Negative Tail Audit

- source: `shadow_outcome_labels_repaired_terminal_v1`
- join note: pool/pair breakdown uses latest-per-(decision_trace_id,horizon) dedup

## Summary

| Horizon | total terminal count | p10 | p5 | p1 | <= -10% count | <= -50% count | <= -90% count | exactly -100% count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6h | 5683 | -2.370946 | -2.370946 | -2.544001 | 27 | 27 | 27 | 27 |
| 24h | 14047 | -2.370946 | -2.370946 | -2.544001 | 27 | 27 | 27 | 27 |

## Classification

| Horizon | classification | count |
| --- | --- | ---: |
| 6h | TERMINAL_VALUE_ZERO_BUG | 27 |
| 24h | TERMINAL_VALUE_ZERO_BUG | 27 |

## By Position / Pool / Reason / Action / Pair / Mark Source

| Horizon | position_id | pool_id | exit_reason | exit_action | token pair | mark_source | count |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| 24h | shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | closed after 26m; final pnl -4.9554 USD (fees 0.0000, il -4.9554, price -0.1660%) | shadow_close | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | pool_mark_only | 26 |
| 6h | shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | closed after 26m; final pnl -4.9554 USD (fees 0.0000, il -4.9554, price -0.1660%) | shadow_close | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | pool_mark_only | 26 |
| 24h | shadow-canary-live-pos-299da787e60301c7c2c61c0f | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | closed after 1m; final pnl -4.6813 USD (fees 0.0000, il -4.6813, price -4.9200%) | shadow_close | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | pool_mark_only | 1 |
| 6h | shadow-canary-live-pos-299da787e60301c7c2c61c0f | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | closed after 1m; final pnl -4.6813 USD (fees 0.0000, il -4.6813, price -4.9200%) | shadow_close | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | pool_mark_only | 1 |

## Judgment

- `-100%` 样本集中在极少数 `position_id`，而且 `terminal_value_usd = 0`、`fee/gas = 0`、`mark_source = pool_mark_only`。
- 这更像 `TERMINAL_VALUE_ZERO_BUG`，不是可接受的真实 terminal proof。
