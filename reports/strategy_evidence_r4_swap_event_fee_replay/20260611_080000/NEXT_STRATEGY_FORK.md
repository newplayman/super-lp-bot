# Next Strategy Fork — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000

## R1 → R2 → R3 → R4 decision tree (closed)

| Stage | Question | Answer |
|---|---|---|
| R1 | Are there 3 pools where $50 × 7d is gas-positive? | YES (mechanical) |
| R2 | Is the R1 gas anchor ($0.30) real? | NO; real is $0.08 |
| R3 | Is the R1 fee proxy correct? | UNCALIBRATED (V3-fork storage mismatch) |
| R4 | What does real Swap data show? | Proxy is conservative; realized fees are 100-1000× the proxy |

R1/R2/R3/R4 together establish:

- $50 × 7d positions on 0xb2cc..., 0x72ab..., 0xb775... are **strongly positive** under
  tight-range assumptions.
- IL variance is real but small relative to fees.
- Gas is $0.08/cycle at 0.05 gwei (R2 anchor not refuted by R4).
- The remaining blockers are **engineering** (auto-exit wiring, IL/time/fee-zero stops,
  PnL event subscription), not data.

## What comes next

The R4 spec leaves the next fork open. Three plausible options:

### Option A: Engineering stage (P0 close)

Write the missing code:

- Auto-exit wiring (50-100 lines of Go): ticker reads `RiskGate.GetState()` every 1m,
  walks open positions, calls `OrderManager.Close(positionID)` on `KillLevelKill`.
- IL stop (30 lines): position out of range triggers close.
- Time stop (30 lines): position held > 7d triggers close.
- Fee-zero stop (30 lines): no fees for 24h triggers close.
- PnL Swap-event subscription (100 lines): use existing event listener to feed `AccrueFees`.

Estimated effort: 1 engineer × 3-5 days. Then re-run R3's exit audit, expect P0 to P1.

### Option B: Manual probe (verification)

Run a $50 × 7d shadow position on 0xb2cc... in shadow mode. The shadow mode **does not
mint a real LP NFT** but it does simulate the entry/exit/fee accounting. After 7d, check
if the simulated fees match the R4 replay's prediction of $108/day.

This would validate the in-range fraction assumption (R4's 0.95 for ±10% is a guess).

Estimated effort: 1 engineer × 1 day to set up the shadow run, then 7d wait, then 1
day to verify.

### Option C: Real $50 × 7d live (with manual supervision)

This is the most aggressive next step. Requires:

- User explicitly opens the freeze for a single $50 × 7d position
- Human operator monitors every 4-6h
- Auto-exit wiring is in place (Option A) OR operator manually closes on risk
- Pre-set abort conditions: pool TVL drops below $5M; volume drops below $50M; ETH
  price moves >5% during the 7d window

R4 does NOT recommend this without first doing Option A or B.

## What R4 recommends

**Option A → Option B → (gated) Option C.**

1. Close the P0 engineering work (Option A). This unblocks the autonomous-tiny-live path.
2. Verify the in-range fraction with a 7d shadow probe (Option B). This validates R4's
   in_range_fraction assumption.
3. If A and B succeed, the user can decide whether to authorize a single $50 × 7d live
   position (Option C) with manual supervision. This is **not** autonomous; it requires
   the human operator to monitor.

If A and B both succeed and the shadow probe shows in-range fraction ≥ 0.90, R5 (a
new research stage) would re-evaluate the recommendation and possibly upgrade to a
`GO_TINY_LIVE` (autonomous) recommendation.

## Hard STOP conditions

Per the R4 spec, R4 stops at the recommendation and does NOT initiate any of the 3
options. The user must explicitly authorize each step.

The freeze is preserved. No canary, no live, no paper, no Mode B.
