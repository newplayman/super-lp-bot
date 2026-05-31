# Risk Signal Definition V1

- price_spike_down: trigger=price_change_pct <= -10 high; <= -5 medium within window severity=high action=exit_now confidence=medium limitations=proxy-quality price change; may reflect aggregated mark noise
- price_spike_up: trigger=price_change_pct >= 15 severity=low action=hold confidence=medium limitations=used as instability marker, not direct loss trigger
- volume_collapse: trigger=current_vol24h_usd <= 60% of previous mark severity=high action=exit_now confidence=medium limitations=uses rolling vol24h proxy, not raw window volume tape
- tvl_drop: trigger=current_tvl_usd <= 85% of previous mark severity=high action=exit_now confidence=medium limitations=pool-level proxy; may lag real reserve updates
- exit_depth_drop: trigger=entry_size / pool_tvl_proxy > 0.1 or tvl proxy thin severity=high action=quarantine_no_entry confidence=low limitations=not a route simulation; proxy only
- trader_concentration_spike: trigger=not available in v1, reserved for later enrichment severity=medium action=hold confidence=unknown limitations=not measured in v1
- holder_concentration_spike: trigger=not available in v1, reserved for later enrichment severity=medium action=hold confidence=unknown limitations=not measured in v1
- abnormal_volume_spike: trigger=current_vol24h_usd >= 180% of previous mark severity=low action=hold confidence=medium limitations=used as regime instability marker
- pool_mark_gap / stale data: trigger=mark gap > 1h or future mark missing beyond horizon severity=high action=quarantine_no_entry confidence=high limitations=staleness may reflect sampling and not real pool failure
