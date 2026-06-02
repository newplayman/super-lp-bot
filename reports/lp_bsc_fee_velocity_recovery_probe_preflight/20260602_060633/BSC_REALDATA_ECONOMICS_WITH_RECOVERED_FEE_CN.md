# BSC PancakeSwap V3 economics preview (with recovered fee velocity)

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- run_id: `20260602_060633`
- row_count: `960`
- positive_proxy_count_total: `34`
- positive_proxy_count_realistic: `0`
- near_break_even_count: `394`
- confidence_adjusted_candidate_count: `0`
- pool_tvl_proxy_usd_assumed: `5000000` (heuristic)

## Best candidate (realistic scenario, fee_ready)

- pool: `0x172fcd41e0913e95784454622d1c3724f546f849`
- pair: `USDT/WBNB`
- fee_tier_raw: `100`
- notional_usd: `20`
- hold_window: `15m`
- net_ev_proxy_usd: `-0.015560`
- net_ev_proxy_pct: `-0.0778`

## Caveats

- Fee proxy uses a heuristic pool TVL = $5M (low/conservative) and pool-level fee, NOT actual position fee accrual. `actual_fee_ready = false`, `token_id_available = false`.
- IL/LVR is a scenario sweep, not an empirical estimate.
- USD prices are heuristic (WBNB=$600, USDC/USDT=$1) — refine with precise quote in v2 if needed.
- `confidence_adjusted_candidate_count` requires `fee_ready=true` for the chosen window AND the scenario being `realistic`/`conservative`. Low-confidence cells are excluded.

## Safety

```text
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
edge_proven            = no
actual_fee_ready       = false
token_id_available     = false
```
