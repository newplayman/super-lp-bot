# Quote Depth Curve Schema

- table_name: `lp_quote_depth_curve_v1`
- entry_safe: `required`
- future_outcome_mixing: `forbidden`
- production_write: `forbidden`
- fields: `run_id`, `pool_id`, `token_pair`, `chain`, `pool_type`, `quote_side`, `virtual_notional_usd`, `quote_source`, `quote_ts`, `feature_cutoff_time`, `entry_safe`, `reserve_liquidity_usd`, `estimated_output_usd`, `estimated_slippage_pct`, `estimated_price_impact_pct`, `exit_depth_available`, `exit_depth_usd`, `capacity_pass`, `capacity_limit_usd`, `confidence`, `invalid_reason`, `created_at`
