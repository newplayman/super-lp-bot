# Position-Level Proof V1

| score_mode | horizon | position_count | future_position_count | terminal_position_count | invalid_position_count | win_rate | avg_net_pnl_pct | median_net_pnl_pct | p10_net_pnl_pct | p5_net_pnl_pct | p1_net_pnl_pct | top20_position_count | bottom20_position_count | top20_median | top20_p10 | top20_p5 | bottom20_median | bottom20_p10 | bottom20_p5 | top20_vs_bottom20_signal | future_only_signal | terminal_only_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_decision_score | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| open_decision_score | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| first_selected_score | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| first_selected_score | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| max_score_before_open | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| max_score_before_open | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |
| median_score_before_open | 6h | 32 | 6 | 26 | 3 | 0.812500 | 0.091572 | 0.014793 | -2.356639 | -2.531888 | -3.408496 | 7 | 7 | 0.115699 | -1.029461 | -1.786731 | 0.021239 | -3.031944 | -3.414419 | better | better | better |
| median_score_before_open | 24h | 30 | 1 | 29 | 3 | 0.833333 | 0.285648 | 0.014793 | -2.242177 | -2.454014 | -2.537614 | 6 | 6 | 1.052731 | -1.281884 | -1.912943 | 0.022667 | -2.446462 | -2.484220 | better | insufficient | better |

## Judgment

- decision_trace_level_better_survives_position_level = yes
- full_strategy_position_level_pass = no
- future_only_position_level_better = no
- terminal_only_position_level_24h = better
- position_level_tail_acceptable = no
