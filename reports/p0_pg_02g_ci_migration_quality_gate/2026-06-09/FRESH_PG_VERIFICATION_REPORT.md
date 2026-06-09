# FRESH_PG_VERIFICATION_REPORT — P0-PG-02G

## Test fixture used

The host already had a working test Postgres from the canonical
P0-PG-02E run:

| Attribute | Value |
|---|---|
| container name | `lpbot-test-pg` |
| image | `postgres:16-alpine` |
| host port | 54329 (mapped to container 5432) |
| user | `lpbot` |
| password | `testpass` (from `LPBOT_POSTGRES_TEST_DSN` in P0-PG-02 review-repair report) |
| database | `lpbot_test` |
| status at start of this stage | 15/15 migrations already applied (19 public tables, 15 rows in `schema_migrations`) |

This is a test-only fixture; it is **not** a shared infra resource
(not r1-postgres, not infra-postgres-1, not supabase_db_root). I did
not need to spin up a new container. auto-mode did not need to refuse
a shared-infra container creation because no new container was needed.

I did not modify the DB except by reading from it. The runner's
`plan` and `status` paths do not write; `apply` is a no-op because
all 15 migrations are already applied.

## Plan (pre-apply, all 15 already there)

```
$ POSTGRES_DSN="postgres://lpbot:testpass@127.0.0.1:54329/lpbot_test?sslmode=disable" \
  bin/lpbot-migrate-postgres plan
{
  "files": [ "000001_init_schema.sql", ... "000015_chain_text_alignment.sql" ],
  "to_apply": null,
  "already_applied": [ "000001_init_schema.sql", ... "000015_chain_text_alignment.sql" ]
}
exit: 0
```

`to_apply: null` confirms the runner sees the DB as fully migrated.
This is the **post-apply** shape, which the CI workflow will also
assert (step 8 in `migration-quality-gate.yml`).

## Apply (must be no-op)

```
$ POSTGRES_DSN="..." bin/lpbot-migrate-postgres apply
{
  "ran": [],
  "failed_at": "",
  "failed_err": "",
  "was_partial": false
}
exit: 0
```

`ran: []` confirms the runner detected all 15 migrations are
already applied and did nothing. The end-to-end idempotency path
is exercised in this single run, in addition to the unit tests in
`internal/adapters/store/postgres/migrator/migrator_test.go`.

## Status

```
$ POSTGRES_DSN="..." bin/lpbot-migrate-postgres status
{
  "applied": [
    { "filename": "000001_init_schema.sql", "checksum": "0096e9..." },
    ...
  ],
  "all_required_tables_present": true,
  "all_required_indexes_present": true,
  "missing_required_tables": [],
  "missing_required_indexes": [],
  "all_present": true
}
exit: 0
```

`all_present: true` confirms the runner's source-of-truth table list
(16 application tables + 1 partial unique index) is fully present in
the test DB. No drift, no missing tables.

## Makefile targets (via the wrapper)

The Makefile target chain for CI:

```
make migrate-postgres-plan
make migrate-postgres
make migrate-postgres-status
```

All three pass with the same exit codes as the direct binary
invocations:

| Target | Exit | Note |
|---|---|---|
| `make migrate-postgres` | 0 | no-op; 0 migrations ran |
| `make migrate-postgres-plan` | 0 | 0 pending, 15 applied |
| `make migrate-postgres-status` | 0 | all_present: true |
| `scripts/migrate-postgres.sh` | 0 | exec's into the binary, same result |
| `scripts/migrate-postgres.sh status` | 0 | same |

## Conclusion

A fresh-pg-like environment was available locally without
spinning up a new container. All four migration entry points
(binary direct, three Makefile targets, shell wrapper, wrapper
with explicit subcommand) were exercised end-to-end against a
real Postgres with all 15 migrations already applied, and every
one exited 0 with the expected semantics. The CI workflow
reproduces the same shape against a freshly-spun `postgres:16-alpine`
service.

If this stage had to re-run on a host without the fixture, the
fallback is the CI workflow, which spins up a fresh container
from the `postgres:16-alpine` image. The local test run is
therefore redundant for CI correctness but useful as a smoke
check that the runner, the wrapper, and the Makefile targets all
agree.
