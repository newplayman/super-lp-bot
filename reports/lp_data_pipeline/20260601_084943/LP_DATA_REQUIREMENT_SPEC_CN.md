# LP Data Requirement Spec

- `quote_exit_depth_20`: source=`existing exit-depth proxy + new quote-depth curve`, existing=`partial`, entry_safe=`yes`
- `quote_exit_depth_100`: source=`new quote-depth curve`, existing=`no`, entry_safe=`yes`
- `quote_exit_depth_500`: source=`new quote-depth curve`, existing=`no`, entry_safe=`yes`
- `quote_exit_depth_1000`: source=`new quote-depth curve`, existing=`no`, entry_safe=`yes`
- `quote_exit_depth_2000`: source=`new quote-depth curve`, existing=`no`, entry_safe=`yes`
- `entry_slippage_curve`: source=`pool math / dry quote`, existing=`partial`, entry_safe=`yes`
- `exit_slippage_curve`: source=`pool math / dry quote`, existing=`partial`, entry_safe=`yes`
- `realized_fee_accrual`: source=`positions/accounting`, existing=`partial`, entry_safe=`yes`
- `fee_apr`: source=`pools.fee_apr_24h`, existing=`yes`, entry_safe=`no`
- `fee_velocity_proxy`: source=`fee_velocity_exit_depth_counterfactual_v1`, existing=`yes`, entry_safe=`yes`
- `volume_x_fee_tier_proxy`: source=`marks + pools fee_bps`, existing=`yes`, entry_safe=`yes`
- `entry_safe_pool_snapshot`: source=`pool_regime_classifier_entry_safe_v1`, existing=`yes`, entry_safe=`yes`
- `gas_fixed_cost_proxy`: source=`research proxy`, existing=`yes`, entry_safe=`no`
- `il_lvr_proxy`: source=`marks-based proxy`, existing=`partial`, entry_safe=`yes`
- `holder_concentration`: source=`tierc_holder_concentration_v1`, existing=`partial`, entry_safe=`no`
- `trader_concentration`: source=`tierc_market_quality_enrichment_v1 / onchain logs outputs`, existing=`partial`, entry_safe=`no`
- `market_regime_volatility`: source=`pool_regime_classifier_entry_safe_v1 + marks`, existing=`yes`, entry_safe=`yes`
- `data_freshness_stale_flags`: source=`pool_regime_classifier_entry_safe_v1`, existing=`yes`, entry_safe=`yes`
