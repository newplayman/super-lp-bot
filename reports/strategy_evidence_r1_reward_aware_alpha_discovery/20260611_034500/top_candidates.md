# Top Candidates — R1

**Generated:** 2026-06-11T03:46:00Z
**Source:** `ranked_candidates.csv` (35 rows: 3 GO_TINY_LIVE, 7 NEED_MORE_DATA, 25 NO_GO)

## Tiny-Live Candidate #1 — Aerodrome WETH / USDC 0.05%

- **Pool:** `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59` (Aerodrome slipstream)
- **Pair:** WETH / USDC, fee tier 0.05% (5 bps)
- **TVL:** $8.74M
- **24h volume:** $134.65M
- **24h price change:** +1.24%
- **Risk level:** LOW (risk-score 0; both sides blue-chip)
- **Data quality:** 0.85
- **Fee APR est:** 281% (this is *not* an LP APR — it's `(vol24 * fee_bps / tvl) * 365`; the LP's share of this depends on capitalisation. The actual per-dollar-per-day fee yield is 0.77%/day → 281% APR. **This is the upper bound assuming a tiny LP takes the full 0.05% cut of every swap; in reality the LP receives a fraction dictated by tick range.**)
- **Why this pool:** Deepest WETH/USDC TVL on Base; lowest vol/TVL variance; passes gas amortization at 50 USDC × 7d.
- **Recommended size:** $50 USDC (matches the minimum viable size).
- **Minimum viable size:** $25 USDC × 7d (crosses zero with $0.13 expected net).
- **Recommended hold time:** 7 days.
- **Expected net PnL at $50 × 7d:** +$0.40 (after -$2.70 fee + $0.34 IL + $0.30 gas = +$0.40, model-implied). Note: at $25 the model says +$0.13 expected net; this is the *minimum* size that the model says breaks even.
- **Max acceptable loss:** $50 (full position + 1 cycle of gas).
- **Stop condition:** price leaves ±15% of entry (medium range).
- **Kill condition:** 24h with 0% gross fee accrual (data quality of $0 fee income is a kill signal — re-evaluate).
- **Unresolved data gaps:** AERO rewards (offline subgraph), holder concentration (not in GeckoTerminal), live gas oracle confirmation (still $0.30 hand-estimate).

## Tiny-Live Candidate #2 — PancakeSwap V3 WETH / USDC 0.01%

- **Pool:** `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (PancakeSwap V3 Base)
- **Pair:** WETH / USDC, fee tier 0.01% (1 bp)
- **TVL:** $3.93M
- **24h volume:** $48.56M
- **Risk level:** LOW
- **Data quality:** 0.85
- **Fee APR est:** 275%
- **Why this pool:** PancakeSwap V3 is the only other blue-chip venue on Base with a 0.01% tier. 0.01% fees are very thin, but volume is real and the pool passes gas at $50 × 7d.
- **Recommended size:** $50 USDC.
- **Minimum viable size:** $25 USDC × 7d (net ≈ $0.05).
- **Recommended hold time:** 7 days.
- **Expected net PnL at $50 × 7d:** +$0.05.
- **Max acceptable loss:** $50.
- **Stop condition:** price leaves ±15% of entry.
- **Kill condition:** 24h with 0% gross fee accrual.
- **Unresolved data gaps:** Same as #1.

## Tiny-Live Candidate #3 — PancakeSwap V3 WETH / USDC 0.05%

- **Pool:** `0xb775272e537cc670c65dc852908ad47015244eaf` (PancakeSwap V3 Base)
- **Pair:** WETH / USDC, fee tier 0.05% (5 bps)
- **TVL:** $1.31M
- **24h volume:** $5.84M
- **Risk level:** LOW
- **Data quality:** 0.85
- **Fee APR est:** 57% (lowest of the three)
- **Why this pool:** Only included for cross-venue diversification. Expected net is thin ($0.04 over 7d) so it ranks #3 by score.
- **Recommended size:** $50 USDC.
- **Minimum viable size:** $50 USDC × 7d (does not pass at $25).
- **Recommended hold time:** 7 days.
- **Expected net PnL at $50 × 7d:** +$0.04.
- **Max acceptable loss:** $50.
- **Stop condition:** price leaves ±15% of entry.
- **Kill condition:** 24h with 0% gross fee accrual.
- **Unresolved data gaps:** Same as #1.

## Why these 3 and not the next 7 (NEED_MORE_DATA)

The next 7 are:

| rank | pool | why NEED_MORE_DATA |
|---|---|---|
| 4 | cbBTC / USDC 0.05% aerodrome | MEDIUM risk (cbBTC not stable, gets risk-score 30) |
| 5 | cbBTC / USDC 0.01% pancakeswap-v3 | MEDIUM risk, but passes gas at $3 × 7d — the most efficient by capital |
| 6 | WETH / cbBTC 0.05% hydrex-integral | MEDIUM risk; new venue (hydrex), not enough history |
| 7 | cbBTC / USDC 0.05% uniswap-v3-base | MEDIUM risk; Uniswap V3 Base has lower vol/TVL |
| 8 | EURC / USDC 0.05% aerodrome | MEDIUM risk; EURC is a smaller stablecoin with lower volume |
| 9 | VIRTUAL / WETH 0.05% aerodrome | MEDIUM risk; VIRTUAL is a long-tail token (the 30 risk-score) |
| 10 | msUSD / USDC 0.05% aerodrome | MEDIUM risk; msUSD is MetaMask's USD — a stablecoin but newer |

The 7 NEED_MORE_DATA candidates become GO_TINY_LIVE-eligible if any of:
- cbBTC is reclassified as blue-chip (lowering the risk-score to 0),
- AERO reward APR for AERO-paired pools is recovered (offline subgraph fix),
- A live on-chain gas oracle measurement confirms <$0.20/cycle (unlikely on Base at 10 gwei).

## What we are NOT recommending

- **Stable-stable pairs** (USDC/USDT, USDC/USDbC) — at 0.01% fee tier, the volume/TVL is so thin that even at $50 × 7d they don't pass. They're in the top 35 but at NO_GO.
- **AERO/USDC, AERO/WETH** — present in the dataset, but with `reward_data_unavailable=true` and fee APR (excluding rewards) < 0.5%/day, they don't pass at any size below $100. With AERO rewards recovered, they might — but that requires R2b (Aerodrome Voter address recovery).
- **Long-tail Aerodrome pools** (VIRTUAL, DEGEN, TOSHI, etc.) — risk-penalised for being non-bluechip; their fee income is high but the model down-weights them for tiny-live safety.
