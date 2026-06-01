# LP Scale Research Problem Definition

旧问题：
- 10U / 20U 小资金 LP 是否能直接正 EV？

新问题：
- 什么资金规模下，LP fee 能覆盖 IL/LVR、entry/exit slippage、gas/fixed cost。
- 10U / 20U 真实资金只用于 probe execution，不用于收益 proof。
- 20 / 100 / 500 / 1000 / 2000U 只做 virtual notional EV。
- `break_even_notional_usd` 和 `capacity_limit_usd` 是主指标。
- 不允许再用 10U / 20U 直接否定整个 LP 方向。

核心输出：
- `virtual_notional_ev`
- `break_even_notional_usd`
- `no_size_can_fix`
- `capacity_limit_usd`
- `fee_minus_cost_curve`
- `tail_risk_by_notional`
- `tier_score`
- `probe_readiness`
