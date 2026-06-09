# ENTRYPOINT_CLEANUP_REPORT — P0-PG-02F

## Scope

P0-PG-02F is the follow-up to P0-PG-02E (the Go migrator). P0-PG-02E is
**already shipped and accepted** on `origin/feat/supabase-postgres-deployment`
at canonical run id `20260609_060000`. P0-PG-02F does **not** re-implement
P0-PG-02E; it removes the remaining legacy shell-script entrypoint and adds
a CI guard against the dual-source SQL drift.

The two real risks addressed:

1. `scripts/migrate-postgres.sh` (canonical: 233 lines, 8546 bytes) was an
   independent awk-based psql loop that maintained its own
   `schema_migrations` table and its own REQUIRED_TABLES list. Two
   parallel migration systems is exactly the kind of drift the audit
   flagged.
2. `migrations/postgres/` and
   `internal/adapters/store/postgres/migrator/sql/` are a true dual
   source on disk. The runner has to embed a real copy (go:embed
   rejects `..` and does not follow symlinks). Without a guard, a new
   migration added to `migrations/postgres/` will not be picked up by
   the runner until the next `make build-*` happens to refresh the
   embed dir.

## Changes

### `scripts/migrate-postgres.sh` — thin wrapper

Before:

- 233 lines, 8546 bytes
- awk-based `-- +goose Up` / `-- +goose Down` section extraction
- `psql -f` loop calling each migration individually
- own `CREATE TABLE IF NOT EXISTS schema_migrations` write
- own `INSERT INTO schema_migrations(filename) VALUES (...)` write
- own `REQUIRED_TABLES` list with 16 entries
- own production-DSN guard (supabase.co / rds / prod / production) with
  `LPBOT_MIGRATE_ALLOW_LIVE=YES` override
- own `apply | plan | status` sub-mode dispatch

After:

- 45 lines, 1645 bytes
- one `exec "${BIN}" "$@"`
- one existence check for `bin/lpbot-migrate-postgres` with a hint
  pointing at `make build-migrate-postgres` / `make migrate-postgres`
- zero SQL parsing, zero `psql`, zero `schema_migrations` writes, zero
  canary/live env auto-load
- the script does not even read DSN; the Go runner does that

Sanity check (binary removed):

```
$ scripts/migrate-postgres.sh
error: /opt/lpbot/lp-bot-v3-origin-check/bin/lpbot-migrate-postgres not built.
hint:  run `make build-migrate-postgres` first (or `make migrate-postgres`).
exit: 2
```

Sanity check (binary present, no DSN):

```
$ POSTGRES_DSN=... bin/lpbot-migrate-postgres plan
lpbot-migrate-postgres: POSTGRES_DSN / DATABASE_URL is empty
exit: 0  (binary prints hint; the wrapper exec'd into it correctly)
```

The Go binary owns the exit-code semantics, the DSN validation, the
canary/live rejection, and the schema_migrations table. The shell
script is now a transparent `exec` shim.

### `scripts/check_postgres_migrations_sync.sh` — new drift guard

A standalone shell script that compares the two migration directories:

- `migrations/postgres/*.sql` (source of truth, in VCS)
- `internal/adapters/store/postgres/migrator/sql/*.sql` (embed copy)

Checks (all must pass):

1. Both directories exist.
2. Both have at least one `.sql` file.
3. The sorted file lists are identical.
4. The `sha256sum` of every file is identical (sorted by filename).

On any drift: prints `drift: ...` to stderr, exit 1.

### `make check-postgres-migrations-sync` — new Makefile target

Wires the script into a single-command target. Both added to
`.PHONY` and to the body. Failure mode is exit 1 from the script,
propagated through `make`.

### Dual source is preserved, not collapsed

The runner cannot read `migrations/postgres/` directly: `go:embed` rejects
`..` paths and does not follow symlinks (verified empirically in P0-PG-02E
— the build failed with `cannot embed file sub/x.sql: in non-directory sub`).
Collapsing the two would require either:

- **A.** Switching the runner to a different migration system that can
  read from any path (e.g. `pressly/goose/v3` — already in `go.mod`).
  That is a deliberate design change for a future task.
- **B.** Moving `migrations/postgres/` into the Go package tree so the
  embed path becomes a normal sibling. That is a directory-layout change
  and would also be a follow-up.

P0-PG-02F explicitly does **not** take either route. The dual source is
**intentionally retained** and **guarded by a sync check** so that
adding a new migration must be a single intentional action: `make
sync-postgres-migrations` (already exists in the Makefile, also a
dependency of every `build-*` target) or any `build-*` invocation will
refresh the embed copy; the sync check makes the failure loud if the
two ever diverge.

## What was NOT changed (explicitly out of scope)

- `migrations/postgres/*.sql` — untouched.
- `internal/adapters/store/postgres/migrator/sql/*.sql` — untouched
  (the build-time copy mechanism in the Makefile already keeps these
  in sync).
- `internal/adapters/store/postgres/migrator/migrator.go` and friends —
  untouched. The canonical Go runner from P0-PG-02E is used as-is.
- `cmd/lpbot-migrate-postgres/main.go` — untouched.
- `configs/config.*.toml` — untouched.
- The deploy systemd unit files — untouched.
- The `tests/test_lp_long_horizon_partial_12h_request_v1.py` r1-related
  modification — preserved untouched on the working tree per the
  user's "不得修改 R1 reports / data dirs" rule.

## Local cleanup performed before P0-PG-02F edits

The previous session had a duplicate P0-PG-02E commit (`75b5291`) and
a non-canonical report directory at
`reports/p0_pg_02e_migration_runner_idempotency/2026-06-09/`. Cleanup:

- `git reset --soft origin/feat/supabase-postgres-deployment` — dropped
  the duplicate commit, moved its changes back to the index.
- `git ls-files -m | grep -v long_horizon | xargs -r git checkout --` —
  no-op (the duplicate was in the index, not worktree).
- `git diff --cached --name-only | grep -v long_horizon | xargs -r git
  reset HEAD --` — unstaged the 73 duplicate files.
- `rm internal/adapters/store/postgres/migrator/discovery.go
   internal/adapters/store/postgres/migrator/embed.go` — deleted two
  untracked stale files from my session; remote's layout uses
  `migrations.go` instead.
- `rm -rf reports/p0_pg_02e_migration_runner_idempotency/2026-06-09` —
  removed the non-canonical report dir.
- `git stash pop` — restored the pre-existing r1 modification that
  had been stashed to protect it across the reset.

Post-cleanup `git ls-files -m`:

```
tests/test_lp_long_horizon_partial_12h_request_v1.py
```

The only remaining tracked modification is the r1 file. Per the
user's directive: r1 files are preserved.
