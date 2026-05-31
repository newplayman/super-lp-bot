# Lookahead / Leakage Audit

- leakage_found: yes
- lookahead_risk: HIGH
- key_evidence:
  regime classifier rows are materialized by completed 15m bucket_end, but the counterfactual maps sample start bucket_start directly onto that row.
  This allows same-bucket post-entry marks to influence regime classification for the sample.
- suspicious_features: sample bucket_start matched to classifier row built from bucket_end = bucket_start + 15m, price_move_5m / 15m / 30m / 1h derived from marks up to classifier bucket_end, volume_change_15m / 30m / 1h derived from marks up to classifier bucket_end, tvl_change_1h derived from marks up to classifier bucket_end, stale_data_flag and data_quality_score computed at classifier bucket_end, not guaranteed pre-entry
- required_fix: shift regime lookup to previous fully known bucket before sample start, recompute regime features with entry-safe timestamps only, downgrade same-bucket freshness/price/volume/tvl features to diagnostic-only until alignment is fixed, rerun regime-aware short-hold counterfactual after temporal alignment fix
