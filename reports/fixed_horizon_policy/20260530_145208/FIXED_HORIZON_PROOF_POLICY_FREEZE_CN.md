# Fixed Horizon Proof Policy Freeze

## Canonical Proof

- name: `v2_strict_fixed_horizon`
- accepted_mark_source:
  - `future_position_mark`
- accepted_position_status:
  - `active_at_target`
- excluded:
  - `terminal_before_target`
  - `pool_mark_only`
  - `terminal_exit_mark`
  - `decision_trace-level samples`

## Research-Only Diagnostic

- name: `v3_terminal_pool_counterfactual`
- purpose:
  - 估算 terminal-before-target 情况下，如果按 pool-level mark 反事实持有，到目标 horizon 会怎样。
- accepted_mark_source:
  - `pool_mark_only`
- confidence:
  - `low`
  - `medium`
- not_allowed_for:
  - `clean proof`
  - `edge_proven`
  - `canary decision`

## Freeze Decision

- `v3_clean_fixed_horizon adds meaningful samples`: no
- `v3_clean should replace v2 strict`: no
- `pool_mark_only_allowed_in_clean_proof`: no
- `terminal_before_target_allowed_in_clean_proof`: no
- `no more materializer semantics variants unless concrete bug appears`: yes

## Evidence

- canonical counts unchanged:
  - `6h`: `42 -> 42`
  - `12h`: `40 -> 40`
  - `24h`: `8 -> 8`
- only counterfactual coverage gain:
  - `6h`: `+21`
  - `12h`: `+19`
  - `24h`: `+44`

结论：canonical proof policy 冻结为 `v2_strict_fixed_horizon`。`v3_research` 保留，但只作 diagnostic / counterfactual。
