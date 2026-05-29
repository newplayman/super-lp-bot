# Entry Untrusted Top20 Deep Dive

- source: `shadow_outcome_labels_repaired_terminal_v1`
- join note: `shadow_outcome_labels_repaired_v2` uses latest-per-(decision_trace_id,horizon) dedup to avoid doubled report counts

## Summary

| Horizon | entry_untrusted total | selected entry_untrusted | top20 entry_untrusted | selected+top20 entry_untrusted |
| --- | ---: | ---: | ---: | ---: |
| 6h | 1935 | 1935 | 816 | 816 |
| 24h | 1921 | 1921 | 813 | 813 |

## Breakdown

| Horizon | reason | count |
| --- | --- | ---: |
| 6h | missing_position_id | 1935 |
| 24h | missing_position_id | 1921 |

## Top Affected

| Horizon | position_id | pool_id | token pair | score bucket | time bucket | count |
| --- | --- | --- | --- | --- | --- | ---: |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 06:00 | 60 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 01:00 | 60 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 04:00 | 60 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 05:00 | 60 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 07:00 | 60 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 03:00 | 60 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 03:00 | 59 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 07:00 | 59 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-23 02:00 | 59 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 01:00 | 59 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 04:00 | 59 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 05:00 | 58 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 06:00 | 58 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | bottom20 | 2026-05-23 09:00 | 56 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | bottom20 | 2026-05-23 09:00 | 56 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | unknown/unknown | mid80 | 2026-05-22 19:00 | 56 |
| 24h | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | top20 | 2026-05-22 19:00 | 56 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 02:00 | 56 |
| 6h | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | unknown/unknown | top20 | 2026-05-22 19:00 | 56 |
| 24h | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 0x4200000000000000000000000000000000000006/0x833589FCD6EDB6E08F4C7C32D4F71B54BDA02913 | mid80 | 2026-05-23 03:00 | 54 |

## Proof Impact

| Horizon | metric | value |
| --- | --- | --- |
| 24h | exclude_entry_untrusted top20_vs_bottom20 pct_signal | better |
| 6h | exclude_entry_untrusted top20_vs_bottom20 pct_signal | better |
| 24h | only_entry_trusted median_net_pnl_pct | 0.090904 |
| 6h | only_entry_trusted median_net_pnl_pct | 0.140547 |
| 24h | only_entry_trusted p10_net_pnl_pct | -2.227870 |
| 6h | only_entry_trusted p10_net_pnl_pct | 0.000436 |

## Judgment

- `entry_untrusted` 的一手口径应归类为 `missing_position_id`，不是 `positions_amount_missing`。
- 它落在 `reconstructable_by_pool_time_strategy / medium confidence` 路径，更像 lineage gap，而不是策略逻辑反转。
- 但 top20 里仍有 816 / 813 条，因此 `reality_gate` 不能转 PASS。
