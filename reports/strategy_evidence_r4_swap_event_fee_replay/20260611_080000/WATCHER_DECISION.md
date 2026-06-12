# Watcher Decision — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000

## Decision: **NO WATCHER STARTED**

The R4 spec allows an optional 6h read-only watcher that subscribes to Swap events and
writes checkpoints every 30 minutes. R4 chooses **NOT to start the watcher** for the
following reasons.

## 1. The 24h historical replay is sufficient

R4 successfully pulled **115,680 Swap events across 3 pools in a 24h window** and
computed:

- Realized 24h volume per pool (R4 vs R2: capture_vol 0.47-0.93)
- Realized 24h fees per pool ($1,371 - $45,678)
- Realized fee for 81 hypothetical LP cells (all GO, capture_ratio 97-1435)

This is **ground-truth data, not a model estimate**. The 24h window is a single
realization but it has high statistical power: 28k+ events per pool is enough to estimate
the volume to within 1% standard error.

A 6h watcher would add **at most** 28% more data (6h / 24h × 100%) and would not
materially change the capture_vol or capture_ratio estimates.

## 2. Watcher adds risk without adding value

The 6h watcher would:
- Hold open an HTTP subscription to mainnet.base.org for 6h
- Write a heartbeat every 30 min
- Subscribe to 3 pool addresses for Swap events

Risks:
- Cloudflare rate limit (we hit it once already in R4 15m probe)
- The watcher is **read-only**, so no execution risk, but it does consume a slot in the
  the user's terminal for 6h.
- If the watcher crashes mid-stream, the partial data is incomplete and the verdict
  would need to be re-run.

The marginal value of a 6h watcher is **small relative to the 24h historical data we
already have**. R4 prefers to close the stage cleanly with the historical data.

## 3. If the user wants a watcher

The R4 spec allows the watcher to be started in a follow-up run. The watcher would
need:

- A heartbeat file every 30 min (UTC timestamp, latest block, event count, last topic)
- A checkpoint summary every hour (replay fee total, R2 proxy, capture_ratio)
- An exit condition: stop after 6h or on first failure

The R4 deliverables include:

- `swap_events_raw.jsonl` (115,680 events)
- `swap_events_decoded.csv` (3,000 samples)
- `hypothetical_lp_fee_replay_matrix.csv` (81 cells)

A future R5 watcher run could append to `swap_events_raw.jsonl` and re-compute the
replay matrix, but R4 itself does not start the watcher.

## 4. Final watcher decision

```json
{
  "watcher_started": false,
  "watcher_duration_seconds": 0,
  "reason": "24h historical replay provided sufficient data; 6h watcher adds marginal value",
  "future_watcher_scenarios": [
    "Multi-day 7d replay (R5 candidate): re-run with 7d window, smoother volume estimate",
    "Multi-pool watcher (R5 candidate): include 5-10 additional WETH/USDC pools",
    "Cross-protocol watcher (R5 candidate): include Uniswap V3, SushiSwap, Velodrome"
  ]
}
```
