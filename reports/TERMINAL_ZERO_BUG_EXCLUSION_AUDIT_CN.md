# Terminal Zero Bug Exclusion Audit

- source: `shadow_outcome_labels_repaired_terminal_v1`

## Summary

| Horizon | exactly -100% count before | exactly -100% count after | p10 before | p10 after | median before | median after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6h | 27 | 0 | -2.370946 | -2.370946 | 0.021239 | 0.021239 |
| 24h | 27 | 0 | -2.370946 | -2.370946 | 0.000779 | 0.000779 |

## Affected Positions / Pools

| Horizon | position_id | pool_id | token pair | count |
| --- | --- | --- | --- | ---: |
| 24h | shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | 26 |
| 6h | shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | 26 |
| 24h | shadow-canary-live-pos-299da787e60301c7c2c61c0f | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | 1 |
| 6h | shadow-canary-live-pos-299da787e60301c7c2c61c0f | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | 1 |

## Judgment

- After excluding the terminal zero bug cohort, the explicit `-100%` tail disappears.
- This does not mean the terminal cohort is automatically safe; it only proves the known `pool_mark_only + terminal_value_usd=0` bug is removable from proof.
