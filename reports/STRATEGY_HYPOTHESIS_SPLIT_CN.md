# Strategy Hypothesis Split

## current_full_strategy

- includes score + terminal exit logic.
- terminal_clean 6h = better
- terminal_clean 24h = worse
- combined_clean 6h = better
- combined_clean 24h = better
- terminal_clean 24h remains worse, so current full strategy proof stays FAIL.

## fixed_horizon_or_no_terminal_exit_strategy

- future_clean 6h = better
- future_clean 24h = better
- future-only subset still shows candidate signal, but this is not the current strategy.
- any fixed-horizon / no-terminal hypothesis needs fresh OOS validation before it can be be treated as strategy evidence.

## Boundary

- current full strategy is not proven.
- only a future-only/fixed-horizon research hypothesis remains discussable.
- tiny_canary_candidate = no
- tiny_canary_allowed = no
