# R2 Baseline Review — R3

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R3_REAL_FEE_ACCRUAL_AND_EXIT_READINESS_V1`
**Run ID:** 20260611_073000
**R2 source:** `reports/strategy_evidence_r2_gas_reward_reprice/20260611_064703/`

## R2 top 3 candidates (carried into R3)

| Rank | Pool | Pair | Protocol | MVS × hold (R2) | Net @ 50×7d (R2) | R2 verdict |
|---|---|---|---|---|---|---|
| 1 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | WETH/USDC 0.05% | aerodrome-slipstream | $3 × 7d | +$0.62 | GO_TINY_LIVE (mechanical) |
| 2 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | WETH/USDC 0.01% | pancakeswap-v3-base | $3 × 7d | +$0.27 | GO_TINY_LIVE (mechanical) |
| 3 | 0xb775272e537cc670c65dc852908ad47015244eaf | WETH/USDC 0.05% | pancakeswap-v3-base | $10 × 7d | +$0.25 | GO_TINY_LIVE (mechanical) |

R2 final_recommendation: `NEED_MORE_DATA` (preserved from R1, with confidence upgrade).

## R2 R1→R2 decision diff (carried into R3)

- **Gas anchor**: R1 hand-estimate $0.30/cycle → R2 observed $0.0795/cycle (0.05 gwei). 3.8× cheaper.
- **MVS widening**: $25/$25/$50 (R1) → $3/$3/$10 (R2) due to better gas math.
- **Reward recovery**: Aerodrome Voter / CLNPM / Gauge addresses recovered; per-pool APR still unknown.
- **IL variance**: unchanged. signal-to-noise improved from 0.03-0.27 (R1) to 0.17-0.41 (R2) but still < 1.

## R3 question (from spec)

> R1/R2 fee proxy = `volume_h24 × fee_tier × position_share`. This is a 1st-order estimate. The
> real test is: what does a real LP position actually earn in fees over 7d, and is that number
> within 30% of the proxy? If the proxy is materially overestimated, the entire R1/R2 model
> collapses and `tiny live` is no longer on the table.
>
> R3 must also determine if the bot has an end-to-end auto-exit path; if not, `tiny live` is
> re-classified from "autonomous LP strategy" to "manual-supervised calibration probe".

## R3 approach

1. **Real position samples (Method 1)**: For each top pool, find recent Mint/IncreaseLiquidity
   events on the pool's NPM, read `positions(tokenId)` for the position struct
   (tickLower/tickUpper/liquidity/feeGrowthInside). Compare actual fees earned to the proxy
   over the observed window.

2. **Hypothetical position calibration (Method 2)**: If Method 1 is blocked, read
   `pool.slot0 / feeGrowthGlobal0X128 / feeGrowthGlobal1X128` directly via storage. Set
   hypothetical ticks [tick - N, tick + N] for the recommended range, compute L for $50
   notional, compute fees from feeGrowth delta.

3. **Exit readiness audit (Section C)**: Code-only audit of risk → close wiring, IL stop, time
   stop, fee-zero stop, kill switch, forced remove/collect, pnl accounting, position reconcile.

## R3 status (preview)

- Method 1: **BLOCKED** for PancakeSwap V3 (`0x03a520b3...`) — `positions(tokenId)` reverts;
  storage layout is non-canonical V3 (Algebra fork). For Aerodrome Slipstream, the
  `0x090b2a6b...` CLNPM has 0 mints in 1h window and 0 IncreaseLiquidity events.
- Method 2: **PARTIAL** — `pool.liquidity()` returns real values for all 3 pools. feeGrowth
  storage slots 1/2 do NOT match canonical V3 layout for PancakeSwap V3 / Aerodrome Slipstream
  (verified by checking slot values vs the expected `volume_24h * fee_tier * 7d` range). The
  proxy itself remains uncalibrated.
- Exit audit: **PARTIAL** — `OrderManager.Close(ExitIntent)` interface exists with a
  complete execution path (`StatusOpen → StatusExiting → StatusClosed`). The
  `defaultOrderManager.Close` runs the simulation path and updates status. **However, the
  risk-gate → forced close wiring is missing**: `RiskGate.Allow()` / `CheckDrawdown()` /
  `CheckVaR()` set kill flags but no loop ticker calls `OrderManager.Close` on kill. Manual
  kill via `RaiseKill()` also doesn't trigger close.
