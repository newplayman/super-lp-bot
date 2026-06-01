# LP Data Pipeline Schema Proposal

- `lp_pool_snapshot_entry_safe_v1`: purpose=`entry-safe pool state snapshots`, entry_safe=`strict`, source=`pools + marks + optional API snapshot`
- `lp_quote_depth_curve_v1`: purpose=`per-pool quote/depth curve by notional`, entry_safe=`strict`, source=`pool math or dry quote`
- `lp_fee_velocity_v1`: purpose=`fee proxy / realized fee lineage`, entry_safe=`strict`, source=`vol*fee_tier proxy and/or onchain swap logs`
- `lp_cost_model_v1`: purpose=`gas/fixed/routing cost proxy`, entry_safe=`not_required`, source=`research proxy + dry quote metadata`
- `lp_il_lvr_proxy_v1`: purpose=`IL/LVR proxy per pool bucket`, entry_safe=`strict`, source=`price path proxy`
- `lp_pool_quality_features_v1`: purpose=`holder/trader/stability/features for scoring`, entry_safe=`strict_or_documented_proxy`, source=`entry-safe snapshots + concentration audits`
- `lp_virtual_notional_economics_v1`: purpose=`virtual notional EV dry model`, entry_safe=`strict`, source=`join of all research-only tables`
