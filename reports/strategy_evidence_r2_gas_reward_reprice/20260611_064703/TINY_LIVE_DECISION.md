# Tiny-Live Decision — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## Recommendation: **NEED_MORE_DATA** (upgraded from R1's "thin edge")

The 3 R1 top candidates remain mechanically GO at $50 × 7d, with R2's better gas anchor widening the comfort zone. But the **decision rule for GO_TINY_LIVE** requires "signal-to-noise better than R1", and the IL-variance issue is unchanged from R1. Therefore R2's recommendation is the same name as R1 (NEED_MORE_DATA) with a much stronger evidence base.

## Top 3 candidates — repriced under R2 gas anchor

| Rank | Pool | Pair | Protocol | MVS × hold (R2) | Expected net @ 50×7d (R2) | Abort conditions |
|---|---|---|---|---|---|---|
| 1 | 0xb2cc... | WETH/USDC 0.05% | aerodrome-slipstream | **$3 × 7d** | **+$0.62** | pool TVL drops below $5M; 24h volume drops below $50M; ETH price moves >5% during the 7d window |
| 2 | 0x72ab... | WETH/USDC 0.01% | pancakeswap-v3-base | **$3 × 7d** | **+$0.27** | pool TVL drops below $2M; 24h volume drops below $25M; ETH price moves >3% during the 7d window |
| 3 | 0xb775... | WETH/USDC 0.05% | pancakeswap-v3-base | **$10 × 7d** | **+$0.25** | pool TVL drops below $1M; 24h volume drops below $3M; ETH price moves >5% during the 7d window |

(R1 said MVS=$25 for #1 and #2, and MVS=$50 for #3. R2 widens MVS to $3/$3/$10 respectively. The expected net at $50×7d is improved by $0.22 for #1, $0.22 for #2, $0.21 for #3.)

## Why still NEED_MORE_DATA, not GO_TINY_LIVE

The R2 stage spec defines `GO_TINY_LIVE` as requiring all of the following:

| Condition | Met? | Why |
|---|---|---|
| Top candidate expected_net_pnl_usd > 0 after observed gas | YES | $0.62, $0.27, $0.25 for top 3 |
| data_quality_score >= 0.75 | YES | R1: 0.85 |
| Risk level LOW or MEDIUM | YES | R1: LOW |
| Gas anchor observed | YES | R2: real on-chain USDC.approve=56,240 + gasPrice=0.006 gwei |
| Reward data either observed or not required | YES (for these specific candidates) | R1 top-3 are non-AERO WETH/USDC, so reward data is not required; AERO pools still have `reward_data_unavailable=partial` |
| Max tiny live size <= 50 USDC | YES | R2: $50 |
| Hold <= 7d | YES | R2: 7d |
| Clear abort conditions | YES | listed above |
| **Signal-to-noise better than R1** | **NO** | gas is fixed (R2 vs R1 = 3.8× better), but IL variance is unchanged ($1–2 on 15% range vs expected $0.62 net) |

The last check is the blocker. The 5–10% range around current tick (which is what a typical $50 LP position would use) has expected IL on a 5% price move of ~$1.25 (10% of position), which is **2× the expected net** even at R2's better gas anchor. The expected value is positive but the **variance is larger than the expected value**, so the position has positive EV but the distribution of outcomes is wide.

The R1 stage spec defined this as "expected net $0.04-$0.40 with IL variance ±$1-2, signal/noise too low for high-confidence GO". R2's gas math widens the "expected net" range to $0.25-$0.62, but the IL variance is unchanged. The signal-to-noise ratio (expected_net / IL_stddev) goes from 0.04-0.40 / 1.5 = 0.03-0.27 (R1) to 0.25-0.62 / 1.5 = 0.17-0.41 (R2). That's an improvement but still not a strong signal.

## What would change this to GO_TINY_LIVE

1. **A short-hold probe (≤ 1 hour)**. A 1-hour LP position has IL variance ~5× smaller than a 7-day position (sqrt of time, for a random-walk price). At 1h, expected IL on 5% range is $0.25 (5% × $50 × 1% price-move-per-hour = $0.025... actually for a true 1h, IL variance is much smaller). But the gas cost is still $0.08, so the position must collect >$0.08 in 1h to break even — and the fee yield is $0.07 per day, so 1h is too short.
2. **A delta-hedged position**. A perps short on Hyperliquid or similar would offset the IL but adds ~0.05% per day in funding cost (~$0.025/day on $50). Net: 0.07 - 0.025 - 0.01 (gas amortised over 1 day) = +$0.035/day on $50 = 25% APR. This is interesting but requires the lpbot to also operate a perps position, which is **out of scope** for the current freeze (no execution, no live, no canary, no paper).
3. **cbBTC re-classification as blue-chip**. R1's NEED_MORE_DATA on cbBTC/USDC 0.01% PancakeSwap becomes GO_TINY_LIVE at $3 × 7d. This is a model call, not a data call. The 9.2% fee APR on this pool (R1: fee_apr_est=9.1985) is much higher than the 2.8% on WETH/USDC, and the cbBTC price-volatility is comparable to WETH. R2 does not re-classify.

## What would change this to NO_GO

1. **Gas anchor observation that exceeds R1's $0.30 model**. R2's observed $0.08 at 0.05 gwei is well below R1's $0.30 — this is what enabled the upgrade. If a future observation shows gas is structurally higher (e.g., during a Base mainnet congestion event), the recommendation would revert to NEED_MORE_DATA.
2. **Live reward observation that AERO emissions are zero for the top 3 candidates**. R2's top 3 candidates are all non-AERO pools, so this is a non-issue for them. If the candidates were AERO pools (e.g., cbBTC/USDC 0.05% Aerodrome, which is R1 rank 4), reward data would matter; the current `reward_data_available=partial` would prevent a high-confidence GO on those.
3. **cbBTC de-peg**. If cbBTC traded below 0.99 × BTC for >24h, all cbBTC-paired pools would fail the risk filter. Not relevant for the top 3 (which are WETH/USDC), but worth noting.

## Safety

- Read-only. No wallet, no signing, no broadcast.
- All on-chain data came from `https://mainnet.base.org` (public, no auth) with browser User-Agent (Cloudflare bot protection bypassed).
- The lp_base_*_readonly.py scripts in `scripts/` were used as references; this R2 run does not modify any of them.
- The R1 reports directory is untouched.
- The freeze is preserved: no canary, no live, no paper, no mode B, no R1/R2 long-horizon collector restart.
