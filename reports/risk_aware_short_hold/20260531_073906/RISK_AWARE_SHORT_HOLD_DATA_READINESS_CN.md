# Risk Aware Short Hold Data Readiness

- pool_id: available=yes source=shadow_decision_trace / shadow_position_marks coverage=100% confidence=high blocker= required=yes
- token_pair: available=yes source=pool_token_metadata / pools coverage=100% confidence=high blocker= required=yes
- start_time: available=yes source=shadow_decision_trace / shadow_position_marks coverage=100% confidence=high blocker= required=yes
- horizon: available=yes source=script config coverage=100% confidence=high blocker= required=yes
- entry pool value / price proxy: available=partial source=shadow_decision_trace / positions / shadow_position_marks coverage=100.0% confidence=medium blocker=some entries require fallback source required=yes
- future pool value / price proxy: available=partial source=shadow_position_marks coverage=100.0% confidence=medium blocker=no_future_pool_mark remains the dominant invalid reason required=yes
- price_move_5m/15m/30m: available=partial source=shadow_position_marks coverage=100.0% confidence=medium blocker=price_change_pct is proxy-quality, not an independent price tape required=yes
- volume_change_15m/30m/1h: available=partial source=shadow_position_marks coverage=100.0% confidence=medium blocker=uses rolling vol24h proxy from marks required=yes
- tvl_change_1h: available=partial source=shadow_position_marks coverage=100.0% confidence=medium blocker=proxy from mark snapshots required=yes
- exit_depth 10/20/50 USD: available=partial source=pools / shadow_position_marks coverage=100.0% confidence=low blocker=proxy only; no route API used in v1 required=yes
- risk event labels: available=partial source=derived from marks coverage=derived confidence=medium blocker=no native risk_events rows; derived labels only required=yes
- fee proxy or fee velocity proxy: available=partial source=pools coverage=100.0% confidence=medium blocker=uses pool vol/tvl and fee_bps proxy required=yes
