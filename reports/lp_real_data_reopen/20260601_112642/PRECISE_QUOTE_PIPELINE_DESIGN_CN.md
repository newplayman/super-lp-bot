# 精确 quote / route 方案设计

- primary quote method: `QuoterV2` static `eth_call`。
- fallback quote method: `v2 constant product / v3 tick-liquidity approximation`。
- route simulation: single pool first, multi-hop only if still read-only。
- notionals: `20 / 100 / 500 / 1000 / 2000U`。
- no wallet / no signature / no router submit。
- recommended next script: `LP_PRECISE_QUOTE_PIPELINE_V1`
