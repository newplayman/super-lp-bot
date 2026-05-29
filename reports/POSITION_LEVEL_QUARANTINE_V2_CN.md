# Position-Level Quarantine V2

| scenario | horizon | position_count | terminal_share | median | p10 | p5 | p1 | win_rate | top20_vs_bottom20_signal | full_strategy_signal | terminal_signal | future_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline position-level proof | 6h | 32 | 0.8125 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 0.812500 | better | better | better | better |
| baseline position-level proof | 24h | 30 | 0.9667 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 0.833333 | better | better | better | insufficient |
| exclude worst 1 position | 6h | 31 | 0.8065 | 0.021239 | -2.227870 | -2.446462 | -3.414419 | 0.838710 | better | better | better | better |
| exclude worst 1 position | 24h | 29 | 0.9655 | 0.021239 | -0.461388 | -2.313716 | -2.479689 | 0.862069 | better | better | better | insufficient |
| exclude worst 3 positions | 6h | 29 | 0.7931 | 0.034862 | -0.003929 | -1.344629 | -3.357567 | 0.896552 | better | better | better | better |
| exclude worst 3 positions | 24h | 27 | 0.9630 | 0.024095 | 0.000051 | -0.013828 | -1.653763 | 0.925926 | better | better | better | insufficient |
| exclude worst 5 positions | 6h | 27 | 0.7778 | 0.058301 | 0.000067 | 0.000041 | -2.809693 | 0.962963 | better | better | better | better |
| exclude worst 5 positions | 24h | 25 | 0.9600 | 0.034862 | 0.000142 | 0.000065 | 0.000039 | 1.000000 | better | better | better | insufficient |
| exclude worst 1 pool | 6h | 27 | 0.8148 | 0.008347 | -2.285100 | -2.476669 | -3.465415 | 0.851852 | better | better | better | insufficient |
| exclude worst 1 pool | 24h | 26 | 0.9615 | 0.014793 | -1.113919 | -2.335177 | -2.484220 | 0.884615 | better | better | better | insufficient |
| exclude worst 3 pools | 6h | 13 | 0.7692 | 0.000779 | -1.782290 | -2.855479 | -3.608610 | 0.846154 | better | better | better | insufficient |
| exclude worst 3 pools | 24h | 13 | 0.9231 | 0.000845 | 0.000038 | -0.891129 | -1.960522 | 0.923077 | better | better | better | insufficient |
| exclude positions with decision_trace_count > p95 | 6h | 30 | 0.8000 | 0.014793 | -2.386049 | -2.534091 | -3.433554 | 0.800000 | better | better | better | better |
| exclude positions with decision_trace_count > p95 | 24h | 28 | 0.9643 | 0.014793 | -2.270793 | -2.469117 | -2.538055 | 0.821429 | better | better | better | insufficient |
| exclude pools with terminal p10 < threshold | 6h | 11 | 0.7273 | 0.000845 | 0.000031 | -1.898431 | -3.417201 | 0.909091 | better | better | better | insufficient |
| exclude pools with terminal p10 < threshold | 24h | 11 | 0.9091 | 0.024095 | 0.000064 | 0.000048 | 0.000034 | 1.000000 | better | better | better | insufficient |
| future-only / no-terminal counterfactual | 6h | 6 | 0.0000 | 0.083446 | -1.898411 | -2.847652 | -3.607045 | 0.833333 | better | better | insufficient | better |
| future-only / no-terminal counterfactual | 24h | 1 | 0.0000 | 1.834137 | 1.834137 | 1.834137 | 1.834137 | 1.000000 | insufficient | insufficient | insufficient | insufficient |
