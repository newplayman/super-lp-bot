# MIGRATION_FRESH_DB_REPORT — P0-PG-03

## Fresh database

`lpbot_smoke03` (owned by `lpbot`) on host `127.0.0.1:54329` (container
`lpbot-test-pg` from the canonical P0-PG-02E run; **not** r1 / infra /
supabase). The database was created at the start of this stage with
`CREATE DATABASE lpbot_smoke03 OWNER lpbot;` and was empty (no tables)
before the smoke.

DSN: `postgres://lpbot:***@127.0.0.1:54329/lpbot_smoke03?sslmode=disable`
(the password is intentionally masked here; full DSN is in the
`run_shadow_smoke.sh` invocation only and is the test fixture default
documented in P0-PG-02 review-repair).

## Sequence

```
make build-migrate-postgres                     # exit 0
make check-postgres-migrations-sync             # exit 0
POSTGRES_DSN=... make migrate-postgres-plan     # exit 0; 15 pending, 0 applied
POSTGRES_DSN=... make migrate-postgres           # exit 0; 15 applied
POSTGRES_DSN=... make migrate-postgres-plan     # exit 0; 0 pending, 15 applied
POSTGRES_DSN=... make migrate-postgres-status   # exit 0; all_present=true
POSTGRES_DSN=... make migrate-postgres           # exit 0; no-op (15 skipped)
```

## Pre-apply plan

```
"to_apply": [
  "000001_init_schema.sql",
  "000002_canary_state.sql",
  "000003_pool_runtime_columns.sql",
  "000004_transactions_timestamp_cleanup.sql",
  "000005_positions_runtime_metadata.sql",
  "000006_active_position_uniqueness.sql",
  "000007_execution_intents.sql",
  "000008_portfolio_snapshots.sql",
  "000009_pnl_v1_and_position_marks.sql",
  "000010_shadow_outcome_labels.sql",
  "000011_shadow_decision_trace.sql",
  "000012_shadow_outcome_repaired_v2.sql",
  "000013_shadow_position_marks.sql",
  "000014_shadow_exit_tables.sql",
  "000015_chain_text_alignment.sql"
],
"already_applied": null
```

All 15 migrations pending. Fresh DB confirmed.

## Apply

```
"applied": null  # (in the post-apply re-apply)
"skipped": null  # first time
"failed_at": "",
"failed_err": "",
"was_partial": false
```

The runner applied all 15 in a single call.

## Post-apply DB inspection

```
$ PGPASSWORD=*** psql -h 127.0.0.1 -p 54329 -U lpbot -d lpbot_smoke03 \
    -c "SELECT count(*) AS migrations_applied FROM schema_migrations;
        SELECT count(*) AS table_count FROM information_schema.tables
        WHERE table_schema='public';"

 migrations_applied
--------------------
                 15
 table_count
-------------
          19
```

15 rows in `schema_migrations`; 19 public tables (18 application tables
+ `schema_migrations` itself).

## Post-apply plan

```
"to_apply": null,
"already_applied": [ ...15 entries... ]
```

`to_apply: null` confirms the runner sees the DB as fully migrated.

## Status

```
"all_required_tables_present": true,
"all_required_indexes_present": true,
"missing_required_tables": [],
"missing_required_indexes": [],
"all_present": true
```

The runner's source-of-truth table list (the 16 application tables the
shadow binary requires, plus the 1 partial unique index
`idx_positions_one_active_per_pool`) is fully present. No drift.

## Re-apply (idempotency)

```
"applied": null,
"skipped": [ ...15 entries... ]
```

The runner's `applied` field is null (no new migrations to apply) and
its `skipped` field lists all 15 — explicit confirmation that the
runner detected they were already there and did nothing.

## Sync check

```
$ make check-postgres-migrations-sync
./scripts/check_postgres_migrations_sync.sh
sync OK: 15 file(s) match between .../migrations/postgres/ and .../migrator/sql/
exit: 0
```

## Cleanup

After the smoke, the database was dropped:

```
$ PGPASSWORD=*** psql -h 127.0.0.1 -p 54329 -U lpbot -d postgres \
    -c "DROP DATABASE lpbot_smoke03;"
DROP DATABASE
```

The `lpbot-test-pg` container itself is left running so future stages
can recreate fresh test databases against it.

## Conclusion

Migration verification on a fresh DB: PASS. The runner is the single
source of truth; the thin shell wrapper (P0-PG-02F) routes through it;
the CI quality gate (P0-PG-02G) enforces the same path.
