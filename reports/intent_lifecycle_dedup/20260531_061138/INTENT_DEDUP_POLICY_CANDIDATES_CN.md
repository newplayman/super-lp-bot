# INTENT_DEDUP_POLICY_CANDIDATES_CN

- `pool_time_bucket_15m` key=pool_id + token_pair + strategy_epoch + 15m time bucket + intent type strength=High sample retention with reduced tick inflation weakness=May still overcount repeated traces within short bursts risk=medium test=yes
- `pool_time_bucket_30m` key=pool_id + token_pair + strategy_epoch + 30m time bucket + intent type strength=Balances compression and sample size weakness=May still repeat within half-hour market state risk=medium test=yes
- `pool_time_bucket_1h` key=pool_id + token_pair + strategy_epoch + 1h time bucket + intent type strength=Matches prior baseline and is easy to interpret weakness=Known to over-compress repeated ticks risk=high test=yes
- `pool_time_bucket_2h` key=pool_id + token_pair + strategy_epoch + 2h time bucket + intent type strength=Stronger anti-repeat control than 1h weakness=May remove legitimate state transitions risk=medium test=yes
- `pool_score_event_refined` key=pool_id + token_pair + strategy_epoch + 1h time bucket + score quantile bucket + intent type strength=Captures score regime while avoiding coarse collapse weakness=Sensitive to score noise in same pool risk=medium test=yes
- `position_reuse_session_refined` key=position_id + pool_id + strategy_epoch + 6h session bucket + intent type strength=Controls reuse-driven inflation at position level weakness=May still merge distinct market states within a session risk=high test=yes
- `hybrid_pool_time_score` key=pool_id + token_pair + strategy_epoch + 30m bucket + score quantile bucket + intent type strength=Better separation than pure time bucket weakness=Could still over-compress score plateaus risk=medium test=yes
- `strict_unique_market_state` key=pool_id + token_pair + strategy_epoch + 1h bucket + score bucket + volatility bucket + liquidity bucket + intent type strength=Strictest market-state separation weakness=Most likely to under-count valid lifecycle opportunities risk=low test=yes
