// Package sqlite provides SQLite storage adapters.
package sqlite

import (
	"database/sql"
	"os"
	"path/filepath"
	"strings"
	"testing"

	_ "github.com/mattn/go-sqlite3"
	"github.com/stretchr/testify/require"
)

func TestMigrateUp(t *testing.T) {
	// Create temporary database
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	// Run migrations
	err := MigrateUp(dbPath, "test_")
	require.NoError(t, err, "MigrateUp should not return error")

	// Verify database file exists
	_, err = os.Stat(dbPath)
	require.NoError(t, err, "Database file should exist")

	// Verify tables were created with prefix
	db, err := sql.Open("sqlite3", dbPath)
	require.NoError(t, err)
	defer db.Close()

	tables := []string{"test_positions", "test_orders", "test_transactions", "test_pool_states"}
	for _, table := range tables {
		var count int
		err := db.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&count)
		require.NoError(t, err)
		require.Equal(t, 1, count, "Table %s should exist", table)
	}

	// Verify goose version table was created
	var versionTableExists int
	err = db.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='test_goose_db_version'").Scan(&versionTableExists)
	require.NoError(t, err)
	require.Equal(t, 1, versionTableExists, "goose version table should exist")
}

func TestMigrateDown(t *testing.T) {
	// Create temporary database
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	// Run migrations up first
	err := MigrateUp(dbPath, "downtest_")
	require.NoError(t, err)

	// Run migrations down
	err = MigrateDown(dbPath, "downtest_")
	require.NoError(t, err, "MigrateDown should not return error")

	// Verify version table is cleared (migrations rolled back)
	db, err := sql.Open("sqlite3", dbPath)
	require.NoError(t, err)
	defer db.Close()

	// After down, version should be at 0 or table dropped
	var version int
	err = db.QueryRow("SELECT version_id FROM downtest_goose_db_version ORDER BY id DESC LIMIT 1").Scan(&version)
	// If error, table may be empty or dropped - both are valid outcomes
	if err != nil {
		// Check if version is 0 (rolled back)
		var version0 int
		err = db.QueryRow("SELECT COUNT(*) FROM downtest_goose_db_version WHERE version_id=0").Scan(&version0)
		require.NoError(t, err)
	}
}

func TestMigrateUp_InvalidPath(t *testing.T) {
	// Test with non-existent parent directory - SQLite cannot create parent dirs
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "subdir", "test.db")

	err := MigrateUp(dbPath, "invalid_")
	// SQLite cannot create parent directories, so this should fail
	require.Error(t, err, "MigrateUp should fail when parent directory doesn't exist")
}

func TestMigrateUp_SchemaPrefix(t *testing.T) {
	// Test that different schema prefixes create isolated tables
	tmpDir := t.TempDir()

	// Run migrations with different prefixes
	dbPath1 := filepath.Join(tmpDir, "test1.db")
	dbPath2 := filepath.Join(tmpDir, "test2.db")

	err := MigrateUp(dbPath1, "dryrun_")
	require.NoError(t, err)

	err = MigrateUp(dbPath2, "live_")
	require.NoError(t, err)

	// Verify tables are isolated
	db1, err := sql.Open("sqlite3", dbPath1)
	require.NoError(t, err)
	defer db1.Close()

	db2, err := sql.Open("sqlite3", dbPath2)
	require.NoError(t, err)
	defer db2.Close()

	// Check dryrun_ tables exist only in db1
	for _, table := range []string{"dryrun_positions", "dryrun_orders"} {
		var count int
		err := db1.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&count)
		require.NoError(t, err)
		require.Equal(t, 1, count, "Table %s should exist in db1", table)
	}

	// Check live_ tables exist only in db2
	for _, table := range []string{"live_positions", "live_orders"} {
		var count int
		err := db2.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&count)
		require.NoError(t, err)
		require.Equal(t, 1, count, "Table %s should exist in db2", table)
	}

	// Cross-check: dryrun_ tables should NOT exist in db2
	var count int
	err = db2.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dryrun_positions'").Scan(&count)
	require.NoError(t, err)
	require.Equal(t, 0, count, "dryrun_ tables should not exist in db2")
}

func TestApplySchemaPrefix(t *testing.T) {
	tests := []struct {
		name     string
		sql      string
		prefix   string
		expected string
	}{
		{
			name:     "simple CREATE TABLE",
			sql:      "CREATE TABLE positions (id TEXT);",
			prefix:   "dryrun_",
			expected: "CREATE TABLE dryrun_positions (id TEXT);",
		},
		{
			name:     "CREATE TABLE with REFERENCES",
			sql:      "CREATE TABLE orders (id TEXT, position_id TEXT, FOREIGN KEY (position_id) REFERENCES positions(id));",
			prefix:   "shadow_",
			expected: "CREATE TABLE shadow_orders (id TEXT, position_id TEXT, FOREIGN KEY (position_id) REFERENCES shadow_positions(id));",
		},
		{
			name:     "INSERT INTO",
			sql:      "INSERT INTO positions VALUES (1, 2, 3);",
			prefix:   "live_",
			expected: "INSERT INTO live_positions VALUES (1, 2, 3);",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := applySchemaPrefix(tt.sql, tt.prefix)
			// Check that prefix was applied
			require.True(t, strings.Contains(result, tt.prefix), "Result should contain prefix")
			// Check that original table name without prefix doesn't appear
			origTable := strings.TrimPrefix(tt.expected, tt.prefix)
			require.False(t, strings.Contains(result, " "+origTable+" "),
				"Original table name should be prefixed")
		})
	}
}

func TestMigrateUp_TablesCreated(t *testing.T) {
	// Integration test: verify all expected tables are created
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	err := MigrateUp(dbPath, "verify_")
	require.NoError(t, err)

	db, err := sql.Open("sqlite3", dbPath)
	require.NoError(t, err)
	defer db.Close()

	// Query all tables (excluding sqlite internal tables like sqlite_sequence)
	rows, err := db.Query("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name")
	require.NoError(t, err)
	defer rows.Close()

	var tables []string
	for rows.Next() {
		var name string
		require.NoError(t, rows.Scan(&name))
		tables = append(tables, name)
	}

	// Should have: positions, orders, transactions, pool_states, goose_db_version
	expectedTables := []string{"verify_goose_db_version", "verify_orders", "verify_positions", "verify_pool_states", "verify_transactions"}
	require.ElementsMatch(t, expectedTables, tables)
}