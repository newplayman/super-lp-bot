# Fixed Horizon Periodic Monitor Plan

- materialize cadence: every `6h` or `12h`
- do not rerun every `30m`
- every run must report completed deltas and review gate
- after `2-3` consecutive `FLAT` runs, check shadow position generation
- after completed counts cross `100`, enter hypothesis review
- tiny_canary_allowed remains `no` until separate manual approval
