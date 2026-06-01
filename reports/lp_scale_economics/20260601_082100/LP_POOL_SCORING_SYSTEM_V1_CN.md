# LP Pool Scoring System V1

- `lp_scale_score_0_100` = weighted sum of fee, depth, slippage, volatility, TVL, volume, concentration, freshness, tail risk.
- `tier_fit_score` = pool scale fit overlay for Tier A/B/C.
- `probe_candidate` = policy flag only, not permission to trade.
- `virtual_notional_candidate` = only means pool is worth dry-modeling further.

评分维度：
- `fee_velocity_score` weight=0.14
- `exit_depth_score` weight=0.18
- `slippage_score` weight=0.12
- `volatility_score` weight=0.1
- `tvl_stability_score` weight=0.1
- `volume_stability_score` weight=0.08
- `holder_concentration_score` weight=0.1
- `trader_concentration_score` weight=0.08
- `data_freshness_score` weight=0.05
- `tail_risk_score` weight=0.05
