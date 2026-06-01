# Virtual Notional Economics Model

- `gross_fee_usd = virtual_notional * fee_velocity_rate * hold_time_factor`
- `il_lvr_cost_usd = virtual_notional * il_lvr_proxy_rate`
- `proportional_slippage_usd = virtual_notional * slippage_rate_for_notional`
- `fixed_cost_usd = gas/fixed execution/routing cost proxy`
- `exit_cost_usd = quote/slippage proxy + fixed cost`
- `net_ev_usd = gross_fee - il_lvr_cost - proportional_slippage - fixed_cost - exit_cost`
- `net_ev_pct = net_ev_usd / virtual_notional`
- `break_even_notional_usd = fixed_cost / variable_edge_rate if >0 else NO_SIZE_CAN_FIX`
- `capacity_limit_usd = conservative min(depth bound, slippage bound)`

注意：不能把 20U 结果按线性倍数扩展到 100/500/1000/2000U。
