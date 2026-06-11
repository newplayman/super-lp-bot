# No-Go Reasons — R0 Base Pool Discovery

**Of 53 risk-passed pools ranked, 0 are `GO_TINY_LIVE`.**

## A. The 45 `NO_GO` pools (risk-passed, expected net negative)

The dominant reason is the same for all 45: **expected net PnL is negative at 1-10 USDC** because daily fee income is < $0.30 gas cost. The risk filter passed them (LOW or MEDIUM), but the LP economics don't close.

Sub-categorisation (by far the most common pattern in the data):

| Sub-reason | Count | Example |
|---|---|---|
| `non_bluechip_pair` risk flag (e.g. AERO/WETH, VIRTUAL/USDC, VVV/WETH, DEGEN/WETH, msETH/WETH, etc.) | ~30 | `0x9785ef59e2b499fb741674ecf6faf912df7b3c1b` (USDT/WETH MEDIUM, non-bluechip) |
| Stable-stable pair (e.g. USDC/USDT, USDC/USDbC) — volume/TVL is too thin to overcome gas | ~5 | USDC/USDT pools |
| `both_stable` flag plus low 24h volume | ~5 | (see ranked CSV rows 12-30) |
| MEDIUM risk from `non_bluechip_pair` even though one side is L1-wrap | ~5 | cbBTC, cbETH combinations |

The full enumeration is in `ranked_tiny_live_candidates.csv` columns `reason` and `go_no_go`. The `reason` text is a short tag explaining the per-row decision; the same pattern repeats 45 times with different pool addresses.

## B. The 8 `NEED_MORE_DATA` pools (the top-8 of the run)

Documented in `TINY_LIVE_CANDIDATE_RECOMMENDATION.md`. All are Aerodrome WETH/USDC or USDC/cbBTC blue-chip / one-stable. They pass risk and have real volume, but the *fee/gas ratio* is < 1.0 at 1-10 USDC. The honest read is:

> For 1-10 USDC positions, Base mainnet's retail-tier LP economics do not amortise a full add+remove+collect gas cycle on the current WETH/USDC 0.05% / 0.3% and USDC/cbBTC 1% pools.

The path to `GO_TINY_LIVE` is either (a) gas/cycle falls to < $0.02 in a low-traffic window, (b) the position is sized large enough to make 0.1% / day a meaningful return (~$1000+ LP where the daily fee covers gas even on a 0.05% tier), or (c) the risk model is updated to count cbBTC as blue-chip for tiny-live.

## C. The 52 `HIGH` / `REJECT` pools (did not even make the ranking)

| Risk level | Count | Typical reason |
|---|---|---|
| HIGH | ~9 | `tvl_below_floor` (TVL < $50k) **and** `abs_pc24 > 35%` — too thin and too volatile |
| REJECT | ~43 | Long-tail meme token (INU/PEPE/DOGE pattern) **or** `tvl_below_floor` (TVL < $50k) **or** pool age < 14d **or** `low_vol_to_tvl` (< 5% per day — dead pool) |

The full per-row reasons are in `risk_filtered_pools.csv` column `risk_flags` (semicolon-separated tags) and `risk_flags.jsonl` (structured per-pool).

## D. The headline no-go for "tiny live at retail on Base today"

If the question is *"if I had to put $1-10 USDC into an LP on Base mainnet today, would I make money?"* the answer is:

> **No, on a per-day basis.** The fee income is real but it is dwarfed by the gas cost of one cycle. To break even on gas in the WETH/USDC 0.05% Aerodrome pool at $10 USDC, you need to hold the position for ~4 days. IL is small in expectation but adds a few cents/day of variance.

This is consistent with the `20260531_124000` final freeze's conclusion that 5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP. The current run confirms the same shape holds on Base at 1-10 USDC: **the per-position fee income is below the gas amortization threshold**.

## E. When to re-scan

- **Weekly**, to see if volume structure changes.
- **Immediately after** any of: (a) Base gas dropping to sub-0.1 gwei for a sustained window, (b) a new fee tier appearing on Aerodrome (e.g. 0.5% for stable pairs), (c) a deep new pool on Uniswap V3 Base with a 1% tier on a blue-chip pair, (d) the freeze being reopened with explicit R0-R5 6-stage plan approval.

Do not re-promote to `GO_TINY_LIVE` based on this run alone.
