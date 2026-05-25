// Package sqlite provides SQLite storage adapters.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	_ "github.com/mattn/go-sqlite3"
	"github.com/pressly/goose/v3"
)

// MigrationsDir is the directory containing SQLite migration files.
const MigrationsDir = "migrations/sqlite"

// MigrateUp runs all pending migrations from migrations/sqlite/ directory.
// It applies the schemaPrefix to all table names (e.g., dryrun_, shadow_, live_).
// Returns error if migrations fail.
func MigrateUp(dbPath string, schemaPrefix string) error {
	return runMigrations(dbPath, schemaPrefix, "up")
}

// MigrateDown rolls back the most recent migration.
// It applies the schemaPrefix to all table names (e.g., dryrun_, shadow_, live_).
// Returns error if rollback fails.
func MigrateDown(dbPath string, schemaPrefix string) error {
	return runMigrations(dbPath, schemaPrefix, "down")
}

// runMigrations executes goose migrations with schema prefix applied.
func runMigrations(dbPath string, schemaPrefix string, direction string) error {
	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return fmt.Errorf("failed to open database: %w", err)
	}
	defer db.Close()

	// Verify database connection
	if err := db.Ping(); err != nil {
		return fmt.Errorf("failed to ping database: %w", err)
	}

	// Get migrations directory
	migrationsAbsDir, err := getMigrationsDir()
	if err != nil {
		return fmt.Errorf("failed to get migrations dir: %w", err)
	}

	// Create temporary directory for prefixed migrations
	tmpDir := filepath.Join(os.TempDir(), "lpbot-migrations-"+schemaPrefix)
	if err := os.MkdirAll(tmpDir, 0755); err != nil {
		return fmt.Errorf("failed to create temp migrations dir: %w", err)
	}

	// Clean up temp directory when function returns
	defer os.RemoveAll(tmpDir)

	// Copy and transform migration files with prefix applied
	if err := copyMigrationsWithPrefix(migrationsAbsDir, tmpDir, schemaPrefix); err != nil {
		return fmt.Errorf("failed to copy migrations: %w", err)
	}

	// Create goose provider with isolated configuration
	versionTable := schemaPrefix + "goose_db_version"
	provider, err := goose.NewProvider(
		goose.DialectSQLite3,
		db,
		os.DirFS(tmpDir),
		goose.WithTableName(versionTable),
		goose.WithDisableGlobalRegistry(true),
	)
	if err != nil {
		return fmt.Errorf("failed to create goose provider: %w", err)
	}

	// Run migrations using provider
	ctx := context.Background()
	if direction == "up" {
		if _, err := provider.Up(ctx); err != nil {
			return fmt.Errorf("goose up failed: %w", err)
		}
	} else {
		if _, err := provider.Down(ctx); err != nil {
			return fmt.Errorf("goose down failed: %w", err)
		}
	}

	return nil
}

// copyMigrationsWithPrefix copies migration files to a temp directory with schema prefix applied.
func copyMigrationsWithPrefix(srcDir, dstDir, schemaPrefix string) error {
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return fmt.Errorf("failed to read migrations dir: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}

		srcPath := filepath.Join(srcDir, entry.Name())
		data, err := os.ReadFile(srcPath)
		if err != nil {
			return fmt.Errorf("failed to read migration %s: %w", entry.Name(), err)
		}

		// Apply schema prefix to SQL content
		transformed := applySchemaPrefix(string(data), schemaPrefix)

		dstPath := filepath.Join(dstDir, entry.Name())
		if err := os.WriteFile(dstPath, []byte(transformed), 0644); err != nil {
			return fmt.Errorf("failed to write migration %s: %w", entry.Name(), err)
		}
	}

	return nil
}

// applySchemaPrefix replaces table names with prefixed versions in SQL content.
func applySchemaPrefix(sql string, prefix string) string {
	// Pattern to match table names in SQL statements
	// Matches: CREATE TABLE, CREATE INDEX, DROP TABLE, FOREIGN KEY, REFERENCES, INSERT INTO, UPDATE, DELETE FROM
	patterns := []string{
		`(?i)\b(positions)\b`,
		`(?i)\b(orders)\b`,
		`(?i)\b(transactions)\b`,
		`(?i)\b(pool_states)\b`,
		`(?i)\b(pools)\b`,
		`(?i)\b(pool_score_history)\b`,
		`(?i)\b(pnl_ledger)\b`,
		`(?i)\b(processed_events)\b`,
		`(?i)\b(config_snapshots)\b`,
		`(?i)\b(reconciliation_log)\b`,
		`(?i)\b(risk_events)\b`,
		`(?i)\b(ledger)\b`,
		`(?i)\b(kill_switch_state)\b`,
		`(?i)\b(goose_db_version)\b`,
	}

	result := sql
	for _, pattern := range patterns {
		re := regexp.MustCompile(pattern)
		result = re.ReplaceAllString(result, prefix+"$1")
	}

	return result
}

// getMigrationsDir returns the absolute path to the migrations directory.
func getMigrationsDir() (string, error) {
	// Start from the current working directory and walk up
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("failed to get working directory: %w", err)
	}

	// Try progressively walking up from current directory
	for {
		candidate := filepath.Join(cwd, "migrations", "sqlite")
		info, err := os.Stat(candidate)
		if err == nil && info.IsDir() {
			return candidate, nil
		}

		// Move up one directory
		parent := filepath.Dir(cwd)
		if parent == cwd {
			break // Reached root
		}
		cwd = parent
	}

	// Fallback: try common relative paths
	candidates := []string{
		"migrations/sqlite",
		"./migrations/sqlite",
		"../migrations/sqlite",
		"../../migrations/sqlite",
	}

	for _, candidate := range candidates {
		absPath, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}

		info, err := os.Stat(absPath)
		if err == nil && info.IsDir() {
			return absPath, nil
		}
	}

	return "", fmt.Errorf("migrations directory not found")
}
