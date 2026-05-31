# ENTRY_NOTIONAL_SOURCE_AUDIT_CN

- hardcoded 10 USD 已完全禁用。
- 只有 high / medium trust source 才允许进入 valid intent lifecycle。
- config default / valuation-only / prior research output 只用于 diagnostic。

- `shadow_decision_trace.intended_notional_usd` exists=yes coverage_pct=0.0 trust=unusable reason=mostly null in current 7d sample
- `shadow_decision_trace.intended_size_usd` exists=no coverage_pct=0.0 trust=unusable reason=column not present in live schema
- `shadow_decision_trace.notional_usd` exists=no coverage_pct=0.0 trust=unusable reason=column not present in live schema
- `shadow_decision_trace.max_order_usd` exists=no coverage_pct=0.0 trust=unusable reason=column not present in live schema
- `shadow_decision_trace.order_usd` exists=no coverage_pct=0.0 trust=unusable reason=column not present in live schema
- `shadow_decision_trace.amount_usd` exists=no coverage_pct=0.0 trust=unusable reason=column not present in live schema
- `shadow_decision_trace.score_json` exists=yes coverage_pct=100.0 trust=diagnostic_only reason=JSON payload can support audit only; not a direct entry notional
- `positions.amount_usd` exists=yes coverage_pct=100.0 trust=medium reason=joinable position notional, requires clean position_id and timing alignment
- `positions.entry_value_usd` exists=no coverage_pct=0.0 trust=unusable reason=column absent from live positions schema
- `positions.notional_usd` exists=no coverage_pct=0.0 trust=unusable reason=column absent from live positions schema
- `positions.opened_at` exists=yes coverage_pct=100.0 trust=diagnostic_only reason=timing support for clean join, not notional itself
- `shadow_position_marks.amount_usd` exists=yes coverage_pct=100.0 trust=medium reason=same-position mark amount can approximate entry notional if near entry and not stale
- `shadow_position_marks.valuation_usd` exists=yes coverage_pct=99.9955 trust=diagnostic_only reason=absolute valuation without trustworthy entry notional cannot form valid entry
- `shadow_position_marks.source` exists=yes coverage_pct=100.0 trust=diagnostic_only reason=mark provenance only
- `shadow_position_lifecycle_proof_v2.entry_value_usd` exists=yes coverage_pct=100.0 trust=diagnostic_only reason=useful reference but downstream derived table, not independent entry source
- `shadow_intent_lifecycle_research_v1.entry_value_usd` exists=yes coverage_pct=100.0 trust=diagnostic_only reason=prior research output only; cannot self-validate v2
