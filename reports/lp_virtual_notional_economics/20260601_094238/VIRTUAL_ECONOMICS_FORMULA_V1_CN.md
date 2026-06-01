# Virtual Economics Formula V1

- `gross_fee_proxy_usd = virtual_notional * fee_velocity_rate * hold_time_factor`
- `il_lvr_proxy_usd = virtual_notional * il_lvr_proxy_rate`
- `slippage_cost_usd = virtual_notional * slippage_rate`
- `exit_cost_usd = virtual_notional * exit_cost_rate`
- `fixed_cost_usd = gas_proxy + fixed_routing_operational_cost_proxy`
- `net_ev_proxy_usd = gross_fee_proxy_usd - il_lvr_proxy_usd - slippage_cost_usd - exit_cost_usd - fixed_cost_usd`
- `net_ev_proxy_pct = net_ev_proxy_usd / virtual_notional`
- `variable_edge_rate = (fee_velocity_rate * hold_time_factor) - il_lvr_proxy_rate - slippage_rate - exit_cost_rate`
- `break_even_notional_usd = fixed_cost_usd / variable_edge_rate if variable_edge_rate > 0 else NO_SIZE_CAN_FIX`

- 20U 结果不能线性外推到更大 notional。
- 每个 notional 使用对应 quote/depth/slippage。
- 低置信 quote 只进入 low_confidence economics。
- 正 proxy EV 不代表 edge_proven。
- 不允许进入 probe/canary。
