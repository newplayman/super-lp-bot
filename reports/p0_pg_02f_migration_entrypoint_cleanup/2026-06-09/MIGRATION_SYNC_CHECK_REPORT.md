# MIGRATION_SYNC_CHECK_REPORT — P0-PG-02F

## The two directories

```
migrations/postgres/                                          (source of truth, in VCS)
  000001_init_schema.sql
  000002_canary_state.sql
  000003_pool_runtime_columns.sql
  000004_transactions_timestamp_cleanup.sql
  000005_positions_runtime_metadata.sql
  000006_active_position_uniqueness.sql
  000007_execution_intents.sql
  000008_portfolio_snapshots.sql
  000009_pnl_v1_and_position_marks.sql
  000010_shadow_outcome_labels.sql
  000011_shadow_decision_trace.sql
  000012_shadow_outcome_repaired_v2.sql
  000013_shadow_position_marks.sql
  000014_shadow_exit_tables.sql
  000015_chain_text_alignment.sql

internal/adapters/store/postgres/migrator/sql/                (embed copy)
  ... same 15 files ...
```

## Why two directories exist

`go:embed` cannot reach outside the package's own subtree with `..`
paths, and does not follow symlinks (confirmed empirically in P0-PG-02E
research: `pattern sub/x.sql: cannot embed file sub/x.sql: in
non-directory sub`). The migrator therefore embeds a *real* copy.

The copy is kept up to date by the Makefile rule
`sync-postgres-migrations` (which is also a dependency of every
`build-*` target). Without a guard, however, a new migration added to
`migrations/postgres/` will be invisible to the runner until the next
build happens to refresh the embed dir, and the divergence will be
silent. That is exactly the risk the audit flagged.

## What the guard checks

`scripts/check_postgres_migrations_sync.sh` enforces, in order:

1. Both directories exist.
2. Both have at least one `.sql` file.
3. The sorted list of `.sql` filenames is identical.
4. The `sha256sum` of every file is identical (sorted by filename).

Any failure: prints `drift: ...` to stderr with a unified diff of the
offending comparison, exits 1.

## Observed state

### In-sync (clean)

```
$ make check-postgres-migrations-sync
./scripts/check_postgres_migrations_sync.sh
sync OK: 15 file(s) match between /opt/lpbot/lp-bot-v3-origin-check/migrations/postgres/ and /opt/lpbot/lp-bot-v3-origin-check/internal/adapters/store/postgres/migrator/sql/
exit: 0
```

### Drift detection (verified by injection)

Append a single comment line to the embed copy of 000001 and re-run:

```
$ echo "-- injected drift" >> internal/adapters/store/postgres/migrator/sql/000001_init_schema.sql
$ make check-postgres-migrations-sync
./scripts/check_postgres_migrations_sync.sh
drift: sha256 mismatch (filenames match; contents differ):
1d0
< 0096e9262815712ba07fa685f02a3dffd26408dca4a59ead0c13c3225e25c066  000001_init_schema.sql
7a7
> 4e0e50d4c8534d580d8bd48032e711a3d69e986d2c1fd00c7515936fb2ca16d2  000001_init_schema.sql
make: *** [Makefile:64: check-postgres-migrations-sync] Error 1
exit: 2
```

After reverting the drift:

```
$ git checkout -- internal/adapters/store/postgres/migrator/sql/000001_init_schema.sql
$ make check-postgres-migrations-sync
sync OK: 15 file(s) match between /opt/lpbot/.../migrations/postgres/ and /opt/lpbot/.../migrator/sql/
exit: 0
```

The guard catches both kinds of drift:

- **missing file** in either dir (file-list diff)
- **content drift** with same filenames (sha256 diff)

## Where the guard sits in the workflow

- `make build-dryrun` / `build-shadow` / `build-live` / `backtest` /
  `build-migrate-postgres` all depend on `sync-postgres-migrations`
  (the build-time copier) so the embed dir is refreshed at every
  build.
- The new `make check-postgres-migrations-sync` is a separate, fast,
  read-only check suitable for CI gating. It does not write anything.
- It is NOT wired into `make test-all` in this commit; the canonical
  follow-up is to add it to `.github/workflows/ci.yml`'s quality-gate
  job. That is recorded in `remaining_blockers`.

## What would happen if a new migration is added

1. Engineer adds `migrations/postgres/000016_*.sql` and commits.
2. CI's existing `build-*` targets would still pass (the new file is
   in the source dir; the runner's embed dir is the old snapshot
   until the next `make build-*` runs).
3. The new `make check-postgres-migrations-sync` would catch the
   drift: the source dir has 16 files, the embed dir has 15.
4. Fix: `make sync-postgres-migrations` (one-shot) or any
   `make build-*` (which depends on it). Re-run sync check: PASS.
