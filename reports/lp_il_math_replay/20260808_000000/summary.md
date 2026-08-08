# WP-02 IL Math Replay

- Status: **PASS**
- Trajectories: 60 (6 real historical, 54 synthetic)
- Scenario distribution: `{'gap_through': 10, 'inside': 10, 'lower_breach': 10, 'sustained_trend': 10, 'upper_breach': 10, 'v_shape': 10}`
- Max inventory error: 1.1241070527e-12% (limit 0.1%)
- Max IL error: 5.68406109309e-11 bps of HODL NAV (limit 5.0)
- Real source: `/opt/lpbot/lp-bot-v3-origin-check/reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000/swap_events_0xb2cc22.jsonl`
- Sampling: streamed first 128 decoded swaps; six unmodified 8-event windows.
- Price convention: human token1 per token0; WETH/USDC source uses token0=18, token1=6 decimals.
- Safety: offline/read-only; no wallet, signing, broadcast, approve, or paid service.
