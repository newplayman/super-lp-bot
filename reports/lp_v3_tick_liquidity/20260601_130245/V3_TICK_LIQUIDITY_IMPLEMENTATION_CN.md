# V3 Tick Liquidity Implementation

- script: `scripts/lp_v3_tick_liquidity_pipeline_v1_readonly.py`
- chain calls: `eth_call` only
- state-changing methods: rejected
- DB writes: independent research-only table `lp_v3_tick_liquidity_snapshot_v1`
- hard cap words per side: `8`
