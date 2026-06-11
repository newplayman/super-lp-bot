# Tiny-Live Reclassification — R3

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R3_REAL_FEE_ACCRUAL_AND_EXIT_READINESS_V1`
**Run ID:** 20260611_073000
**Reclassified at:** 2026-06-11T07:30:00Z (UTC)

## R3 final_recommendation: `CALIBRATION_PROBE_ONLY`

R3 cannot promote any of the 3 R2 top candidates to `GO_TINY_LIVE` (autonomous) and
cannot promote to `NO_GO` or `STOP_FEE_ONLY_TINY_LIVE_PATH` either. The honest answer
is **`CALIBRATION_PROBE_ONLY`**: a manually-supervised $50 probe could scientifically
calibrate the fee model and prove the wiring, but it would not be an autonomous LP
strategy.

## R3 decision rules (from spec)

### `GO_TINY_LIVE` (autonomous) — REQUIRED conditions

| Condition | Met? | Why |
|---|---|---|
| fee proxy not materially overestimated by R3 calibration | **NO** | R3 fee calibration is BLOCKED (V3-fork storage layout mismatch). Proxy is uncalibrated. |
| expected_net / IL_stddev >= 1 (or hedge) | NO | R2 says 0.17-0.41; same as R1, no hedge. |
| exit path can close position automatically | **NO** | P0: no ticker reads risk state and calls `OrderManager.Close`. |
| fee/gas/PnL accounting can verify result | **NO** | P1: no `Swap` event subscription feeding `AccrueFees`. |
| no P0/P1 live execution blocker | **NO** | 4 P0 + 6 P1 blockers from the exit audit. |
| max size <= 50 USDC | YES | R2 MVS=$3/$3/$10; R3 reuses $50 cap. |
| hold <= 7d | YES | R2 hold=7d. |

**Verdict: NOT GO_TINY_LIVE.**

### `CALIBRATION_PROBE_ONLY` — REQUIRED conditions

| Condition | Met? | Why |
|---|---|---|
| fee calibration still uncertain | YES | R3 calibration is BLOCKED. |
| edge thin (signal/noise < 1) | YES | R2 signal/noise = 0.17-0.41. |
| exit path incomplete | YES | P0 wiring missing. |
| but a $50 probe could scientifically calibrate fee model | YES | Real position with on-chain Swap event log would give ground truth. |
| must be manual-supervised | YES | No auto-exit; human must invoke Close. |

**Verdict: CALIBRATION_PROBE_ONLY.**

### `STOP_FEE_ONLY_TINY_LIVE_PATH` — REJECTED

This category applies if the fee proxy appears materially overestimated. **R3 cannot
confirm or refute the proxy** (calibration is BLOCKED). The proxy is uncalibrated,
not known-bad. Therefore `STOP_FEE_ONLY_TINY_LIVE_PATH` is not appropriate. If the
spec is read strictly, the unknown status is closer to `NEED_MORE_DATA` than to
`STOP_*`.

### `NEED_MORE_DATA` — R1/R2 verdict preserved

R1 final_recommendation: `NEED_MORE_DATA`. R2 final_recommendation: `NEED_MORE_DATA`
(with confidence upgrade). R3's `CALIBRATION_PROBE_ONLY` is essentially a refinement
of `NEED_MORE_DATA` with a concrete action: a $50 manual probe with on-chain Swap event
capture. After the probe, the fee model can be calibrated and the recommendation
upgraded to either `GO_TINY_LIVE` (if proxy is correct) or `STOP_FEE_ONLY_*` (if
proxy overestimates).

## R3 final_recommendation details

```json
{
  "final_recommendation": "CALIBRATION_PROBE_ONLY",
  "max_probe_size_usdc": 50,
  "max_hold_days": 7,
  "mode": "shadow OR manual-supervised-live (NOT autonomous)",
  "human_required": true,
  "human_actions": [
    "Pre-position: read pool.state (slot0, liquidity) and confirm tick range ±2%",
    "Pre-position: capture expected fee from R1/R2 model",
    "Open: invoke OrderManager.Open manually or via CLI; capture tx hash and tokenId",
    "During hold: subscribe to Swap events on the pool (RPC), log each swap",
    "On risk verdict: invoke OrderManager.Close manually (no auto-close)",
    "Post-close: read position.feeGrowthInside0LastX128 / 1LastX128 to compute actual fees",
    "Post-close: collect + burn via OrderManager"
  ],
  "calibration_outputs": [
    "actual_fee_usd over 7d (from on-chain feeGrowth deltas, requires protocol ABI)",
    "il_usd over 7d (from start/end tick + token amounts)",
    "gas_usd (from tx receipts)",
    "net_pnl_usd (actual fee - IL - gas)",
    "compare to R2 expected_net = $0.62 (R2 model)"
  ]
}
```

## What R3 specifically changes vs R2

- R2 said `NEED_MORE_DATA` because of IL variance + reward data unknown.
- R3 confirms that even if R2's gas anchor and reward recovery are correct, **the
  fee proxy is uncalibrated** and the **auto-exit path is missing**. So R2's
  `NEED_MORE_DATA` was actually under-stating the gap.
- R3's reclassification `CALIBRATION_PROBE_ONLY` is the new honest answer: a
  $50 probe with a human operator is the cheapest path to ground-truth fee
  data + ground-truth close execution.
- The bot cannot be promoted to autonomous `GO_TINY_LIVE` until the auto-exit
  wiring (P0) and the fee proxy calibration (P0 — needs protocol ABI) are both
  resolved.

## What would change the recommendation

- **Auto-exit wiring**: a single goroutine that reads `RiskGate.GetState()` every
  TickInterval and calls `OrderManager.Close(positionID)` for each open position
  with `state.Level == KillLevelKill`. Estimated effort: ~50 lines of Go. Then
  R3's exit audit goes from P0 to P1.
- **Protocol-specific ABI for feeGrowth**: an `AerodromeSlipstreamStateReader` and
  a `PancakeSwapV3AlgebraStateReader` that decode the state struct. Estimated
  effort: ~200 lines of Go (or Python, for off-line calibration). Then R3's
  fee calibration goes from BLOCKED to PASS.
- **Reward data recovery** (R2's `partial` state): full recovery of per-pool
  reward APR from the Aerodrome Goldsky URL or via gauge bytecode analysis.
  Estimated effort: ~30 min of analyst time (per R2's recommendation).
- **cbBTC re-classification** (R1's open): a model call, not a data call.

If auto-exit wiring + feeGrowth ABI are both completed, R4 could realistically
re-classify the 3 top candidates to `GO_TINY_LIVE` at $50 × 7d with
`signal_to_noise > 1` (the open question: is the proxy within 30% of realized?).
