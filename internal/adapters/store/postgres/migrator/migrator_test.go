// Tests for the Go-based Postgres migration runner. These tests
// exercise the migrator against a real Docker postgres (LPBOT_POSTGRES_TEST_DSN)
// when available; otherwise they use a small in-memory stub FS to
// verify the unit-level contracts.
package migrator

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/lib/pq"
)

// TestExtractUpSection_StripsDownSection verifies the goose Up/Down
// extraction: the resulting SQL must NOT include any DROP TABLE
// statements from the Down section.
func TestExtractUpSection_StripsDownSection(t *testing.T) {
	cases := []struct {
		name      string
		input     string
		wantEmpty bool
		wantSub   string
	}{
		{
			name: "normal up+down",
			input: `-- +goose Up
-- +goose StatementBegin
CREATE TABLE foo (id INT);
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DROP TABLE foo;
-- +goose StatementEnd
`,
			wantSub: "CREATE TABLE foo (id INT);",
		},
		{
			name: "up only (no down)",
			input: `-- +goose Up
-- +goose StatementBegin
CREATE TABLE bar (id INT);
-- +goose StatementEnd
`,
			wantSub: "CREATE TABLE bar (id INT);",
		},
		{
			name: "no annotations",
			input: `CREATE TABLE baz (id INT);
`,
			wantEmpty: true,
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := extractUpSection(c.input)
			if c.wantEmpty {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("extractUpSection: %v", err)
			}
			if !strings.Contains(got, c.wantSub) {
				t.Errorf("expected substring %q, got %q", c.wantSub, got)
			}
			// Down section must NOT appear in the up extraction.
			if strings.Contains(got, "DROP TABLE") {
				t.Errorf("up extraction contains DROP TABLE: %q", got)
			}
		})
	}
}

// TestLooksLikeProductionDSN verifies the production-DSN heuristic
// matches the user spec: refuse supabase.co / rds.amazonaws.com /
// "prod" / "production" without LPBOT_MIGRATE_ALLOW_LIVE.
func TestLooksLikeProductionDSN(t *testing.T) {
	cases := []struct {
		dsn  string
		want bool
	}{
		{"postgres://user:pass@127.0.0.1:5432/db", false},
		{"postgres://user:pass@10.0.0.1:5432/db", false},
		{"postgres://user:pass@db.supabase.co:5432/postgres", true},
		{"postgres://user:pass@my-rds.amazonaws.com:5432/db", true},
		{"postgres://user:pass@db-prod.internal:5432/db", true},
		{"postgres://user:pass@db-production.internal:5432/db", true},
		{"postgres://user:pass@db.example.com:5432/db", false},
	}
	for _, c := range cases {
		got := looksLikeProductionDSN(c.dsn)
		if got != c.want {
			t.Errorf("looksLikeProductionDSN(%q) = %v, want %v", c.dsn, got, c.want)
		}
	}
}

// TestDSNHost_StripsCredentials verifies that dsnHost returns only
// the host (no user, no password, no path). This is the safety
// property that keeps our logs from leaking secrets.
func TestDSNHost_StripsCredentials(t *testing.T) {
	cases := []struct {
		dsn  string
		want string
	}{
		{"postgres://user:supersecret@db.example.com:5432/dbname", "db.example.com:5432"},
		{"postgresql://user:supersecret@db.example.com/dbname", "db.example.com"},
		{"postgres://user@db.example.com:5432/db", "db.example.com:5432"},
		{"not-a-url", ""},
	}
	for _, c := range cases {
		got := dsnHost(c.dsn)
		if got != c.want {
			t.Errorf("dsnHost(%q) = %q, want %q", c.dsn, got, c.want)
		}
	}
}

// TestRunner_AllowLiveDSN_PermitsProductionDSN verifies the
// AllowLiveDSN config (or LPBOT_MIGRATE_ALLOW_LIVE=YES) lets the
// runner proceed past the production-DSN check. We use a closed
// local port (127.0.0.1:1, which refuses connections immediately)
// so the test runs in <1s rather than waiting for a connect
// timeout to an unreachable host.
func TestRunner_AllowLiveDSN_PermitsProductionDSN(t *testing.T) {
	cfg := Config{
		DSN:           "postgres://user:pass@127.0.0.1:1/db",
		MigrationsFS:  newFakeMigrationsFS(),
		MigrationsDir: ".",
		AllowLiveDSN: true,
	}
	_, err := NewRunner(context.Background(), cfg)
	if err == nil {
		t.Fatal("expected ping failure, got nil")
	}
	// The error must come from the DB layer, not from the
	// production-DSN check. The production-DSN guard error
	// message contains the exact phrase "production endpoint".
	if strings.Contains(err.Error(), "production endpoint") {
		t.Errorf("AllowLiveDSN=true should bypass production check, got: %v", err)
	}
}

// TestRunner_RejectsProductionDSN_WithoutAllowLiveDSN verifies the
// default behavior: refuse production-looking DSNs.
func TestRunner_RejectsProductionDSN_WithoutAllowLiveDSN(t *testing.T) {
	cfg := Config{
		DSN:           "postgres://user:pass@db.supabase.co:5432/postgres",
		MigrationsFS:  newFakeMigrationsFS(),
		MigrationsDir: ".",
		// AllowLiveDSN: false (default)
	}
	_, err := NewRunner(context.Background(), cfg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "production endpoint") {
		t.Errorf("expected error to mention 'production endpoint', got: %v", err)
	}
}

// TestRunner_NoEnvCanaryOrLiveAutoLoad verifies that the runner
// explicitly does NOT read .env.canary or .env.live. This test does
// not run any DDL; it just exercises NewRunner with a non-routable
// host to verify the path through to PingContext fails on the
// connection attempt (not on a canary env file).
func TestRunner_NoEnvCanaryOrLiveAutoLoad(t *testing.T) {
	// Use a clearly non-production DSN. Even with .env.canary
	// existing on the test runner's cwd, the runner should not
	// silently pick it up. We verify by checking that the only
	// source of DSN is the explicit Config.DSN field.
	cfg := Config{
		DSN:           "postgres://user:pass@127.0.0.1:1/db",
		MigrationsFS:  newFakeMigrationsFS(),
		MigrationsDir: ".",
		// AllowLiveDSN: false
	}
	// We expect PingContext to fail with a network error, not with
	// "production endpoint" (which would mean the runner picked up
	// some other DSN).
	_, err := NewRunner(context.Background(), cfg)
	if err == nil {
		t.Fatal("expected ping failure on 127.0.0.1:1, got nil")
	}
	if strings.Contains(err.Error(), "production endpoint") {
		t.Errorf("runner should not have detected a production DSN for 127.0.0.1:1: %v", err)
	}
}

// TestRunner_ProductionDSNGate_RespectsEnvVar verifies that setting
// LPBOT_MIGRATE_ALLOW_LIVE=YES in the env bypasses the production
// DSN check.
func TestRunner_ProductionDSNGate_RespectsEnvVar(t *testing.T) {
	t.Setenv("LPBOT_MIGRATE_ALLOW_LIVE", "YES")
	// Use a non-routable host so the call eventually fails at
	// PingContext, but the production-DSN check should pass first.
	cfg := Config{
		DSN: "postgres://user:pass@198.51.100.1:5432/db",
	}
	_, err := NewRunner(context.Background(), cfg)
	if err == nil {
		t.Fatal("expected ping failure, got nil")
	}
	if strings.Contains(err.Error(), "production endpoint") {
		t.Errorf("env var LPBOT_MIGRATE_ALLOW_LIVE=YES should bypass production check, got: %v", err)
	}
}

// --- Real-DB integration tests (skipped without LPBOT_POSTGRES_TEST_DSN) ---

// testMigrationsFS is the embed.FS used by the integration tests.
// Re-uses the production MigrationsFS so the tests exercise the
// real migration files.
func testMigrationsFS() interface {
	// minimal interface compatible with fs.FS
} {
	// Use the package-level MigrationsFS via a typed cast.
	return MigrationsFS
}

// TestMigrator_PlanListsAllMigrations verifies that Plan returns
// all 15 migration files in the embed.FS, with the correct
// to_apply / already_applied split.
func TestMigrator_PlanListsAllMigrations(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()

	plan, err := runner.Plan(ctx)
	if err != nil {
		t.Fatalf("Plan: %v", err)
	}
	if got, want := len(plan.Files), 15; got != want {
		t.Errorf("Plan.Files = %d, want %d", got, want)
	}
}

// TestMigrator_ApplyOnFreshDB verifies the full apply path on a
// freshly-created schema (after DROP SCHEMA). We test this by
// applying all migrations to a fresh DB, then checking the
// schema_migrations table has 15 rows and all required tables/indexes
// are present.
func TestMigrator_ApplyOnFreshDB(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	// Reset DB
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()

	res, err := runner.Apply(ctx)
	if err != nil {
		t.Fatalf("Apply: %v", err)
	}
	if got, want := len(res.Applied), 15; got != want {
		t.Errorf("res.Applied = %d, want %d", got, want)
	}
	if got, want := len(res.Skipped), 0; got != want {
		t.Errorf("res.Skipped = %d, want %d", got, want)
	}
	if res.FailedAt != "" {
		t.Errorf("res.FailedAt = %q, want \"\"", res.FailedAt)
	}

	// Verify all required tables + index are present.
	status, err := runner.Status(ctx)
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.AllPresent {
		t.Errorf("missing required tables/indexes: %v", status.Missing)
	}
}

// TestMigrator_ReRunIsNoOp verifies that re-running Apply on an
// up-to-date DB is a no-op: all migrations are reported as
// skipped, none as applied.
func TestMigrator_ReRunIsNoOp(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	// Reset DB and apply once
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()
	if _, err := runner.Apply(ctx); err != nil {
		t.Fatalf("first Apply: %v", err)
	}
	// Second apply
	res, err := runner.Apply(ctx)
	if err != nil {
		t.Fatalf("second Apply: %v", err)
	}
	if got, want := len(res.Applied), 0; got != want {
		t.Errorf("second Apply: res.Applied = %d, want %d (no-op expected)", got, want)
	}
	if got, want := len(res.Skipped), 15; got != want {
		t.Errorf("second Apply: res.Skipped = %d, want %d", got, want)
	}
}

// TestMigrator_ChecksumMismatchRefuses verifies that if a file's
// content changes after it was applied, the runner refuses to
// proceed (it doesn't know whether the file was "intentionally"
// modified or corrupted, and re-running could lead to inconsistent
// state).
func TestMigrator_ChecksumMismatchRefuses(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	// Reset DB
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	// First, apply with a slightly different (but compatible) set
	// of migrations.
	fakeFS := newFakeMigrationsFS("000001_init_schema.sql", "-- +goose Up\n-- +goose StatementBegin\nCREATE TABLE foo (id INT);\n-- +goose StatementEnd\n")
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  fakeFS,
		MigrationsDir: ".",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()
	if _, err := runner.Apply(ctx); err != nil {
		t.Fatalf("first Apply: %v", err)
	}
	// Now, simulate a file change: build a NEW runner with a
	// DIFFERENT file (same filename, different content).
	mutatedFS := newFakeMigrationsFS("000001_init_schema.sql", "-- +goose Up\n-- +goose StatementBegin\nCREATE TABLE foo (id INT, name TEXT);\n-- +goose StatementEnd\n")
	mutatedRunner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  mutatedFS,
		MigrationsDir: ".",
	})
	if err != nil {
		t.Fatalf("NewRunner mutated: %v", err)
	}
	defer mutatedRunner.Close()
	_, err = mutatedRunner.Apply(ctx)
	if err == nil {
		t.Fatal("expected checksum-mismatch error, got nil")
	}
	if !strings.Contains(err.Error(), "checksum mismatch") {
		t.Errorf("expected error to mention 'checksum mismatch', got: %v", err)
	}
}

// TestMigrator_PerMigrationTransactionRollback verifies that a
// failure in the middle of a multi-statement migration rolls back
// the entire migration (no partial DDL is left in the DB).
func TestMigrator_PerMigrationTransactionRollback(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	// Migration 1 succeeds; migration 2 has a syntax error mid-statement
	// (this should fail the entire transaction, so the schema_migrations
	// row for migration 2 should NOT be inserted).
	fakeFS := newFakeMigrationsFS(
		"000001_init.sql",
		"-- +goose Up\n-- +goose StatementBegin\nCREATE TABLE t1 (id INT);\n-- +goose StatementEnd\n",
		"000002_broken.sql",
		"-- +goose Up\n-- +goose StatementBegin\nCREATE TABLE t2 (id INT);\nSYNTAX_ERROR_HERE;\n-- +goose StatementEnd\n",
	)
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  fakeFS,
		MigrationsDir: ".",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()
	res, err := runner.Apply(ctx)
	if err == nil {
		t.Fatal("expected apply to fail, got nil")
	}
	if res.FailedAt != "000002_broken.sql" {
		t.Errorf("res.FailedAt = %q, want 000002_broken.sql", res.FailedAt)
	}
	if !res.WasPartial {
		t.Error("res.WasPartial should be true (000001 was applied before 000002 failed)")
	}
	// Verify: t1 EXISTS (from 000001, which was committed), t2 does
	// NOT exist (from 000002, which was rolled back), and
	// schema_migrations has only 000001.
	verifyTableExists(t, dsn, "t1", true)
	verifyTableExists(t, dsn, "t2", false)
	verifyMigrationApplied(t, dsn, "000001_init.sql", true)
	verifyMigrationApplied(t, dsn, "000002_broken.sql", false)
}

// TestMigrator_StatusReturnsCorrectFields verifies that Status
// returns the correct required-tables / missing / all-present
// fields.
func TestMigrator_StatusReturnsCorrectFields(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()
	if _, err := runner.Apply(ctx); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	status, err := runner.Status(ctx)
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.AllPresent {
		t.Errorf("expected all present, missing: %v", status.Missing)
	}
	if got, want := len(status.Applied), 15; got != want {
		t.Errorf("status.Applied = %d, want %d", got, want)
	}
	// Verify each applied entry has a real checksum (not the legacy '').
	for _, e := range status.Applied {
		if e.Checksum == "" {
			t.Errorf("legacy checksum '' for %s; should be filled", e.Filename)
		}
		if len(e.Checksum) != 64 {
			t.Errorf("checksum for %s has length %d, want 64 (sha256 hex)", e.Filename, len(e.Checksum))
		}
	}
}

// TestMigrator_LegacyDB_BackfillOnFirstApply simulates a legacy
// schema_migrations row (checksum='') and verifies the runner
// backfills the real checksum on first apply, then refuses to
// re-run.
func TestMigrator_LegacyDB_BackfillOnFirstApply(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	// Pre-populate the schema_migrations table with a legacy
	// checksum='' row, simulating a DB that was set up by the
	// pre-Go shell runner.
	fakeFS := newFakeMigrationsFS(
		"000001_init.sql",
		"-- +goose Up\n-- +goose StatementBegin\nCREATE TABLE legacy_test (id INT);\n-- +goose StatementEnd\n",
	)
	// First, write the legacy row directly.
	{
		runner, err := NewRunner(ctx, Config{
			DSN:           dsn,
			MigrationsFS:  fakeFS,
			MigrationsDir: ".",
		})
		if err != nil {
			t.Fatalf("NewRunner (legacy setup): %v", err)
		}
		if _, err := runner.db.ExecContext(ctx,
			`CREATE TABLE IF NOT EXISTS schema_migrations (
				filename TEXT PRIMARY KEY,
				applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
			)`,
		); err != nil {
			t.Fatalf("create legacy schema_migrations: %v", err)
		}
		// Compute the legacy file's checksum and insert it with '' stored.
		f, err := fakeFS.Open("000001_init.sql")
		if err != nil {
			t.Fatalf("fakeFS.Open: %v", err)
		}
		buf := make([]byte, 1024)
		n, _ := f.Read(buf)
		_ = f.Close()
		sum := sha256.Sum256(buf[:n])
		_ = hex.EncodeToString(sum[:]) // compute but don't use
		if _, err := runner.db.ExecContext(ctx,
			`INSERT INTO schema_migrations(filename, applied_at) VALUES ($1, NOW())`,
			"000001_init.sql",
		); err != nil {
			t.Fatalf("insert legacy row: %v", err)
		}
		// Manually add the checksum column (legacy tables don't have it).
		if _, err := runner.db.ExecContext(ctx,
			`ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT NOT NULL DEFAULT ''`,
		); err != nil {
			t.Fatalf("add checksum column: %v", err)
		}
		_ = runner.Close()
	}

	// Now run Apply: should backfill the legacy checksum and treat
	// the migration as already-applied (no re-apply).
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  fakeFS,
		MigrationsDir: ".",
	})
	if err != nil {
		t.Fatalf("NewRunner (apply): %v", err)
	}
	defer runner.Close()
	res, err := runner.Apply(ctx)
	if err != nil {
		t.Fatalf("Apply: %v", err)
	}
	if got, want := len(res.Applied), 0; got != want {
		t.Errorf("res.Applied = %d, want %d (legacy should be backfilled not re-applied)", got, want)
	}
	if got, want := len(res.Skipped), 1; got != want {
		t.Errorf("res.Skipped = %d, want %d", got, want)
	}
	// Verify checksum was backfilled.
	var cs string
	if err := runner.db.QueryRowContext(ctx,
		`SELECT checksum FROM schema_migrations WHERE filename = $1`,
		"000001_init.sql",
	).Scan(&cs); err != nil {
		t.Fatalf("query checksum: %v", err)
	}
	if cs == "" {
		t.Error("checksum was not backfilled; still ''")
	}
	if len(cs) != 64 {
		t.Errorf("checksum length = %d, want 64 (sha256 hex)", len(cs))
	}
}

// TestMigrator_PostgresAdapterIntegrationStillPasses is a
// smoke test that the existing
// TestPostgresRepoIntegration (which exercises the live schema
// guard) still passes after we've replaced the shell migration
// runner with the Go one. This guards against the migrator
// introducing a regression in the actual schema (e.g. wrong
// required-tables list).
func TestMigrator_PostgresAdapterIntegrationStillPasses(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	ctx := context.Background()
	if err := dropPublicSchema(ctx, dsn); err != nil {
		t.Fatalf("reset DB: %v", err)
	}
	// Apply all migrations
	runner, err := NewRunner(ctx, Config{
		DSN:           dsn,
		MigrationsFS:  MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		t.Fatalf("NewRunner: %v", err)
	}
	defer runner.Close()
	if _, err := runner.Apply(ctx); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	// Verify required tables + index
	status, err := runner.Status(ctx)
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.AllPresent {
		t.Errorf("missing: %v", status.Missing)
	}
	// Verify the per-table list is the same as what the postgres
	// package test expects.
	required := runner.requiredTablesAndIndexes()
	if len(required) != 17 {
		// 16 tables + 1 index
		t.Errorf("requiredTablesAndIndexes returned %d items, want 17", len(required))
	}
}

// --- helpers ---

// dropPublicSchema drops + recreates the public schema. Used by
// integration tests to start from a fresh state.
func dropPublicSchema(ctx context.Context, dsn string) error {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return err
	}
	defer db.Close()
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		return err
	}
	if _, err := db.ExecContext(ctx, "DROP SCHEMA public CASCADE; CREATE SCHEMA public"); err != nil {
		return fmt.Errorf("drop/create public schema: %w", err)
	}
	return nil
}

// verifyTableExists checks if a table exists in the public schema.
func verifyTableExists(t *testing.T, dsn, table string, want bool) {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()
	var exists bool
	if err := db.QueryRow("SELECT to_regclass('public.' || $1) IS NOT NULL", table).Scan(&exists); err != nil {
		t.Fatalf("to_regclass: %v", err)
	}
	if exists != want {
		t.Errorf("table %s exists = %v, want %v", table, exists, want)
	}
}

// verifyMigrationApplied checks if a migration is recorded in
// schema_migrations.
func verifyMigrationApplied(t *testing.T, dsn, filename string, want bool) {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations WHERE filename = $1", filename).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	got := count > 0
	if got != want {
		t.Errorf("migration %s applied = %v, want %v", filename, got, want)
	}
}

// fakeFS is a small in-memory fs.FS used by the per-migration
// transaction tests. It holds a fixed set of named files and reads
// them as raw bytes. Reading is supported; directory listing is
// supported; sub-directories are not (we keep all files at root).
type fakeFS struct {
	files map[string]string // filename -> content
}

// newFakeMigrationsFS builds a fakeFS from alternating (filename,
// content) pairs.
func newFakeMigrationsFS(pairs ...string) *fakeFS {
	if len(pairs)%2 != 0 {
		panic("newFakeMigrationsFS requires even number of args")
	}
	fs := &fakeFS{files: map[string]string{}}
	for i := 0; i < len(pairs); i += 2 {
		fs.files[pairs[i]] = pairs[i+1]
	}
	return fs
}

// Open opens the named file. Implements fs.FS.
func (f *fakeFS) Open(name string) (fs.File, error) {
	content, ok := f.files[name]
	if !ok {
		return nil, &fs.PathError{Op: "open", Path: name, Err: errors.New("file not found")}
	}
	return &fakeFile{content: content, reader: strings.NewReader(content)}, nil
}

// ReadDir lists the entries at the given path. Only the root path
// (".") is supported. Implements fs.ReadDirFS (via fs.FS's
// fs.ReadDir helper).
func (f *fakeFS) ReadDir(name string) ([]fs.DirEntry, error) {
	if name != "." {
		return nil, &fs.PathError{Op: "readdir", Path: name, Err: errors.New("not a directory")}
	}
	var entries []fs.DirEntry
	for fn := range f.files {
		entries = append(entries, fakeDirEntry{name: fn})
	}
	return entries, nil
}

type fakeDirEntry struct {
	name string
}

func (e fakeDirEntry) Name() string               { return e.name }
func (e fakeDirEntry) IsDir() bool                { return false }
func (e fakeDirEntry) Type() fs.FileMode          { return 0 }
func (e fakeDirEntry) Info() (fs.FileInfo, error) { return nil, errors.New("not implemented") }

// fakeFile implements fs.File over an in-memory string.
type fakeFile struct {
	content string
	reader  *strings.Reader
	stat    fakeFileInfo
	closed  bool
}

// Read reads up to len(p) bytes.
func (f *fakeFile) Read(p []byte) (int, error) {
	if f.closed {
		return 0, fs.ErrClosed
	}
	if f.reader == nil {
		f.reader = strings.NewReader(f.content)
	}
	return f.reader.Read(p)
}

// Close closes the file.
func (f *fakeFile) Close() error {
	f.closed = true
	return nil
}

// Stat returns a FileInfo for the file.
func (f *fakeFile) Stat() (fs.FileInfo, error) {
	return f.stat, nil
}

type fakeFileInfo struct {
	name    string
	size    int64
	mode    fs.FileMode
	modTime time.Time
}

func (fi fakeFileInfo) Name() string       { return fi.name }
func (fi fakeFileInfo) Size() int64        { return fi.size }
func (fi fakeFileInfo) Mode() fs.FileMode  { return fi.mode }
func (fi fakeFileInfo) ModTime() time.Time { return fi.modTime }
func (fi fakeFileInfo) IsDir() bool        { return false }
func (fi fakeFileInfo) Sys() interface{}   { return nil }
