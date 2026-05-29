# FIXED_HORIZON_FRESH_OOS_ACCUMULATION_PLAN

- horizons: 6h / 12h / 24h
- proof_unit: position_lifecycle only
- forbidden: decision_trace-level primary proof
- forbidden: terminal-exit proof mixed into fixed-horizon proof
- forbidden: canary / live / paper / wallet / tx path

## sample thresholds
- position_count < 30 => INSUFFICIENT
- 30 <= position_count < 100 => EARLY
- 100 <= position_count < 300 => PRELIMINARY
- position_count >= 300 => USABLE

## per-report required outputs
- new_position_count
- completed_6h_count
- completed_12h_count
- completed_24h_count
- entry_trusted_rate
- future_position_mark_coverage
- median_net_pnl_pct / p10 / p5 / p1
- win_rate
- top20_vs_bottom20_signal
- tail_concentration
- sample_sufficiency
- edge_proven = no unless USABLE and gates pass
- tiny_canary_allowed = no