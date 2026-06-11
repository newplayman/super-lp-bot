# Next Strategy Fork — R3

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R3_REAL_FEE_ACCRUAL_AND_EXIT_READINESS_V1`
**Run ID:** 20260611_073000

## What R3 has closed vs R1/R2

| Open item | R1 status | R2 status | R3 status |
|---|---|---|---|
| Gas anchor (cycle cost) | unverified ($0.30 hand-est) | observed ($0.08) | re-confirmed ($0.08, not refuted) |
| Aerodrome Voter address | unknown | recovered (0xf33a96b...) | n/a (carried) |
| Aerodrome Gauge address | unknown | recovered (0x8279...b72) | n/a (carried) |
| Aerodrome CLNPM address | unknown | recovered (0x090b2a6b...) | n/a (carried) |
| Per-pool reward APR | unknown | partial (addresses only) | unchanged |
| IL variance | R1: ±$1-2 on 15% range | R2: same, but signal/noise improved | unchanged |
| Fee proxy calibration | unvalidated | unvalidated | **BLOCKED** (V3-fork storage) |
| Auto-exit wiring | n/a (assumed) | n/a (assumed) | **MISSING** (P0) |
| IL stop / time stop / fee-zero stop | n/a (assumed) | n/a (assumed) | **MISSING** (P0) |
| Live close path | n/a (frozen) | n/a (frozen) | code exists, untested |

## The forking point: fee-only vs probe-driven

R3 is the forking point. The two paths diverge:

### Path A: fee-only tiny live (current R1/R2 path)

- Reuse the R1/R2 fee proxy as the model's expected income.
- Open a $50 × 7d position on top 1, 2, or 3 candidate.
- Auto-close on risk verdict (P0 wiring).
- Net expected: $0.25-$0.62 per position over 7d.
- **Risk**: if the proxy is wrong by 2×, the position is unprofitable after gas.
  And there is no auto-exit if IL variance blows up.

### Path B: probe-driven calibration (R3's recommendation)

- Open a $50 × 7d position with **a human operator** monitoring.
- Subscribe to all `Swap` events on the pool and log them.
- At the end of 7d, close (manually) and compute the realized fee from on-chain
  `feeGrowthInside0LastX128` / `feeGrowthInside1LastX128` (after the
  protocol-specific ABI is recovered) or from the swap events.
- Use the realized fee to calibrate the R1/R2 proxy.
- Then re-evaluate `GO_TINY_LIVE` (or `NO_GO`) on calibrated data.

**R3 recommends Path B** because:
1. The fee proxy is the largest single uncertainty. Path A ignores it.
2. The auto-exit wiring is missing. Path A assumes it.
3. The cost of a $50 × 7d manual probe is small ($0.50 gas + opportunity cost)
   compared to the value of ground-truth fee data.

## R4 (next stage) — recommend probe execution with on-chain event capture

If the user authorizes a tiny manual probe, R4 should:

1. **Open a $50 × 7d position on pool 0xb2cc... (Aerodrome Slipstream WETH/USDC 0.05%)**
   using the existing shadow mode (no live execution; this is a shadow test).
2. **Subscribe to `Swap` events on the pool** for 7 days, logging the volume per
   swap, the price before/after, and the cumulative feeGrowth.
3. **At the end of 7d, close the position** (still in shadow mode).
4. **Calibrate the R1/R2 proxy**:
   - Compute the realized fee from `feeGrowthInside0LastX128` deltas
     (requires Aerodrome Slipstream ABI; recover from `0x090b2a6b...` bytecode or
     Goldsky).
   - Compute the realized IL from start/end tick.
   - Compute the realized gas from tx receipts.
   - Compare to the R2 expected_net of $0.62.
5. **Re-evaluate R1/R2/R3 with calibrated data** and produce R4 verdict.

R4 would be the first stage to give us ground-truth fee data. It also tests the
close path end-to-end (in shadow mode), which is the second-largest unknown.

## What R4 is NOT

- R4 is NOT a live execution. The freeze is preserved; the probe runs in shadow
  mode (`-tags=shadow`) which simulates but does not broadcast.
- R4 is NOT autonomous. A human operator is required to start the probe, monitor
  the run, and stop it at the end of 7 days. (Or the existing scheduler can be
  used to stop it automatically, with a confirmation step.)
- R4 is NOT a calibration of reward APR. The Aerodrome gauge reward is still
  unknown; the R2 reward_data_available=partial is unchanged.

## Why probe first, then maybe live

- A $50 × 7d shadow probe costs $0.50 in gas (one cycle), $0 in opportunity cost
  (the position is simulated), and gives us ground-truth fee data.
- If the probe shows realized fees of $0.50-0.70 over 7d, the proxy is correct
  and the R1/R2 model's expected_net is reliable. Then we can consider live with
  the auto-exit wiring added.
- If the probe shows realized fees of $0.05-0.15 over 7d, the proxy overestimates
  by 4-12×. Then the $50 × 7d band is gas-negative and the whole fee-only path
  is no-go.

This is the cheapest possible path to ground truth.

## STOP conditions

Per the R3 spec: "如果 R2 cannot promote to high-confidence GO_TINY_LIVE, stop,
don't tiny-live." R2's `NEED_MORE_DATA` is preserved. R3 cannot promote to
`GO_TINY_LIVE` either. Therefore the freeze is preserved and no live execution
is authorized. The probe (R4) is shadow-mode only and requires explicit user
authorization to start.

If the user wants to proceed:

1. **Authorize R4 shadow probe** (this is a human decision).
2. **R4 runs for 7 days** in shadow mode, logs all Swap events, computes realized fee.
3. **R4 re-evaluates** with calibrated data and produces a final verdict.

If the user does not want to proceed, the freeze remains in place and no further
stage is run.
