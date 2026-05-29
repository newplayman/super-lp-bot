# Strategy Proof Boundary

## What is currently provable

- `future_position_mark` clean subset shows a candidate signal direction (`better`) in 6h and 24h.

## What is not currently provable

- the full strategy including terminal exits
- a strict reality-proof path for terminal outcomes
- any canary-readiness conclusion

## Why the boundary exists

- terminal rows exist, but all current `terminal_exit_mark` rows in the repaired table are sourced from `pool_mark_only`
- after excluding `pool_mark_only`, the strict terminal cohort becomes empty
- raw proof is still contaminated by `entry_untrusted` outside the clean subset

## Two research directions

1. Repair terminal position-level proof
   - build a dedicated position-level terminal mark layer
   - validate whether closed/exit-adjacent position marks can support strict proof

2. Define a no-terminal / fixed-horizon hold strategy as a separate research hypothesis
   - treat future-position-mark clean subset as a distinct strategy hypothesis
   - do not claim it proves the current full strategy

## Current Decision

- `tiny_canary_candidate = no`
- `tiny_canary_allowed = no`
