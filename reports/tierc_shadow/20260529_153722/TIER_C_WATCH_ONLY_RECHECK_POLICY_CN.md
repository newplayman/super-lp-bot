# TIER_C_WATCH_ONLY_RECHECK_POLICY

- `REJECT_LOCKED`: do not recheck on short cadence. Only revisit after rediscovery or a material market-structure change.
- `WATCH_RISK_HIGH`: recheck every 12h. Focus on trader concentration, holder concentration, and exit depth. Upgrade only if concentration and holder risks both move below research thresholds.
- `WATCH_NO_SWAP_LOGS`: recheck once after 6-12h. If swap logs are still absent, keep watch-only and do not escalate.
- `WATCH_UNSUPPORTED_POOL`: recheck only after a new parser/ABI path is added. Do not poll on time cadence alone.
- `WATCH_DATA_MISSING`: recheck every 6h. Focus on OHLCV/stability, buyers/sellers, unique traders, and exit depth.

Upgrade rules:
- WATCH -> `SHADOW_ONLY_DATA_READY` only if buyers/sellers, unique traders, trader concentration, holder concentration, exit depth, and stability are all present and none breach risk thresholds.
- WATCH -> `REJECT_LOCKED` if holder concentration becomes extreme, trader concentration becomes extreme, or repeated no-log/no-parser conditions show the pool is structurally unsuitable for Tier C proof.

Hard defaults:
- `holder_concentration_extreme` => `REJECT_LOCKED`
- `top1_trader_volume_share > 90%` => `WATCH_RISK_HIGH` unless later normalized
- `no_swap_logs` => recheck 6-12h later
- `unsupported_pool_type` => recheck only after parser support
- `stability_missing` => recheck after OHLCV/snapshot refresh
- `tiny_canary_allowed = no`
