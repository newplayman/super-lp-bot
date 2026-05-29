# Tier C Data Source Plan

| data class | preferred source | coverage expected | rate limit risk | trust level | enough for Tier C proof |
|---|---|---|---|---|---|
| trader / buyer / seller | GeckoTerminal if available | medium | low | medium | no - current coverage is weak and zeros are ambiguous |
| trader / buyer / seller | DEX Screener if available | medium | medium | medium | no - useful cross-check only |
| trader / buyer / seller | on-chain swap logs research-only fallback | high | high | high | yes - strongest fallback for Tier C proof if implemented cleanly |
| holder concentration | existing snapshot provider | low | low | medium | partial - only if snapshot fresh and token listed |
| holder concentration | BaseScan provider | medium | medium | medium | partial - rate limits and inconsistent HTML/API responses |
| holder concentration | fallback research snapshot | medium | medium | medium | partial - acceptable for research filter, not final proof |
| exit depth | quote route simulation if available | medium | medium | high | yes - strongest direct proxy for small-size exit viability |
| exit depth | pool reserve / liquidity approximate model | high | medium | medium | partial - useful lower-confidence fallback |
| exit depth | DEX route API only as research source | medium | medium | medium | partial - okay for shadow/research only |
| short-window stability | GeckoTerminal OHLCV | high | low | high | yes - enough for candle-based survival metrics |
| short-window stability | local cached candles | high | medium | high | yes - preferred after first fetch |
| short-window stability | shadow price/volume snapshots | medium | medium | medium | partial - depends on coverage quality |

优先级：先补 trader / buyer / seller 与 exit depth，其次补 holder concentration 和 1h stability deltas。
