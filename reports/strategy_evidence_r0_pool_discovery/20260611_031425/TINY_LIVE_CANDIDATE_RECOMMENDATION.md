# Tiny-Live Candidate Recommendation

**Status:** **`NEED_MORE_DATA`** (not `GO_TINY_LIVE`).
**Reason:** No pool in the 120-pool set produces a positive expected net PnL at 1-10 USDC after fees, IL, and gas. The 8 highest-scoring blue-chip / one-stable pools all net between -$0.26/day and -$0.30/day at the optimal (size, range) cell.

## Top-3 by score (all `NEED_MORE_DATA`)

These are the three pools that would, *if* the fee/gas ratio were not the binding constraint, be the most defensible tiny-live probes on Base. They are documented for ChatGPT-side review and for the next re-scan, **not** as instructions to execute.

### Candidate #1 — Aerodrome WETH / USDC 0.05% (deepest WETH/USDC pool)
- **Pool:** `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59` (Aerodrome slipstream)
- **Pair:** WETH / USDC, fee tier 0.05% (5 bps)
- **TVL:** $8.48M, **24h vol:** $133.3M
- **24h price change:** +0.6% (low)
- **Best cell:** 10 USDC, narrow 5% range
- **Expected gross fee:** $0.0786/day
- **Expected IL:** $0.0361/day
- **Gas / cycle:** $0.30
- **Expected net:** **-$0.258/day**
- **Fee/gas:** 0.26×
- **Risk level:** LOW (0 risk-score; both sides are blue-chip)
- **Why it's #1:** deepest TVL on Base in the WETH/USDC 0.05% tier, most resilient to a 1-10 USDC LP, lowest risk score in the candidate band.
- **What it would take to promote to `GO_TINY_LIVE`:** either (a) gas/cycle falls below $0.02 (would need L2 gas oracle observation in a 0.1 gwei window) or (b) we accept holding the position ≥ 4 days and price the time-cost as zero. Neither is a sane choice today.

### Candidate #2 — Aerodrome WETH / USDC 0.05% (2.95M TVL)
- **Pool:** `0x3fe04a59ebd38cf06080a6a98d124eb59392a` (Aerodrome slipstream)
- **Pair:** WETH / USDC, fee tier 0.05%
- **TVL:** $2.95M, **24h vol:** $34.3M
- **Best cell:** 10 USDC, narrow 5% range
- **Expected net:** **-$0.278/day**
- **Fee/gas:** 0.19×
- **Risk:** LOW
- **Why it's #2:** same shape as #1 with lower TVL; not strictly preferred but the data shows the deeper pool (rank 1) is the right one to bet on if the gas constraint ever loosens.

### Candidate #3 — Aerodrome USDC / cbBTC 1% (only fee tier that produces positive gross fee)
- **Pool:** `0x3e66e55e97ce60096f74b7c475e8249f2d31a9fb` (Aerodrome slipstream)
- **Pair:** USDC / cbBTC, fee tier **1%** (100 bps)
- **TVL:** $2.89M, **24h vol:** $7.10M
- **Best cell:** 10 USDC, narrow 5% range
- **Expected gross fee:** **$0.246/day** (highest in the set)
- **Expected IL:** $0.013/day (low — cbBTC is the most "stable" of the L1 wraps)
- **Expected net:** **-$0.067/day** (closest to breakeven)
- **Fee/gas:** 0.82×
- **Risk level:** MEDIUM (25 risk-score) — `non_bluechip_pair` flag (cbBTC is L1-wrap BTC; the risk filter treats it as non-stable, hence not blue-chip)
- **Why it's #3 and not #1:** the only pool where the fee income *almost* covers gas. The risk filter being too strict on cbBTC is the policy decision worth revisiting.
- **What it would take to promote to `GO_TINY_LIVE`:** reclassify cbBTC as L1-blue-chip for tiny-live. That is a risk-model change, not a runtime change.

## Recommended initial size, range, hold time, exit condition

*(For the day this stage becomes `GO_TINY_LIVE`. Not for today.)*

| | Candidate #1 | Candidate #2 | Candidate #3 |
|---|---|---|---|
| Recommended initial size | 1 USDC (probe, not 10) | 1 USDC | 1 USDC |
| Recommended range | narrow 5% | narrow 5% | narrow 5% |
| Recommended max runtime | 24 h | 24 h | 24 h |
| Hard exit (price) | price leaves ±5% of entry | same | same |
| Hard exit (time) | 24 h regardless | same | same |
| Max acceptable loss | 1 USDC + gas (~$0.30) | same | same |
| Expected daily fee at 1 USDC | $0.0079 | $0.0058 | $0.0246 |
| Expected daily net at 1 USDC | -$0.30 | -$0.31 | -$0.29 |

The recommendation is **1 USDC, not 10 USDC**, even though 10 USDC is the "best" cell by the score. At 1-10 USDC the *gross fee* is so small that the gas cost of one cycle is a meaningful fraction of the position. The right probe size is the smallest unit that produces a measurable on-chain signature (1 USDC = ~7 swaps at 5 bps fee to break even on the gas cost of a single tx).

## What we do not yet know

- **Gas in a 1-3 gwei window** (Base is usually < 1 gwei at low-traffic hours; this run did not measure it). The $0.30/cycle is a mid-range assumption.
- **Whether cbBTC should count as blue-chip** for tiny-live risk classification. The model currently says no; one reasonable counter-position says yes.
- **Whether the 24h volume reflects a normal regime.** Today's run shows base volume on WETH/USDC at ~$133M for one pool, which is high; this may be transient. A 7-day rolling average would tighten the fee estimate.
- **Whether a non-Aerodrome venue (Uniswap V3, PancakeSwap V3) has a structurally different fee tier that closes the gap.** None of the ranked 53 did, but the 120-pool set is dominated by Aerodrome slipstream.
- **Holder concentration and contract risk** on the long-tail tokens (AERO, VIRTUAL, VVV, etc.) — those pools are filtered out of the top-3, but if we relax the pair allowlist, those become the next candidate set.

## Explicit no-go for the rest of the 53 ranked pools

See `NO_GO_REASONS.md`.
