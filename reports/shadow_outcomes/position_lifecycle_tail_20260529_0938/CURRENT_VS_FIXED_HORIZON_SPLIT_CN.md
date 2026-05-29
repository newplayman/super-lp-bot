# Current Strategy vs Fixed-Horizon Split

1. current_full_strategy

- score + terminal exit logic
- current position-level full strategy: FAIL
- failure reason: tail does not pass; terminal or lifecycle tail risk remains

2. fixed_horizon_or_no_terminal_exit_hypothesis

- future-only subset may still show candidate direction
- this is not the current strategy
- it still needs fresh OOS
- it cannot enter canary

## Recommendation

- continue current strategy repair: yes
- start separate fixed-horizon research branch: yes
- need fresh OOS long run: yes
- continue canary ban: yes
