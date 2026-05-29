# Tier C Counterfactual OOS

- research_universe_count: 4
- research_position_count: 372
- oos_result_count: 1860
- methodology: read-only counterfactual position_lifecycle built from Tier C research-universe traces deduped by pool+hour bucket, with 10/20/50 USD entry sizes and 15m/30m/1h/2h/6h horizons.
- price path: GeckoTerminal 5m OHLCV on local network path; fee and slippage are research-only estimates.

| horizon | entry_size_usd | research_position_count | completed_count | invalid_count | median_net_pnl_pct | p10 | p5 | p1 | win_rate | exit_depth_fail_count | data_quality_fail_count | top_loss_pool | top_positive_pool |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15m | 10.00 | 124 | 124 | 0 | -0.000414 | -0.014342 | -0.026682 | -0.032035 | 0.459677 | 0 | 75 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 15m | 20.00 | 124 | 124 | 0 | -0.000425 | -0.014361 | -0.026701 | -0.032205 | 0.451613 | 0 | 75 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 15m | 50.00 | 124 | 124 | 0 | -0.000461 | -0.014871 | -0.026758 | -0.032716 | 0.451613 | 0 | 75 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 30m | 10.00 | 124 | 120 | 4 | -0.000409 | -0.018824 | -0.023977 | -0.034332 | 0.483333 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 30m | 20.00 | 124 | 120 | 4 | -0.000424 | -0.018843 | -0.024147 | -0.034351 | 0.483333 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 30m | 50.00 | 124 | 120 | 4 | -0.000471 | -0.018900 | -0.024658 | -0.034408 | 0.483333 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa |
| 1h | 10.00 | 124 | 120 | 4 | -0.000010 | -0.024322 | -0.037878 | -0.041870 | 0.500000 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 1h | 20.00 | 124 | 120 | 4 | -0.000025 | -0.024424 | -0.037897 | -0.041889 | 0.500000 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 1h | 50.00 | 124 | 120 | 4 | -0.000072 | -0.024439 | -0.037954 | -0.041946 | 0.500000 | 0 | 76 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 2h | 10.00 | 124 | 112 | 12 | -0.000192 | -0.025746 | -0.045062 | -0.070009 | 0.491071 | 0 | 78 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 2h | 20.00 | 124 | 112 | 12 | -0.000204 | -0.025765 | -0.045068 | -0.070179 | 0.491071 | 0 | 78 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 2h | 50.00 | 124 | 112 | 12 | -0.000240 | -0.025822 | -0.045083 | -0.070690 | 0.491071 | 0 | 78 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 6h | 10.00 | 124 | 97 | 27 | -0.003040 | -0.050838 | -0.062995 | -0.092339 | 0.432990 | 0 | 82 | 0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 6h | 20.00 | 124 | 97 | 27 | -0.003059 | -0.050857 | -0.063014 | -0.092358 | 0.432990 | 0 | 82 | 0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |
| 6h | 50.00 | 124 | 97 | 27 | -0.003116 | -0.050914 | -0.063071 | -0.092415 | 0.432990 | 0 | 82 | 0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830 | 0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf |