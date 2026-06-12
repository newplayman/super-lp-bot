# Funding Source Health — D1

## Public endpoints tested (no auth, no API key)

| Source | URL | Status | Funding rate | Annualized APR |
|---|---|---|---|---|
| Hyperliquid | `https://api.hyperliquid.xyz/info` (type=metaAndAssetCtxs) | OK | -9.9002e-06 (1h) | -8.67% |
| Binance | `https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT` | OK | -6.5980e-05 (8h) | -7.22% |
| OKX | `https://www.okx.com/api/v5/public/funding-rate?instId=ETH-USD-SWAP` | **403 Forbidden** (Cloudflare block) | n/a | n/a |

**Median annualized funding APR (HL + Binance): -7.95%** (positive = longs pay shorts → shorts RECEIVE funding)

## Interpretation

- ETH perp funding is currently **negative** on both Hyperliquid and Binance, meaning **shorts pay longs** (a long-biased market, slightly backwardated).
- A SHORT ETH hedge would therefore **pay funding** at the current rates, not receive.
- This is the OPPOSITE direction from what the D1 spec's "neutral / +5% APR funding" scenarios assume. The D1 spec scenarios were framed for a SHORT that *receives* funding in normal conditions, which is the opposite of current reality.

## What this means for D1

- For a SHORT hedge, the funding cost is approximately **-7.95% APR** (cost, not income).
- The spec's -5% APR scenario (short receives funding) is **inconsistent with current data**. -20% APR is also unrealistic for current ETH.
- The 0% APR scenario in the spec is roughly the actual current state.
- The +5% APR and +20% APR scenarios are **favorable** to the SHORT thesis (assuming they would apply in the future) and are useful as upper-bound stress tests.

## Funding data freshness

- All sources checked at 2026-06-12T12:00:00Z.
- HL funding: 1h cadence. Binance/OKX: 8h cadence.
- Coinglass was NOT queried (spec says "only if no key needed" — Coinglass requires auth for funding history).
- Snapshot is point-in-time; the D1 model uses the spec's scenario table as primary input and uses the current rates as a sanity check.

## Note for D1 model

The model uses the spec's funding scenarios as primary inputs (-20% to +20% APR in 5 steps). The current observed rate of -7.95% is between the 0% and -5% scenarios and is a useful point estimate for the "current regime" case.
