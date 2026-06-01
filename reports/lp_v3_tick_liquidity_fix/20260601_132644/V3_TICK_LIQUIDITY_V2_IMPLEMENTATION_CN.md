# V3 Tick Liquidity V2 Implementation

- script: `scripts/lp_v3_tick_liquidity_pipeline_v2_readonly.py`
- strategy: prevalidate standard 224-byte slot0 pools only for high-confidence materialization
- unsupported variants remain diagnostic-only
- DB writes: independent research-only table `lp_v3_tick_liquidity_snapshot_v2`
