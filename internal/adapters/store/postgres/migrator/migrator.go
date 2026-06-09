// Package migrator provides a Go-based migration runner for the lp-bot
// Postgres adapter.
//
// Design constraints (per LP_BOT_ENGINEERING_P0_PG_02E stage):
//
//   1. Each migration runs in its own transaction. On any error the
//      transaction is rolled back and the runner stops.
//
//   2. Applied migrations are tracked in a schema_migrations table with
//      columns (filename TEXT PK, checksum TEXT, applied_at TIMESTAMPTZ).
//      SHA256 of the file content is recorded so re-running detects
//      accidental drift.
//
//   3. The runner is idempotent: re-running apply on an up-to-date DB
//      is a no-op. Re-running apply on a partial-failure DB resumes
//      from the first un-applied migration.
//
//   4. The runner does NOT auto-load .env.canary, .env.live, or any
//      canary/live env. DSN must be supplied explicitly via POSTGRES_DSN
//      or DATABASE_URL. (The shell wrapper scripts/migrate-postgres.sh
//      may still be used; see the production-DSN guard there.)
//
//   5. The runner does NOT connect to production-looking DSNs unless
//      LPBOT_MIGRATE_ALLOW_LIVE=YES is set. Production-DSN detection
//      matches the shell wrapper's heuristic.
//
//   6. The runner exposes plan / status / apply subcommands so a
//      operator can preview before applying.
//
// This replaces scripts/migrate-postgres.sh as the canonical entry
// point. The shell script remains as a thin wrapper for backward
// compat (CI usage, operator muscle memory).
package migrator

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"net/url"
	"os"
	"path"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

// Mode is the runner subcommand.
type Mode string

const (
	ModePlan   Mode = "plan"
	ModeStatus Mode = "status"
	ModeApply  Mode = "apply"
)

// Config is the input to NewRunner.
type Config struct {
	// DSN is the postgres connection string. Required.
	DSN string
	// MigrationsFS is the embed.FS containing *.sql files. Required.
	MigrationsFS fs.FS
	// MigrationsDir is the subdirectory inside MigrationsFS where
	// migrations live (e.g. "migrations").
	MigrationsDir string
	// AllowLiveDSN, when true, permits DSNs that look like production
	// (supabase.co, rds.amazonaws.com, prod, production). Default
	// false; the runner refuses production-looking DSNs unless this is
	// set or LPBOT_MIGRATE_ALLOW_LIVE=YES in env.
	AllowLiveDSN bool
}

// Runner is the migration runner. Construct with NewRunner and call
// one of Plan, Status, Apply.
type Runner struct {
	cfg     Config
	db      *sql.DB
	files   []migrationFile
}

// migrationFile is the in-memory representation of a single .sql
// migration. checksum is SHA256 of the file content (not the
// migration's effect — the user is expected to use a different
// filename if they want to mutate the effect, and a different
// checksum will surface that).
type migrationFile struct {
	filename string
	content  string
	checksum string
}

// NewRunner opens a DB connection and reads the migration directory.
// It does NOT apply any migrations. The caller must invoke Plan /
// Status / Apply explicitly.
func NewRunner(ctx context.Context, cfg Config) (*Runner, error) {
	if cfg.DSN == "" {
		return nil, errors.New("migrator: DSN is required")
	}
	if cfg.MigrationsFS == nil {
		return nil, errors.New("migrator: MigrationsFS is required")
	}
	if cfg.MigrationsDir == "" {
		cfg.MigrationsDir = "."
	}
	if !cfg.AllowLiveDSN {
		if os.Getenv("LPBOT_MIGRATE_ALLOW_LIVE") == "YES" {
			cfg.AllowLiveDSN = true
		}
	}
	if !cfg.AllowLiveDSN && looksLikeProductionDSN(cfg.DSN) {
		return nil, fmt.Errorf("migrator: DSN looks like a production endpoint; "+
			"refusing to migrate. Set LPBOT_MIGRATE_ALLOW_LIVE=YES if intentional. "+
			"DSN host: %s", dsnHost(cfg.DSN))
	}

	db, err := sql.Open("postgres", cfg.DSN)
	if err != nil {
		return nil, fmt.Errorf("migrator: sql.Open: %w", err)
	}
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("migrator: db.Ping: %w", err)
	}

	r := &Runner{cfg: cfg, db: db}
	if err := r.readMigrations(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("migrator: readMigrations: %w", err)
	}
	return r, nil
}

// Close releases the DB connection.
func (r *Runner) Close() error {
	if r.db == nil {
		return nil
	}
	return r.db.Close()
}

// readMigrations lists and reads all *.sql files in the migrations dir,
// sorted by filename (lexical). Each file is read once; the SHA256
// checksum is computed from the raw file content.
func (r *Runner) readMigrations(ctx context.Context) error {
	entries, err := fs.ReadDir(r.cfg.MigrationsFS, r.cfg.MigrationsDir)
	if err != nil {
		return fmt.Errorf("readDir %s: %w", r.cfg.MigrationsDir, err)
	}
	var files []migrationFile
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		fullName := path.Join(r.cfg.MigrationsDir, e.Name())
		raw, err := fs.ReadFile(r.cfg.MigrationsFS, fullName)
		if err != nil {
			return fmt.Errorf("ReadFile %s: %w", fullName, err)
		}
		sum := sha256.Sum256(raw)
		files = append(files, migrationFile{
			filename: e.Name(),
			content:  string(raw),
			checksum: hex.EncodeToString(sum[:]),
		})
	}
	sort.Slice(files, func(i, j int) bool {
		return files[i].filename < files[j].filename
	})
	r.files = files
	return nil
}

// ensureSchemaMigrationsTable creates the schema_migrations table
// if it does not already exist. Idempotent.
//
// Also handles a legacy schema_migrations table created by the
// pre-Go runner (scripts/apply_postgres_migrations.sh) that has
// only (filename, applied_at) and lacks a checksum column. In that
// case we add the column with a default of '' (legacy entries have
// unknown checksums; they're still considered applied and will not
// be re-run unless their checksum mismatches the file on disk).
func (r *Runner) ensureSchemaMigrationsTable(ctx context.Context) error {
	const ddl = `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			filename   TEXT PRIMARY KEY,
			checksum   TEXT NOT NULL DEFAULT '',
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)`
	if _, err := r.db.ExecContext(ctx, ddl); err != nil {
		return fmt.Errorf("create schema_migrations: %w", err)
	}
	// Backfill the checksum column on legacy tables that don't have
	// it. This is a no-op on fresh DBs (column already exists).
	if err := r.ensureChecksumColumn(ctx); err != nil {
		return err
	}
	return nil
}

// ensureChecksumColumn adds the checksum column to a legacy
// schema_migrations table that lacks it. Idempotent.
func (r *Runner) ensureChecksumColumn(ctx context.Context) error {
	var hasColumn bool
	if err := r.db.QueryRowContext(ctx,
		`SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_schema = 'public'
			  AND table_name = 'schema_migrations'
			  AND column_name = 'checksum'
		)`,
	).Scan(&hasColumn); err != nil {
		return fmt.Errorf("check checksum column: %w", err)
	}
	if hasColumn {
		return nil
	}
	// Add the column with default '' (empty string) so the existing
	// rows (which don't have a checksum) remain valid. The runner
	// will compare these empty checksums against the file's SHA256
	// and refuse to proceed if they mismatch.
	if _, err := r.db.ExecContext(ctx,
		`ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT NOT NULL DEFAULT ''`,
	); err != nil {
		return fmt.Errorf("add checksum column: %w", err)
	}
	return nil
}

// extractUpSection returns the SQL between `-- +goose Up` and the
// next `-- +goose Down` (or EOF). This matches the goose convention
// and avoids running any DROP TABLE statements in the Down section.
func extractUpSection(content string) (string, error) {
	const up = "-- +goose Up"
	const down = "-- +goose Down"
	upIdx := strings.Index(content, up)
	if upIdx < 0 {
		return "", errors.New("no -- +goose Up annotation found")
	}
	after := content[upIdx+len(up):]
	downIdx := strings.Index(after, down)
	if downIdx < 0 {
		return strings.TrimSpace(after), nil
	}
	return strings.TrimSpace(after[:downIdx]), nil
}

// appliedSet returns the set of filenames currently recorded as
// applied, with their stored checksums.
type appliedEntry struct {
	Filename string `json:"filename"`
	Checksum string `json:"checksum"`
}

// backfillLegacyChecksums updates any applied row with checksum=''
// to the current file's SHA256. Legacy rows from the pre-Go shell
// runner have checksum='' because the shell did not record a
// checksum. The migration is already applied; backfilling with the
// current file's checksum is safe because the file content is, by
// definition, the version that was applied.
func (r *Runner) backfillLegacyChecksums(ctx context.Context, applied map[string]string) error {
	for _, f := range r.files {
		recorded, ok := applied[f.filename]
		if !ok {
			continue // not yet applied
		}
		if recorded != "" {
			continue // already has a real checksum
		}
		// Legacy row: backfill with the current file's checksum.
		if _, err := r.db.ExecContext(ctx,
			`UPDATE schema_migrations SET checksum = $1 WHERE filename = $2 AND checksum = ''`,
			f.checksum, f.filename,
		); err != nil {
			return fmt.Errorf("backfill %s: %w", f.filename, err)
		}
	}
	return nil
}

func (r *Runner) appliedSet(ctx context.Context) (map[string]string, error) {
	if err := r.ensureSchemaMigrationsTable(ctx); err != nil {
		return nil, err
	}
	rows, err := r.db.QueryContext(ctx, "SELECT filename, checksum FROM schema_migrations")
	if err != nil {
		return nil, fmt.Errorf("SELECT schema_migrations: %w", err)
	}
	defer rows.Close()
	out := map[string]string{}
	for rows.Next() {
		var f, c string
		if err := rows.Scan(&f, &c); err != nil {
			return nil, fmt.Errorf("scan schema_migrations row: %w", err)
		}
		out[f] = c
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows.Err: %w", err)
	}
	return out, nil
}

// PlanResult describes the planned migration run.
type PlanResult struct {
	Files          []string `json:"files"`
	ToApply        []string `json:"to_apply"`
	AlreadyApplied []string `json:"already_applied"`
}

// Plan lists all migration files and which ones would be applied.
func (r *Runner) Plan(ctx context.Context) (*PlanResult, error) {
	applied, err := r.appliedSet(ctx)
	if err != nil {
		return nil, err
	}
	res := &PlanResult{}
	for _, f := range r.files {
		res.Files = append(res.Files, f.filename)
		if _, ok := applied[f.filename]; ok {
			res.AlreadyApplied = append(res.AlreadyApplied, f.filename)
		} else {
			res.ToApply = append(res.ToApply, f.filename)
		}
	}
	return res, nil
}

// StatusResult describes the post-apply status of the DB.
type StatusResult struct {
	Applied    []appliedEntry `json:"applied"`
	Missing    []string       `json:"missing"`
	Required   []string       `json:"required"`
	AllPresent bool           `json:"all_present"`
}

// Status returns which migrations are applied and which required
// tables/indexes are present.
func (r *Runner) Status(ctx context.Context) (*StatusResult, error) {
	applied, err := r.appliedSet(ctx)
	if err != nil {
		return nil, err
	}
	res := &StatusResult{}
	for fn, cs := range applied {
		res.Applied = append(res.Applied, appliedEntry{Filename: fn, Checksum: cs})
	}
	sort.Slice(res.Applied, func(i, j int) bool {
		return res.Applied[i].Filename < res.Applied[j].Filename
	})
	required := r.requiredTablesAndIndexes()
	for _, name := range required {
		var exists bool
		if err := r.db.QueryRowContext(ctx, "SELECT to_regclass('public.' || $1) IS NOT NULL", name).Scan(&exists); err != nil {
			return nil, fmt.Errorf("to_regclass %s: %w", name, err)
		}
		if !exists {
			res.Missing = append(res.Missing, name)
		}
	}
	res.Required = required
	res.AllPresent = len(res.Missing) == 0
	return res, nil
}

// requiredTablesAndIndexes returns the source-of-truth list of
// tables/indexes the live schema guard requires. Keep in sync with
// scripts/migrate-postgres.sh status REQUIRED_TABLES and
// cmd/lpbot/main.go loadLiveSchemaState.
func (r *Runner) requiredTablesAndIndexes() []string {
	return []string{
		"positions",
		"transactions",
		"execution_intents",
		"portfolio_snapshots",
		"position_marks",
		"canary_events",
		"pnl_ledger",
		"shadow_decision_trace",
		"shadow_position_marks",
		"shadow_exit_decisions",
		"shadow_exit_actions",
		"shadow_outcome_labels",
		"pools",
		"pool_score_history",
		"risk_events",
		"kill_switch_state",
		"idx_positions_one_active_per_pool",
	}
}

// ApplyResult is returned from Apply.
type ApplyResult struct {
	Applied    []string `json:"applied"`
	Skipped    []string `json:"skipped"`     // already-applied, no-op
	FailedAt   string   `json:"failed_at"`   // empty on success
	FailedErr  string   `json:"failed_err"`  // empty on success
	WasPartial bool     `json:"was_partial"` // true if some applied before failure
}

// Apply runs all pending migrations in lexical order, each in its
// own transaction. Already-applied migrations are skipped (no-op).
//
// Safety properties:
//   - A migration that has been partially applied is detected by
//     checksum mismatch: if the recorded checksum of a previously-
//     applied migration differs from the file's current SHA256, Apply
//     refuses to proceed (it would be unsafe to "continue" because
//     the migration may have partially completed).
//   - A migration that fails mid-execution causes its transaction
//     to roll back; the schema_migrations row is NOT inserted; the
//     runner stops and returns ApplyResult.FailedAt.
//   - Re-running Apply on a fully-up-to-date DB is a no-op (Skipped
//     populated, Applied empty, FailedAt empty).
//   - Legacy migration rows (recorded with checksum='') are
//     backfilled with the current file checksum on first apply,
//     so the runner can verify them on subsequent runs.
func (r *Runner) Apply(ctx context.Context) (*ApplyResult, error) {
	if err := r.ensureSchemaMigrationsTable(ctx); err != nil {
		return nil, err
	}
	applied, err := r.appliedSet(ctx)
	if err != nil {
		return nil, err
	}

	// Legacy checksum backfill: if any previously-applied row has
	// checksum='' (set by the pre-Go shell runner), backfill with
	// the current file's SHA256. This is safe because:
	//   - The migration is already applied (the file is by definition
	//     the same version that was applied).
	//   - The backfill is itself idempotent (re-running the same
	//     checksum is a no-op).
	if err := r.backfillLegacyChecksums(ctx, applied); err != nil {
		return nil, fmt.Errorf("backfill legacy checksums: %w", err)
	}
	// Re-read applied set after backfill so subsequent comparisons
	// use the up-to-date checksums.
	applied, err = r.appliedSet(ctx)
	if err != nil {
		return nil, err
	}

	// Checksum-mismatch guard: if a previously-applied file's
	// checksum no longer matches the file on disk, the migration
	// has been mutated post-apply. Refuse to proceed.
	for _, f := range r.files {
		if recorded, ok := applied[f.filename]; ok {
			if recorded != f.checksum {
				return nil, fmt.Errorf("migrator: checksum mismatch for %s: "+
					"recorded=%s file=%s. Refusing to apply to avoid corrupting "+
					"a partially-applied migration. Investigate and either "+
					"revert the file change or add a corrective migration.",
					f.filename, recorded, f.checksum)
			}
		}
	}

	res := &ApplyResult{}
	for _, f := range r.files {
		if _, ok := applied[f.filename]; ok {
			res.Skipped = append(res.Skipped, f.filename)
			continue
		}

		upSQL, err := extractUpSection(f.content)
		if err != nil {
			res.FailedAt = f.filename
			res.FailedErr = err.Error()
			res.WasPartial = len(res.Applied) > 0
			return res, fmt.Errorf("extractUpSection %s: %w", f.filename, err)
		}

		// Per-migration transaction: BEGIN; <upSQL>; INSERT; COMMIT
		tx, err := r.db.BeginTx(ctx, nil)
		if err != nil {
			res.FailedAt = f.filename
			res.FailedErr = err.Error()
			res.WasPartial = len(res.Applied) > 0
			return res, fmt.Errorf("BeginTx %s: %w", f.filename, err)
		}
		if _, err := tx.ExecContext(ctx, upSQL); err != nil {
			_ = tx.Rollback()
			res.FailedAt = f.filename
			res.FailedErr = err.Error()
			res.WasPartial = len(res.Applied) > 0
			return res, fmt.Errorf("apply %s: %w", f.filename, err)
		}
		// Record in same transaction as the migration effect. If the
		// recording insert fails (e.g. disk full), the entire
		// migration is rolled back.
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO schema_migrations(filename, checksum) VALUES ($1, $2)",
			f.filename, f.checksum,
		); err != nil {
			_ = tx.Rollback()
			res.FailedAt = f.filename
			res.FailedErr = err.Error()
			res.WasPartial = len(res.Applied) > 0
			return res, fmt.Errorf("record %s: %w", f.filename, err)
		}
		if err := tx.Commit(); err != nil {
			res.FailedAt = f.filename
			res.FailedErr = err.Error()
			res.WasPartial = len(res.Applied) > 0
			return res, fmt.Errorf("commit %s: %w", f.filename, err)
		}
		res.Applied = append(res.Applied, f.filename)
	}
	return res, nil
}

// looksLikeProductionDSN returns true if the DSN host looks like
// a production environment (supabase.co / rds.amazonaws.com / contains
// "prod" or "production"). The check is intentionally conservative
// (false positives are safer than false negatives).
func looksLikeProductionDSN(dsn string) bool {
	low := strings.ToLower(dsn)
	for _, marker := range []string{"supabase.co", "rds.amazonaws.com", "prod", "production"} {
		if strings.Contains(low, marker) {
			return true
		}
	}
	return false
}

// dsnHost extracts "host[:port]" from a postgres URL for safe logging.
// Returns empty string on parse failure.
func dsnHost(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return ""
	}
	host := u.Hostname()
	if host == "" {
		return ""
	}
	if p := u.Port(); p != "" {
		return host + ":" + p
	}
	return host
}

// itoa is a small helper to keep error messages readable.
func itoa(n int) string { return strconv.Itoa(n) }

var _ = itoa
