# Improved Quote Depth Method

- constant_product: `v2_reserve_math_proxy` if reserve/liquidity available, else `v2_tvl_volume_proxy`
- concentrated_liquidity: `v3_tick_liquidity_proxy` if tick/liquidity present, else `v3_conservative_liquidity_proxy`
- unknown: `liquidity_proxy_only` with low confidence
- external_cached_liquidity: diagnostic-only fallback, low/medium confidence

- wallet_or_signature_required: `no`
- router_submit_required: `no`
- monotonicity_required: `yes`
- confidence_assigned_per_row: `yes`
