# MIGRATION_REPORT — Mode A2

## Fresh database

`lpbot_mode_a2_20260610_065144` (owned by `lpbot`) on host
`127.0.0.1:54329` (container `lpbot-test-pg` from the canonical
P0-PG-02E run). The database was empty before the migrations.

DSN: `postgres://lpbot:***@127.0.0.1:54329/lpbot_mode_a2_20260610_065144?sslmode=disable`

## Sequence

```
make build-migrate-postgres                           # exit 0
make check-postgres-migrations-sync                   # exit 0
                                                   # sync OK: 15 files
POSTGRES_DSN="..." make migrate-postgres-plan      # exit 0
                                                   # 15 pending, 0 applied
POSTGRES_DSN="..." make migrate-postgres            # exit 0
                                                   # ran: 15
POSTGRES_DSN="..." make migrate-postgres-status    # exit 0
                                                   # all_present: true
POSTGRES_DSN="..." make migrate-postgres            # exit 0 (reapply, no-op)
```

## Pre-apply plan

```
"to_apply": [
  "000001_init_schema.sql",
  ...
  "000015_chain_text_alignment.sql"
],
"already_applied": null
```

All 15 migrations pending. Fresh DB confirmed.

## Apply

```
"failed_at": "",
"failed_err": "",
"was_partial": false
```

The runner applied all 15 in a single call.

## Post-apply DB inspection

```
migrations_applied: 15
```

15 rows in `schema_migrations`.

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
"all_present": true
```

The runner's source-of-truth table list is fully present. No drift.

## Re-apply (idempotency)

```
"applied": null,
"skipped": [ ...15 entries... ]
```

The runner detected all 15 were already there and did nothing.

## Sync check

```
sync OK: 15 file(s) match between migrations/postgres/ and migrator/sql/
```

## Cleanup

After the soak, the database was dropped:

```
DROP DATABASE
```

## Conclusion

Migration verification on a fresh DB: PASS. The runner is the
single source of truth; the thin shell wrapper (P0-PG-02F) routes
through it; the CI quality gate (P0-PG-02G) enforces the same
path.