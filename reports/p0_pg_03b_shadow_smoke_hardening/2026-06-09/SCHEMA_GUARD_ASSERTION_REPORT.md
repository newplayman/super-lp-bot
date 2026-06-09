# SCHEMA_GUARD_ASSERTION_REPORT — P0-PG-03B

## What was added

P0-PG-03's safety check claimed "schema guard OK" but only verified the
shadow mode banner and metrics-server start. The actual
`loadLiveSchemaState` function in `cmd/lpbot/main.go` is gated to
**execution modes only** (`app.liveGate.isExecutionMode() && enabled`);
shadow is not execution, so in shadow mode the schema guard never
ran. The smoke therefore could not actually assert that the required
postgres relations were present.

P0-PG-03B adds a parallel `runShadowSchemaGuard` that runs the same
`loadLiveSchemaState` + `validateLiveSchemaState` pair in shadow mode,
and emits a single structured log line:

```
schema_guard=ok backend=postgres checked_relations=<N>
```

on success, or

```
schema_guard=fail backend=<backend> error="<missing tables>"
```

on failure. The shadow binary fails closed (exit non-zero) if the
guard fails, so a missing table on the smoke DB would prevent the
binary from reaching the workers loop and the smoke would naturally
FAIL.

## Mechanism

```go
// in cmd/lpbot/main.go (after ensureShadow*Table calls)
if backend == "postgres" || backend == "postgresql" || backend == "pg" {
    if err := app.runShadowSchemaGuard(ctx); err != nil {
        return fmt.Errorf("shadow schema guard failed: %w", err)
    }
}

// runShadowSchemaGuard itself:
func (app *App) runShadowSchemaGuard(ctx context.Context) error {
    ...
    state, err := loadLiveSchemaState(ctx, dbStore.DB())
    if err != nil { return err }
    if err := validateLiveSchemaState(state); err != nil {
        app.logger.Error("schema_guard=fail", ...)
        return err
    }
    app.logger.Info("schema_guard=ok backend=postgres",
        zap.Int("checked_relations", len(state)))
    return nil
}
```

## What the guard checks

Same table list as the live-mode guard (in `loadLiveSchemaState`):

- `positions`
- `transactions`
- `execution_intents`
- `portfolio_snapshots`
- `position_marks`
- `canary_events`
- `pnl_ledger`
- `shadow_decision_trace`
- `idx_positions_one_active_per_pool` (the partial unique index)

The check uses `SELECT to_regclass('public.<name>') IS NOT NULL`,
which is fast and does not require `SELECT *`. `checked_relations: 9`
in the smoke log confirms the full list ran.

## Safety-check wiring

`scripts/check_shadow_smoke_safety.sh` now requires:

```
required_substrings=(
  'Running in shadow mode'
  'metrics server started'
  'schema_guard=ok'                 # NEW in P0-PG-03B
  'smoke_no_rpc_mode=true'          # NEW in P0-PG-03B
  'base_rpc_initialization=skipped' # NEW in P0-PG-03B
)
```

Missing any of these makes the safety check exit 1 with a specific
message naming the missing substring.

## Empirical evidence (5-minute hardened smoke)

The 5-minute smoke log contains exactly the expected schema-guard
line:

```
{"level":"info","ts":1781025855.7947454,
 "caller":"lpbot/main.go:896",
 "msg":"schema_guard=ok backend=postgres",
 "env":"shadow","schema_version":1,"checked_relations":9}
```

The safety check confirms this:

```
shadow_smoke_safety: forbidden_pattern_violations=0
shadow_smoke_safety: missing_required_substrings=0
shadow_smoke_safety: OK
shadow_smoke_safety:   - schema_guard=ok present
```

## Negative case

If the smoke's test DB were missing one of the required relations,
`validateLiveSchemaState` would return:

```
shadow schema guard failed: live schema guard blocked startup; missing postgres relations: <name>
```

The binary would exit 1 at startup, the log would contain
`schema_guard=fail` instead of `schema_guard=ok`, and the safety check
would FAIL on the missing-substring assertion. This is the intended
fail-closed behavior.

## What was NOT changed

- The `loadLiveSchemaState` + `validateLiveSchemaState` pair (still
  used by the live-mode path; the shadow path calls them too).
- The required table list (single source of truth, shared by both
  live and shadow paths).
- The live-mode schema guard (still gated to execution modes; still
  not invoked in shadow mode).