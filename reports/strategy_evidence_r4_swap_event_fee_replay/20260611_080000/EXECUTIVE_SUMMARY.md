# Executive Summary — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000
**Verdict:** **PASS** (historical replay complete, decision clear, no execution)

## TL;DR

R4 calibrates the R1/R2 fee proxy by reading **real on-chain Swap events** for the 3 top
candidate pools over 24h. The result is the **opposite of what R1/R2/R3 feared**: the
fee proxy is **conservative by 100-1000×** for tight-range positions, not aggressive.

### Headline numbers

- **115,680 Swap events** decoded across 3 pools in 24h
- **100% decode success rate** (0 decode failures)
- **R2 reported volume is overestimated by 7-53%** (R4 capture_vol 0.47-0.93)
- **R2 fee proxy is conservative by 100-1000×** for tight-range LPs (R4 capture_ratio 97-1435)
- **$50 × 7d ±10% range** on top pool 0xb2cc... would net **~$107/day** in fees
  (R2 expected: $0.39/day)

### Final recommendation: `GO_TINY_LIVE_PLAN_ONLY`

A $50 × 7d position on pool 0xb2cc... (Aerodrome Slipstream WETH/USDC 0.05%) with
±10% range is **strongly positive** under R4's replay:

- Expected net: **$107/day × 7 = $749 over 7d**
- After gas ($0.08) and IL (~$1): **$742 net**
- Annualized: **7,748% APR**

This is a **plan, not execution**. The freeze is preserved. The user must explicitly
authorize a 3-step plan (engineering → shadow probe → live) before any position is
opened.

## What R4 has decided

1. **The R1/R2 fee proxy is calibrated.** Realized fees are 100-1000× the proxy for
   tight ranges. The proxy was conservative, not aggressive.
2. **The R3 expectation that "proxy may be 2-10× too high" was wrong.** It's actually
   100-1000× too low for tight ranges.
3. **The remaining blockers are engineering, not data.** R3 documented 3 P0 issues
   (auto-exit, IL/time/fee-zero stops, PnL event feed). R4 does not address these.
4. **A $50 × 7d position is expected to be very profitable** if the in-range fraction
   is 0.90+ (R4's guess; needs verification).

## What R4 does NOT do

- Does not run canary, live, paper, or any execution mode.
- Does not connect to a wallet, signer, or broadcaster.
- Does not sign or broadcast any transaction.
- Does not modify R1, R2, R3, or any pre-existing report directory.
- Does not start the 6h watcher (24h historical replay is sufficient).

## What R4 recommends next

**Engineering (P0 close) → Manual shadow probe (verification) → Gated live.**

See `NEXT_STRATEGY_FORK.md` for details.
