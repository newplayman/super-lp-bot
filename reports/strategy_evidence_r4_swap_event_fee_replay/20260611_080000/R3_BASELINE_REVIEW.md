# R3 Baseline Review — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000
**R3 source:** `reports/strategy_evidence_r3_real_fee_exit_readiness/20260611_073000/`

## R3 top 3 pools (carried into R4)

| Rank | Pool | Pair | Protocol | MVS × hold (R3) | Net @ 50×7d (R3) | R3 verdict |
|---|---|---|---|---|---|---|
| 1 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | WETH/USDC 0.05% | aerodrome-slipstream | $3 × 7d | +$0.62 (R2 model) | CALIBRATION_PROBE_ONLY |
| 2 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | WETH/USDC 0.01% | pancakeswap-v3-base | $3 × 7d | +$0.27 (R2 model) | CALIBRATION_PROBE_ONLY |
| 3 | 0xb775272e537cc670c65dc852908ad47015244eaf | WETH/USDC 0.05% | pancakeswap-v3-base | $10 × 7d | +$0.25 (R2 model) | CALIBRATION_PROBE_ONLY |

R3 final_recommendation: `CALIBRATION_PROBE_ONLY`. The expected_net numbers ($0.62, $0.27, $0.25) are from the R1/R2 fee proxy, which R3 explicitly called **uncalibrated** because the V3-fork storage layout mismatch prevents direct on-chain feeGrowth probing.

## R3 R1→R2→R3 decision diff (carried into R4)

- **R1**: $0.30/cycle gas hand-estimate, $0.04-$0.40 expected net at $50×7d, IL variance dominates, `NEED_MORE_DATA`.
- **R2**: $0.08/cycle gas observed on-chain, $0.25-$0.62 expected net at $50×7d, Aerodrome Voter/CLNPM/Gauge addresses recovered, `NEED_MORE_DATA` (with confidence upgrade).
- **R3**: fee proxy uncalibrated by direct feeGrowth probe (V3-fork storage mismatch). Exit-readiness audit: P0 auto-exit wiring missing; P0 IL/time/fee-zero stops missing; P1 approve revocation not invoked in live close; P1 PnL Swap-event subscription missing. Recommendation: `CALIBRATION_PROBE_ONLY` (a $50 × 7d shadow probe with manual supervision).

## R4 question (from spec)

R4 takes the next step: instead of trying to read feeGrowth directly from storage (which R3 proved is blocked for V3 forks), R4 reads **real Swap events** from each pool and computes the realized volume + fees over 24h, then uses the Swap event log to **replay** what a hypothetical $X position with ±R% range would have earned.

> "对 R2 Top 3 池，过去/未来 24h 的真实 Swap events 能否支持 R2 fee proxy？"

## R3 audit corrections (carried into R4)

The R3 report correctly noted:

1. **fee proxy uncalibrated** by R3 — R4 attempts to calibrate via Swap event replay.
2. **auto-exit wiring missing** — R4 does NOT touch this. The auto-exit is still a P0 for autonomous live. R4's recommendation is a **plan**, not execution.
3. **IL stop / time stop / fee-zero stop missing** — R4 notes these as still P0.
4. **PnL swap-event feed missing** — R4 PARTIALLY closes this by demonstrating how to subscribe to Swap events externally. The bot itself does not have this subscription, but the data is available.

## R4 watch-out: shadow open is not real

R3's recommendation to "open a $50 × 7d position in shadow mode" was misleading. R4 spec corrects: **shadow mode does not mint an LP NFT and does not produce on-chain fee accrual**. The correct approach is read-only Swap event capture + hypothetical LP fee replay. R4 follows this approach.

## R4 deliverables

- `swap_event_abi_probe.md` — confirmed topic hashes for each pool
- `swap_events_raw.jsonl` — raw event logs (concatenated from 24h)
- `swap_events_decoded.csv` — decoded amount0/amount1/sqrtPriceX96/liquidity/tick
- `historical_24h_swap_replay.csv` / `.jsonl` — per-pool 24h stats
- `hypothetical_lp_fee_replay_matrix.csv` / `.jsonl` — 81-cell matrix
- `FEE_PROXY_CALIBRATION_DECISION.md` — what R4 learned about the proxy
- `WATCHER_DECISION.md` — whether to start the 6h watcher
- `TINY_LIVE_DECISION.md` — final tiny-live verdict
- `NEXT_STRATEGY_FORK.md` — what comes after R4
- `FINAL_VERDICT.json` — structured summary
