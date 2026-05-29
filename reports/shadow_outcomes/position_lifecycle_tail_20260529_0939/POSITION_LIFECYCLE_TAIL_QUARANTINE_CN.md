# Position Lifecycle Tail Quarantine Sensitivity

Proof-layer simulation only. No strategy parameters were changed.

| scenario | horizon | position_count | terminal_position_count | future_position_count | median | p10 | p5 | p1 | win_rate | top20_vs_bottom20_signal | full_strategy_signal | terminal_signal | future_signal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| baseline position-level proof | 24h | 33 | 29 | 1 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 0.833333 | better | better | better | insufficient |
| baseline position-level proof | 6h | 35 | 26 | 6 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 0.812500 | better | better | better | better |
| exclude terminal positions | 24h | 4 | 0 | 1 | 1.834137 | 1.834137 | 1.834137 | 1.834137 | 1.000000 | better | better | insufficient | insufficient |
| exclude terminal positions | 6h | 9 | 0 | 6 | 0.083446 | -1.898411 | -2.847652 | -3.607045 | 0.833333 | better | better | insufficient | better |
| exclude worst 1 pool | 24h | 28 | 27 | 1 | 0.022667 | -0.725122 | -2.469117 | -2.538055 | 0.857143 | better | better | better | insufficient |
| exclude worst 1 pool | 6h | 34 | 26 | 5 | 0.021239 | -2.227870 | -2.446462 | -2.537394 | 0.838710 | better | better | better | worse |
| exclude worst 1 position | 24h | 32 | 28 | 1 | 0.021239 | -0.461388 | -2.313716 | -2.479689 | 0.862069 | better | better | better | insufficient |
| exclude worst 1 position | 6h | 34 | 26 | 5 | 0.021239 | -2.227870 | -2.446462 | -2.537394 | 0.838710 | better | better | better | worse |
| exclude worst 10 positions | 24h | 23 | 19 | 1 | 0.245125 | 0.007158 | 0.006842 | 0.002044 | 1.000000 | better | better | better | insufficient |
| exclude worst 10 positions | 6h | 25 | 18 | 4 | 0.112145 | 0.007158 | 0.001160 | 0.000793 | 1.000000 | better | better | better | worse |
| exclude worst 3 pools | 24h | 15 | 14 | 1 | 0.024095 | -0.011849 | -0.777038 | -2.190608 | 0.866667 | better | better | better | insufficient |
| exclude worst 3 pools | 6h | 26 | 22 | 4 | 0.028051 | -0.009869 | -1.783152 | -2.500737 | 0.884615 | better | better | better | worse |
| exclude worst 3 positions | 24h | 30 | 26 | 1 | 0.024095 | 0.000051 | -0.013828 | -1.653763 | 0.925926 | better | better | better | insufficient |
| exclude worst 3 positions | 6h | 32 | 24 | 5 | 0.034862 | -0.003929 | -1.344629 | -2.330885 | 0.896552 | better | better | better | worse |
| exclude worst 5 positions | 24h | 28 | 24 | 1 | 0.034862 | 0.000142 | 0.000065 | 0.000039 | 1.000000 | better | better | better | insufficient |
| exclude worst 5 positions | 6h | 30 | 22 | 5 | 0.058301 | 0.000067 | 0.000041 | -0.014620 | 0.962963 | better | better | better | worse |
| future-only fixed-horizon subset | 24h | 1 | 0 | 1 | 1.834137 | 1.834137 | 1.834137 | 1.834137 | 1.000000 | better | better | insufficient | insufficient |
| future-only fixed-horizon subset | 6h | 6 | 0 | 6 | 0.083446 | -1.898411 | -2.847652 | -3.607045 | 0.833333 | better | better | insufficient | better |

## Interpretation

- This checks whether tail risk is dominated by a few positions or pools.
- future-only fixed-horizon remains a hypothesis line, not the current strategy.
