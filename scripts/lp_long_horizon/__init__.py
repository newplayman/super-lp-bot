"""LP long-horizon read-only collector helper package.

Modules:
- lp_long_horizon.utils.retry: retry/backoff/timeout/429 helpers
- lp_long_horizon.utils.abort: AbortController, ErrorRateMonitor
- lp_long_horizon.adapters.local_artifact_replay: real pool_address source
- lp_long_horizon.adapters.public_api_coingecko: read-only OHLC source
- lp_long_horizon.adapters.solana_rpc_readonly: read-only getMultipleAccountsInfo source
- lp_long_horizon.classify.market_regime: 7-regime classifier
- lp_long_horizon.storage.research_store: SQLite + JSONL store
"""
__all__ = [
    "utils", "adapters", "classify", "storage",
]
