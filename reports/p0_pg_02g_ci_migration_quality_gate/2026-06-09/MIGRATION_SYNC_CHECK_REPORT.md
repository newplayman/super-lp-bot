# MIGRATION_SYNC_CHECK_REPORT — P0-PG-02G

The sync check is unchanged from P0-PG-02F; this stage only wires it
into the local quality gate and the GitHub Actions quality gate.

## Local: `make check-postgres-migrations-sync`

```
$ make check-postgres-migrations-sync
./scripts/check_postgres_migrations_sync.sh
sync OK: 15 file(s) match between /opt/lpbot/lp-bot-v3-origin-check/migrations/postgres/ and /opt/lpbot/lp-bot-v3-origin-check/internal/adapters/store/postgres/migrator/sql/
exit: 0
```

The script checks:

1. Both directories exist.
2. Both have at least one `.sql` file.
3. The sorted `.sql` filename lists are identical.
4. The SHA256 of every file is identical (sorted by filename).

Drift detection was already verified end-to-end in P0-PG-02F (sha256
injection + restore). Re-verified in this stage by re-running the
target on the current tree (PASS).

## CI: GitHub Actions

The new `migration-quality-gate.yml` workflow runs the same script
as step 4 of the job. The existing `ci.yml` quality-gate job also
runs it as a new step (`Migration sync check`). Both will fail
the build on drift, including the daily cron.

A drift in either direction (missing file in either dir; content
mismatch with same filenames) is caught and reported with a unified
diff to stderr.

## Where the guard sits in the workflow

```
PR / push / cron
  └─ ci.yml quality-gate ──► make check-postgres-migrations-sync   (cheap; every PR)
  └─ migration-quality-gate.yml ──► make check-postgres-migrations-sync   (paths-gated; full DB run)
```

The cheap check is the primary drift guard; the dedicated workflow
re-runs the same check inside the postgres-isolated job so any drift
in the DB-bound path is also caught.
