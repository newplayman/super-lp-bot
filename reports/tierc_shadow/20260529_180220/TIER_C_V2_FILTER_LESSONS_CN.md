# Tier C V2 Filter Lessons

- Source: V1 counterfactual batch failure and manual candidate audit.
- These thresholds are research-only filters, not production strategy rules.

- `EXIT_DEPTH_BAD`: `max_exit_depth_fail_rate=0.05`. V1 failed pools above 0.05 exit-depth fail rate broke tail or completion quality
- `TAIL_TOO_HEAVY`: `max_p10_loss_threshold=-0.005`. V1 best short-horizon p10 stayed materially below 0; research floor set at -0.5%
- `VOLUME_COLLAPSE`: `max_volume_collapse_rate=0.15`. V1 weaker pools moved above 0.15 volume-collapse rate
- `PRICE_SPIKE_DOWN`: `max_price_spike_down_rate=0.05`. price spike-down above 5% of samples lined up with unstable tails
- `HOLDER_RISK`: `max_holder_concentration=25`. conservative holder concentration cap for Tier C research-only filtering
- `DATA_QUALITY_FAIL`: `max_quarantine_trigger_rate=0.30`. V1 quarantine-heavy pools were not salvageable even after proof-layer filtering
- `QUARANTINE_100_PERCENT`: `max_quarantine_trigger_rate=0.30`. 100% quarantine pools are automatic reject in V2 research filter
- `SURVIVAL_TOO_LOW`: `min_survival_rate=0.80`. V1 low-survival pools failed both tail and completion screens
- `EXIT_DEPTH_USD`: `min_exit_depth_usd=100`. research minimum exit depth target at least 10x the default 10 USD probe size
