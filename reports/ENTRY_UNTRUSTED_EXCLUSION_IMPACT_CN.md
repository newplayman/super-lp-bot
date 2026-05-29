# Entry Untrusted Exclusion Impact

- source: `shadow_outcome_labels_repaired_terminal_v1`

## Impact Summary

| Horizon | top20 count before | top20 count after excluding entry_untrusted | top20 median pct before | top20 median pct after | top20 p10 pct before | top20 p10 pct after | bottom20 median pct before | bottom20 median pct after | pct_signal before | pct_signal after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 6h | 5260 | 4444 | 1.331198 | 2.074138 | 0.000000 | 0.156497 | 0.140170 | 0.141561 | better | better |
| 24h | 4900 | 4087 | 0.596005 | 4.255168 | -0.019768 | -0.019768 | 0.069957 | 0.069957 | better | better |

## Concentration

| Horizon | pool_id | position_id | time bucket | count |
| --- | --- | --- | --- | ---: |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 05:00 | 60 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 04:00 | 60 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 06:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 03:00 | 60 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 01:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 01:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 05:00 | 60 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 07:00 | 60 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 03:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 04:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 07:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 06:00 | 60 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 02:00 | 59 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 02:00 | 59 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-22 19:00 | 58 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-22 19:00 | 58 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 00:00 | 57 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-23 00:00 | 57 |
| 6h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-22 21:00 | 57 |
| 24h | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | shadow-pos-b56917c6282e10d8858782aa | 2026-05-22 21:00 | 57 |

## Judgment

- `entry_untrusted` does not reverse edge direction if excluded; `pct_signal` remains `better` in both horizons.
- It is concentrated in a small set of pool/position/time buckets, not spread uniformly across the whole proof surface.
