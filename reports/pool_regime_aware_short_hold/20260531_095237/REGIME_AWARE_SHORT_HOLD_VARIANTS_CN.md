# Regime Aware Short Hold Variants

- baseline_hold_all: none
- risk_signal_v2_quarantine_first: quarantine on quarantine-first price/volume/depth signal
- regime_exclude_data_stale: exclude DATA_STALE_OR_INCOMPLETE
- regime_enter_only_healthy: enter HEALTHY_SHORT_HOLD only
- regime_enter_healthy_or_stable_fee: enter HEALTHY_SHORT_HOLD or STABLE_FEE
- regime_exclude_bad_all: exclude all bad regimes
- regime_score_threshold_loose: risk_score <= 35
- regime_score_threshold_strict: risk_score <= 20
- hybrid_regime_plus_signal: regime not bad and signal not quarantine
- hybrid_regime_plus_signal_plus_fee: regime not bad, signal not quarantine, fee_proxy > exit_cost_proxy
