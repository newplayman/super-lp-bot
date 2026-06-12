# Next Strategy Fork — R4B

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4B_ACTIVE_LIQUIDITY_CORRECTED_FEE_REPLAY_V1`
**Run ID:** 20260612_090000

## R1 → R2 → R3 → R4 → R4B decision tree (closed)

| Stage | Question | Answer |
|---|---|---|
| R1 | Are there 3 pools where $50 × 7d is gas-positive? | YES (mechanical) |
| R2 | Is R1's gas anchor ($0.30) real? | NO; real is $0.08 |
| R3 | Is R1's fee proxy correct? | UNCALIBRATED (V3-fork storage mismatch) |
| R4 | What does real Swap data show? | Proxy is conservative; realized fees 100-1000× proxy |
| **R4B** | **Is R4's formula rigorous? Use L_event as denominator** | **Numerically equivalent (correction factor 0.94-1.00). R4 was approximately right.** |

R4B closes the active-liquidity denominator concern. The 81-cell matrix is
re-validated with the corrected formula.

## What comes next

The R4B spec says: "不允许进入 tiny live plan" (cannot enter tiny live plan).
R4B's `NEED_MORE_DATA` recommendation blocks any further action.

### Path A: Multi-day R5 replay (read-only, no execution)

A 7d or 30d swap event replay would smooth out the variance and give a tighter
estimate. The R4 spec's `R4B` is read-only and would not require the user's
authorization for a 7d replay (just an extended time window).

Estimated effort: 1 engineer × 1 day (script re-run with 7d window).

### Path B: Manual shadow probe (verification)

Run a $50 × 7d shadow position on 0xb2cc... in shadow mode. Shadow mode does not
mint a real LP NFT but does simulate the entry/exit/fee accounting. After 7d, check
if the simulated fees match the R4B replay's prediction of $120/day (for ±10% range).

**Note**: R4B's policy disallows this. The user said "不允许进入 tiny live plan" and
"不允许 live/canary/paper". A shadow probe is not live, but the user may still
disallow it as a process step.

### Path C: Engineering stage (P0 close)

Write the missing code:
- Auto-exit wiring (50-100 lines of Go)
- IL stop, time stop, fee-zero stop (30 lines each)
- PnL Swap-event subscription (100 lines)

**Note**: R4B's policy disallows this. The user said "不允许写 auto-exit 工程".

## R4B's recommendation

`NEED_MORE_DATA` with a clear path forward:

1. **Multi-day replay (Path A)**: 7d swap event replay to validate the 24h sample.
   This is the cheapest path to a higher-confidence answer.
2. **Then revisit the recommendation**. If the 7d replay confirms the 24h result,
   the recommendation can be upgraded.

If the 7d replay diverges significantly from the 24h, R4B's `NEED_MORE_DATA` is the
correct verdict.

## Hard STOP conditions

Per the R4B spec, R4B stops at the recommendation and does NOT initiate any of the
3 paths. The user must explicitly authorize each step.

The freeze is preserved. No canary, no live, no paper, no Mode B.
