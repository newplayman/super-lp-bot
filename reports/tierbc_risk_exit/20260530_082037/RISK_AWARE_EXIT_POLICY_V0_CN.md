# RISK_AWARE_EXIT_POLICY_V0

- price_move_15m_down: tier_b=< -2% tier_c=< -1.5% data=price_move_15m
- tvl_drop_1h: tier_b=> 20% tier_c=> 10% data=tvl_drop_1h
- volume_collapse_1h: tier_b=> 70% drop tier_c=> 50% drop data=volume_change_1h
- trader_share_spike: tier_b=top1 > 50% or top5 > 75% tier_c=top1 > 90% or top5 > 95% data=top1/top5 trader share
- exit_depth_bad: tier_b=THIN/UNKNOWN tier_c=THIN/UNKNOWN data=exit_depth_status
- mark_stale: tier_b=true tier_c=true data=mark_stale
- fee_velocity_decay: tier_b=high decay tier_c=medium decay data=fee_velocity_decay
- max_hold_time: tier_b=6h/12h/24h tier_c=15m/30m/1h/2h data=clock only