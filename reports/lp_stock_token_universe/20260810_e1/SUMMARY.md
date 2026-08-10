# Stock-token LP universe (read only)

- observed_at_utc: `2026-08-10T15:35:14.680746+00:00`
- input: `https://yields.llama.fi/pools`
- pool_count: **117**
- issuer_unknown_pool_count: **33**
- wash_suspect_pool_count (`vol1d/TVL > 1.5`): **7**
- Raydium protocol counts (metadata-first): `{'clmm': 52}`
- status: Stage-1 leads only; not on-chain validated and not entry-eligible evidence.

| chain | A | B | C | stock×stock |
|---|---:|---:|---:|---:|
| BSC | 1 | 0 | 0 | 0 |
| Base | 0 | 1 | 0 | 0 |
| Defichain | 25 | 0 | 0 | 0 |
| Ethereum | 8 | 0 | 0 | 0 |
| Mantle | 10 | 0 | 0 | 0 |
| Robinhood Chain | 4 | 0 | 0 | 0 |
| Solana | 43 | 9 | 15 | 1 |

## Protocol correction versus the task research assumption

The research memo treated `raydium-amm` as constant-product.  In this current snapshot the stock-token rows carry `poolMeta=Concentrated - …`; metadata therefore classifies them as `clmm`. The project slug alone is not accepted as architecture evidence, and ambiguous Raydium rows fail closed as `unknown`.

Different issuers always retain different `instrument_id` values; bare-ticker issuers remain `unknown`.
