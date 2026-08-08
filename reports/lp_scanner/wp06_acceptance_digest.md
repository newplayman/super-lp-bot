# LP Shadow Daily Digest — all history

_generated 2026-08-08T17:26:51.268706+00:00 · read-only/paper-only_

## Runner heartbeat

- Source: `reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/heartbeat.jsonl`
- Valid ticks: **2,154** (unique 2,154; malformed lines 0)
- Window: 2026-06-24T11:54:26.450337+00:00 → 2026-08-08T17:02:41.980052+00:00
- Portfolio net: $0.69 → $1,554.17; observed max drawdown $322.66
- Breach events: 35; last tick pools 6 (exited 3, active OOR 2)

## Scanner

- Source: `reports/lp_scanner/scanner.db`
- Latest atomic cycle: 2026-08-08T17:26:36.129879+00:00
- Snapshots: 736; opportunities 1 (accepted 0, rejected 1)
- Rejections: NETCOVER_INPUT_MISSING:fee_ev_usd,reward_ev_usd,il_ev_usd,entry_cost_usd,exit_cost_usd,gas_usd,slippage_usd,reward_conversion_cost_usd,exit_latency_loss_usd (1)

### Latest opportunities

| accepted | symbol | pool | expected net ($) | NetCover | rejection |
|---|---|---|---:|---:|---|
| no | WETH-CBBTC | 0xffa192f04b1e5f9f | — | — | NETCOVER_INPUT_MISSING:fee_ev_usd,reward_ev_usd,il_ev_usd,entry_cost_usd,exit_cost_usd,gas_usd,slippage_usd,reward_conversion_cost_usd,exit_latency_loss_usd |

## Safety

This digest reports shadow evidence only. It does not authorize or perform execution.
