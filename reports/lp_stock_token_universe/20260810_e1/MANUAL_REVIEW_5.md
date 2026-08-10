# E1 manual review — five pools

Review scope: issuer identity and protocol architecture only.  DefiLlama yield,
TVL, volume, and pool UUID remain Stage-1 aggregator leads and were not promoted
to on-chain facts by this review.

| pool UUID | chain / pool | issuer check | protocol check | verdict |
|---|---|---|---|---|
| `9462784c-c0e5-4539-914e-ac006e5b3097` | Solana `AAPLX-USDC` (`raydium-amm`) | `AAPLX` is the normalized display form of Backed `AAPLx`; instrument `backed:AAPLX`, underlying `AAPL` | current row metadata is `Concentrated - 0.25%`; metadata overrides the legacy slug, so this is `clmm` | correct |
| `d841f4d5-34a3-4671-809e-47ed34fd9bcf` | Solana `NVDAX-USDC` (`orca-dex`) | `NVDAX` is Backed `NVDAx`; instrument `backed:NVDAX`, underlying `NVDA` | Orca pool path is Whirlpool/concentrated liquidity (`clmm`) | correct |
| `39a5812f-e1cf-56f4-aa1c-12098cc6ac1d` | BSC `USDT-SPYON` (`uniswap-v3`) | reviewed Ondo suffix mapping gives instrument `ondo:SPYON`, underlying `SPY`; it is not merged with Backed `SPYX` | Uniswap v3 is concentrated liquidity (`clmm`) | correct |
| `4f4f8680-0740-55fc-b0b5-dd49f530f9f5` | Robinhood Chain `USDG-NVDA` (`ekubo`) | chain-scoped bare ticker gives instrument `robinhood:NVDA`; it is not merged with Backed `NVDAX` | Ekubo is classified as concentrated liquidity (`clmm`) | correct |
| `b2dc3501-c0b2-4463-9d19-35dd1a8630b5` | Ethereum `WTSLAX-USDC` (`uniswap-v3`) | wrapper normalization maps `WTSLAX` to Backed instrument `backed:TSLAX`, underlying `TSLA` | Uniswap v3 is concentrated liquidity (`clmm`) | correct |

All five rows match the reviewed catalogue and explicit protocol dispatch table.
The review intentionally does not guess the issuer of bare tickers outside an
issuer-specific chain: the current evidence reports those pools as `unknown`.
