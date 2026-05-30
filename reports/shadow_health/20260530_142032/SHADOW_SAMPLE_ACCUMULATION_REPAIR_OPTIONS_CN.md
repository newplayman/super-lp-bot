# Shadow Sample Accumulation Repair Options

- `Continue OOS accumulation only`
  - applicable=`no`
  - evidence=`24h matured samples exist, but all are pool_mark_only after terminal`
  - recommended=`no`

- `Shadow selector / position writer audit`
  - applicable=`no`
  - evidence=`intent_open rows already carry valid position_id; 5613/5619 are reuse_shadow_position`
  - recommended=`no`

- `Mark coverage fix`
  - applicable=`yes`
  - evidence=`24h matured positions have no future position mark`
  - recommended=`no`
  - note=`not first priority, because pool-level marks already exist`

- `Materializer semantics fix`
  - applicable=`yes`
  - evidence=`24h matured positions are pool_mark_only and strict v2 excludes them`
  - recommended=`yes`

- `Add research-only synthetic lifecycle from unique intent`
  - applicable=`no`
  - evidence=`intent_open mostly means reuse of existing positions, not independent new entry candidates`
  - recommended=`no`

