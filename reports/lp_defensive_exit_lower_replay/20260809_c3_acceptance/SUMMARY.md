# C3 Real Historical Lower-Breach Exit Replay

Result: **PASS**; 3 lower breaches, 1 gap-through.

Source: `reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000/swap_events_decoded.csv` (`6b70c073a0c3d31fcf562eff33954af78fd9674d4df80fce006e2e2bd38a7c03`), 3000 decoded real swaps.

Paper/read-only only: no wallet, signing, approval, or broadcast.

| Scenario | Lower/gap | Mode | Quote result | Post risky | Cost model vs actual | Result |
|---|---|---|---|---:|---:|---|
| Aerodrome Slipstream WETH/USDC 0.05% | LOWER/False | REMOVE_TO_STABLE | PASS | 0.25 | -20.88% | PASS |
| PancakeSwap V3 WETH/USDC 0.01% | LOWER/False | REMOVE_TO_STABLE | PASS | 0.25 | -1.24% | PASS |
| PancakeSwap V3 WETH/USDC 0.05% | LOWER/True | REMOVE_TO_STABLE | slippage_limit | 1.00 | -0.27% | PASS |

The Aerodrome cost model under-estimates the selected first reliable post-breach fill by about 21%; this is explicitly retained as a calibration warning.
