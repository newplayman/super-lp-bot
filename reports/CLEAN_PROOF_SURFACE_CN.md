# Clean Proof Surface v1

- source: `shadow_outcome_labels_repaired_terminal_v1`
- rule:
  - `entry_trusted = true`
  - `outcome_type in (future_position_mark, terminal_exit_mark)`
  - `mark_source != pool_mark_only`
  - `terminal_value_usd > 0 if terminal_exit_mark`
  - `net_pnl_pct calculable`
  - `invalid_reason not in (entry_untrusted, terminal_value_zero_bug, pool_mark_only)`

## Summary

| Horizon | total count | selected count | top20 count | excluded entry_untrusted count | excluded terminal_zero_bug count | excluded pool_mark_only count | median_net_pnl_pct | p10_net_pnl_pct | top20 vs bottom20 pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6h | 18618 | 18618 | 3436 | 1935 | 27 | 5767 | 0.158153 | 0.003778 | better |
| 24h | 10178 | 10178 | 1900 | 1921 | 27 | 14131 | 0.160851 | 0.007943 | better |
