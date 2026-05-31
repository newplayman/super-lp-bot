# INTENT_ENTRY_SOURCE_POLICY_CN

- valid_intent_lifecycle requires high or medium trust entry source.
- low confidence and diagnostic-only sources are excluded from valid proof.
- no hardcoded default notional allowed.

## Valid Sources
- `trace_intended_notional_usd` trust=high condition=non-null, positive, numeric
- `joined_position_amount_usd` trust=medium/high condition=position_id joins cleanly, opened near intent, same pool, no ambiguity
- `first_position_mark_amount_usd` trust=medium condition=same position, near entry time, positive, not stale

## Invalid or Diagnostic Only
- `config_default_notional`
- `hardcoded_default_10`
- `pool_valuation_without_position_linkage`
- `valuation_usd_absolute_without_matching_entry_notional`
- `null_or_zero_fallback`
