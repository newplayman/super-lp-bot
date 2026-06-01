# Quote Depth Source Selection

- primary_source: `reserve_math_approximation`
- fallback_source: `existing_exit_depth_estimates`
- requires_signature: `no`
- requires_wallet: `no`

- `onchain_reserve_approximation` selected=`no` supports=`partial` read_only_safe=`yes` limitations=`needs parser for pools.liquidity/tick plus protocol-specific math`
- `uniswap_v2_v3_math_from_pool_state` selected=`no` supports=`yes` read_only_safe=`yes` limitations=`best no-signing path if pool type coverage is good`
- `dex_aggregator_dry_quote_api` selected=`no` supports=`partial` read_only_safe=`yes` limitations=`not preferred until existing configured API is confirmed`
- `router_quoteStatic_callStatic` selected=`no` supports=`partial` read_only_safe=`yes` limitations=`safe if pure eth_call only, but protocol coverage still incomplete`
- `geckoterminal_dexscreener_liquidity_proxy` selected=`no` supports=`partial` read_only_safe=`yes` limitations=`good coarse fallback, not enough alone`
- `existing_exit_depth_research_tables` selected=`no` supports=`partial` read_only_safe=`yes` limitations=`currently only small-cap and Tier C oriented`
- `no_source` selected=`no` supports=`no` read_only_safe=`yes` limitations=`not acceptable`
