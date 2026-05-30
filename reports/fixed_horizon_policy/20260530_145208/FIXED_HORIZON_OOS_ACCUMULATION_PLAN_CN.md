# Fixed Horizon OOS Accumulation Plan

## Current Canonical Counts

- `completed_6h = 42`
- `completed_12h = 40`
- `completed_24h = 8`

## Review Thresholds

- minimum preliminary review:
  - `6h completed >= 100`
  - `12h completed >= 100`
  - `24h completed >= 100`
  - 或至少两个 horizon `completed >= 100`
- stronger usable review:
  - 每个 horizon `completed >= 300`

## Cadence

- materialize every `6h` or `12h`
- no need to materialize every `30m`
- if `24h completed` grows too slowly, wait at least one full `24h` cycle before rechecking

## Canonical Observation Policy

- continue observing with:
  - `v2 strict`
  - `v3 clean` only as equivalence check
- do not use:
  - `v3 terminal pool counterfactual` for clean proof
  - terminal-exit proof
  - decision-trace-level samples

## Must Report Each Run

- `completed_6h_count`
- `completed_12h_count`
- `completed_24h_count`
- `p10 / p5 / p1`
- `top20_vs_bottom20_signal`
- `worst_position_contribution`
- `worst_pool_contribution`
- `new_position_count`
- `future_position_mark_coverage`

## Gate Discipline

- before thresholds: `no hypothesis review`
- before thresholds: `edge_proven = no`
- before thresholds: `tiny_canary_allowed = no`
