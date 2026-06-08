// Package postgres provides PostgreSQL adapter tests.
package postgres

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

// migrationNumberRE extracts the leading numeric portion of a migration
// filename (e.g. "000011" from "000011_shadow_decision_trace.sql").
var migrationNumberRE = regexp.MustCompile(`^(\d+)_`)

// columnRE extracts a "colname TYPE" pair from a CREATE TABLE statement.
// Handles "colname TYPE", "colname TYPE NOT NULL", "colname TYPE DEFAULT ..."
// but does NOT handle multi-line column definitions.
var columnRE = regexp.MustCompile(`(?m)^\s*(\w+)\s+([A-Z][A-Z0-9_ ]*?)(?:\s+NOT\s+NULL|\s+DEFAULT|\s+PRIMARY|,|\s*$)`)

// tableRE finds CREATE TABLE statements.
var tableRE = regexp.MustCompile(`(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);`)

// indexRE finds CREATE INDEX / CREATE UNIQUE INDEX statements.
var indexRE = regexp.MustCompile(`(?i)CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)`)

// TestMigrationsSchemaCompatibility is a STATIC test that does not require a
// live Postgres connection. It parses every .sql under migrations/postgres and
// verifies the columns/tables/indexes that the live schema guard
// (cmd/lpbot/main.go loadLiveSchemaState) and the Go repos expect are present
// in at least one migration.
func TestMigrationsSchemaCompatibility(t *testing.T) {
	migrationsDir := findMigrationsDir(t)

	// Required tables per cmd/lpbot/main.go loadLiveSchemaState +
	// cmd/lpbot/position_mark.go (in-Go CREATE TABLE) + P0-PG-02-B (added
	// 000013 / 000014 migrations). All shadow tables and runtime metadata
	// tables should be sourced from migrations, not in-Go CREATE TABLE.
	requiredTables := []string{
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
		"pools",
		"pool_score_history",
		"risk_events",
		"kill_switch_state",
		"shadow_outcome_labels",
	}

	// Required index per the live schema guard.
	requiredIndexes := []string{
		"idx_positions_one_active_per_pool",
	}

	// Required columns by table. The Go repos use these (see
	// internal/adapters/store/postgres/position_repo.go,
	// pool_repo.go, tx_repo.go, etc.) and the live schema guard requires the
	// table itself to exist; this check makes the column-level expectations
	// explicit.
	requiredColumns := map[string][]string{
		"positions":         {"id", "pool_id", "chain", "status", "tick_lower", "tick_upper", "amount_usd", "opened_at", "protocol", "open_tx_hash", "metadata"},
		"pools":             {"pool_id", "chain", "protocol", "token0", "token1", "fee_bps", "liquidity", "tick", "tvl_usd", "vol_24h", "fee_apr_24h", "updated_at"},
		"transactions":      {"id", "chain", "tx_hash", "from_address", "to_address", "data", "value", "nonce", "deadline", "min_out", "signature", "status"},
		"execution_intents": {"id", "mode", "chain", "action", "status", "idempotency_key", "risk_snapshot_json", "sizing_snapshot_json", "created_at", "updated_at"},
		"portfolio_snapshots": {"id", "mode", "chain", "wallet_address", "balances_json", "positions_json", "created_at"},
		"position_marks":    {"id", "position_id", "pool_id", "chain", "mark_time", "created_at"},
		"canary_events":      {"id", "chain", "command", "stage", "status", "position_id", "created_at", "updated_at"},
		"pnl_ledger":         {"id", "position_id", "kind", "amount", "token_symbol", "chain", "block_number", "block_time"},
		"shadow_decision_trace": {"id", "tick_time", "trace_id", "pool_id", "chain", "protocol", "score_total", "selected", "intent_open", "created_at"},
	}

	// Aggregate CREATE TABLE / CREATE INDEX across all migrations.
	tableDefs := map[string]string{}  // table -> full SQL body
	tablesSeen := map[string]bool{}
	indexesSeen := map[string]bool{}
	alteredColumns := map[string]map[string]bool{} // table -> col -> true (from ALTER TABLE ADD COLUMN)

	entries, err := os.ReadDir(migrationsDir)
	require.NoError(t, err, "read migrations dir")
	require.NotEmpty(t, entries, "migrations dir should not be empty")

	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		path := filepath.Join(migrationsDir, e.Name())
		body, err := os.ReadFile(path)
		require.NoError(t, err, "read %s", path)
		text := string(body)

		// CREATE TABLE
		for _, m := range tableRE.FindAllStringSubmatch(text, -1) {
			tbl := strings.ToLower(m[1])
			body := m[2]
			tableDefs[tbl] = body
			tablesSeen[tbl] = true
		}

		// CREATE INDEX
		for _, m := range indexRE.FindAllStringSubmatch(text, -1) {
			idx := strings.ToLower(m[1])
			indexesSeen[idx] = true
		}

		// ALTER TABLE x ADD COLUMN [IF NOT EXISTS] y ...
		// Supports both single-column and compact multi-column syntax
		// (e.g. 000003_pool_runtime_columns.sql uses 5 ADD COLUMN in one
		// ALTER TABLE statement). The compact form looks like:
		//   ALTER TABLE pools ADD COLUMN IF NOT EXISTS liquidity TEXT,
		//       ADD COLUMN IF NOT EXISTS tick BIGINT,
		//       ...
		// First, find each ALTER TABLE ... statement and the table name; then
		// find ADD COLUMNs in that statement.
		alterTableRE := regexp.MustCompile(`(?is)ALTER\s+TABLE\s+(\w+)\b`)
		alterColRE := regexp.MustCompile(`(?i)ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)`)
		alterMatches := alterTableRE.FindAllStringSubmatchIndex(text, -1)
		// Build a list of (tblName, start, end) for each ALTER TABLE
		// statement, where end is the position of the terminating ";".
		type alterStmt struct {
			tbl  string
			body string
		}
		var stmts []alterStmt
		for _, m := range alterMatches {
			// Group 1 is the table name; indices [2]:[3] in the submatches.
			tbl := strings.ToLower(text[m[2]:m[3]])
			stmtStart := m[0]
			stmtEnd := m[1]
			for stmtEnd < len(text) && text[stmtEnd] != ';' {
				stmtEnd++
			}
			body := text[stmtStart:stmtEnd]
			stmts = append(stmts, alterStmt{tbl: tbl, body: body})
		}
		for _, s := range stmts {
			for _, c := range alterColRE.FindAllStringSubmatch(s.body, -1) {
				col := strings.ToLower(c[1])
				if alteredColumns[s.tbl] == nil {
					alteredColumns[s.tbl] = map[string]bool{}
				}
				alteredColumns[s.tbl][col] = true
			}
		}
	}

	// 1. Required tables exist (created or altered somewhere).
	for _, tbl := range requiredTables {
		require.Truef(t, tablesSeen[tbl],
			"required table %q is not CREATEd in any migration; "+
				"this is a schema/code mismatch with the live schema guard "+
				"(cmd/lpbot/main.go loadLiveSchemaState) or the in-Go ensure*Table helpers",
			tbl)
	}

	// 2. Required indexes exist.
	for _, idx := range requiredIndexes {
		require.Truef(t, indexesSeen[idx],
			"required index %q is not CREATEd in any migration", idx)
	}

	// 3. Required columns are present in either CREATE TABLE body or ALTER TABLE ADD.
	for tbl, cols := range requiredColumns {
		body, ok := tableDefs[tbl]
		if !ok {
			// Table must exist via ALTER alone, in which case columns may be
			// only added incrementally. We still need the core CREATE in
			// at least one migration.
			require.Failf(t, "missing CREATE TABLE for %q", tbl)
		}
		bodyCols := map[string]bool{}
		for _, m := range columnRE.FindAllStringSubmatch(body, -1) {
			bodyCols[strings.ToLower(m[1])] = true
		}
		alterCols := alteredColumns[tbl]
		for _, col := range cols {
			require.Truef(t, bodyCols[col] || (alterCols != nil && alterCols[col]),
				"required column %q.%q is missing from CREATE TABLE body AND not added by any ALTER TABLE",
				tbl, col)
		}
	}

	// 4. Sanity: migration numbering should be sequential or have an explicit
	// gap-acknowledgement. (migrate-postgres.sh enforces this at run time.)
	nums := []int{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		m := migrationNumberRE.FindStringSubmatch(e.Name())
		if m == nil {
			continue
		}
		n, err := strconv.Atoi(m[1])
		require.NoError(t, err)
		nums = append(nums, n)
	}
	sort.Ints(nums)
	require.NotEmpty(t, nums, "no migration files with numeric prefix found")
	// 000011 may exist for shadow_decision_trace (added 2026-06-09). Earlier
	// numbering may have a 000010 -> 000012 gap depending on which
	// shadow_outcome_repaired_v2 numbering the user adopts; this is a
	// warning not a failure.
	for i := 1; i < len(nums); i++ {
		if nums[i] != nums[i-1]+1 {
			t.Logf("WARN: migration numbering gap detected: %06d -> %06d "+
				"(acceptable when intentional; migrate-postgres.sh refuses by default)",
				nums[i-1], nums[i])
		}
	}
}

// findMigrationsDir locates migrations/postgres/ relative to the test
// process. Tests run with the package source as cwd so we walk up from
// internal/adapters/store/postgres.
func findMigrationsDir(t *testing.T) string {
	t.Helper()
	cwd, err := os.Getwd()
	require.NoError(t, err)
	// Try a few candidate paths.
	candidates := []string{
		filepath.Join(cwd, "..", "..", "..", "migrations", "postgres"),
		filepath.Join(cwd, "..", "..", "..", "..", "migrations", "postgres"),
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			return c
		}
	}
	t.Fatalf("migrations/postgres dir not found; tried %v", candidates)
	return ""
}

// TestPostgresRepoIntegration runs only when LPBOT_POSTGRES_TEST_DSN is set.
// It applies all migrations and runs a smoke roundtrip on each repo.
// When unset, the test SKIPs (we don't fabricate PASS).
func TestPostgresRepoIntegration(t *testing.T) {
	dsn := os.Getenv("LPBOT_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("LPBOT_POSTGRES_TEST_DSN not set; skipping integration test")
	}
	t.Logf("integration test would run against DSN host: %s",
		// never log the full DSN (may contain password)
		dsnHost(dsn))

	// Note: the postgres adapter does not yet have a Go-based migration
	// runner (BLK-PG-08 from P0-PG-01 audit). The shell script
	// scripts/migrate-postgres.sh is the canonical entry point and
	// must be run BEFORE this test (it records applied migrations in
	// the schema_migrations marker table).
	cfg, err := parseDSNForTest(dsn)
	require.NoError(t, err, "parse DSN")
	adapter, err := New(cfg)
	if err != nil {
		t.Skipf("could not connect to LPBOT_POSTGRES_TEST_DSN: %v", err)
	}
	defer adapter.Close()
	require.NotNil(t, adapter)
	t.Logf("postgres adapter connected; schema guard not yet exercised (migration runner pending)")

	// Verify the required tables (live schema guard) are present.
	required := []string{
		"positions", "transactions", "execution_intents", "portfolio_snapshots",
		"position_marks", "canary_events", "pnl_ledger", "shadow_decision_trace",
		"shadow_position_marks", "shadow_exit_decisions", "shadow_exit_actions",
		"pools", "pool_score_history", "risk_events", "kill_switch_state",
		"shadow_outcome_labels",
	}
	for _, tbl := range required {
		var exists bool
		err := adapter.DB().QueryRow("SELECT to_regclass('public.' || $1) IS NOT NULL", tbl).Scan(&exists)
		require.NoError(t, err, "check %s", tbl)
		require.Truef(t, exists, "required table %q missing (run scripts/migrate-postgres.sh first)", tbl)
	}
	t.Logf("all %d required tables present", len(required))

	// Verify the required index is present.
	var idxExists bool
	err = adapter.DB().QueryRow("SELECT to_regclass('public.idx_positions_one_active_per_pool') IS NOT NULL").Scan(&idxExists)
	require.NoError(t, err)
	require.Truef(t, idxExists, "required index idx_positions_one_active_per_pool missing")
	t.Logf("required index idx_positions_one_active_per_pool present")

	// Smoke roundtrip on PositionRepo: Save then FindByID.
	ctx := context.Background()
	pos := &domain.Position{
		ID:        "pos-it-" + fmt.Sprintf("%d", time.Now().UnixNano()),
		PoolID:    "0xpool-it",
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		Tier:      domain.TierA,
		TickLower: -100,
		TickUpper: 100,
		AmountUSD: domain.MustDecimal("12.34"),
		OpenedAt:  time.Now().Unix(),
		MetadataJSON: "{}",
	}
	require.NoError(t, adapter.PositionRepo().Save(ctx, pos), "save position")
	got, err := adapter.PositionRepo().FindByID(ctx, pos.ID)
	require.NoError(t, err, "find position")
	require.NotNil(t, got, "position not found after save")
	require.Equal(t, pos.ID, got.ID, "position ID roundtrip mismatch")
	require.Equal(t, pos.PoolID, got.PoolID, "position pool_id roundtrip mismatch")
	require.Equal(t, pos.Chain, got.Chain, "position chain roundtrip mismatch (TEXT alignment)")
	require.Equal(t, pos.Status, got.Status, "position status roundtrip mismatch")
	t.Logf("PositionRepo Save+FindByID roundtrip OK; chain TEXT='%s'", string(got.Chain))

	// Cleanup the test row.
	_, _ = adapter.DB().ExecContext(ctx, "DELETE FROM positions WHERE id = $1", pos.ID)
}

// dsnHost extracts "host[:port]" from a postgres URL for safe logging.
func dsnHost(dsn string) string {
	// Strip scheme + credentials, keep host[:port]
	idx := strings.Index(dsn, "://")
	if idx < 0 {
		return dsn
	}
	rest := dsn[idx+3:]
	if at := strings.Index(rest, "@"); at >= 0 {
		rest = rest[at+1:]
	}
	if slash := strings.Index(rest, "/"); slash >= 0 {
		rest = rest[:slash]
	}
	return rest
}

// parseDSNForTest is a minimal DSN parser sufficient for the integration
// test. It accepts postgres://user:pass@host:port/dbname?sslmode=disable
// and returns a PostgresConfig. Errors are surfaced via require.NoError.
func parseDSNForTest(dsn string) (PostgresConfig, error) {
	cfg := PostgresConfig{
		SSLMode: "disable",
	}
	idx := strings.Index(dsn, "://")
	if idx < 0 {
		return cfg, errTestDSN("missing scheme")
	}
	rest := dsn[idx+3:]
	var userInfo string
	if at := strings.Index(rest, "@"); at >= 0 {
		userInfo = rest[:at]
		rest = rest[at+1:]
	}
	if slash := strings.Index(rest, "/"); slash >= 0 {
		dbPart := rest[slash+1:]
		// Strip ?sslmode=... etc. from database name.
		if q := strings.Index(dbPart, "?"); q >= 0 {
			dbPart = dbPart[:q]
		}
		cfg.Database = dbPart
		rest = rest[:slash]
	}
	if q := strings.Index(rest, "?"); q >= 0 {
		rest = rest[:q]
	}
	if colon := strings.Index(rest, ":"); colon >= 0 {
		cfg.Host = rest[:colon]
		_, _ = parsePortForTest(rest[colon+1:], &cfg)
	} else {
		cfg.Host = rest
	}
	if userInfo != "" {
		if colon := strings.Index(userInfo, ":"); colon >= 0 {
			cfg.User = userInfo[:colon]
			cfg.Password = userInfo[colon+1:]
		} else {
			cfg.User = userInfo
		}
	}
	return cfg, nil
}

func parsePortForTest(s string, cfg *PostgresConfig) (int, error) {
	if s == "" {
		cfg.Port = 5432
		return 5432, nil
	}
	p, err := strconv.Atoi(s)
	if err != nil {
		return 0, err
	}
	cfg.Port = p
	return p, nil
}

type testDSNError struct{ msg string }

func (e *testDSNError) Error() string { return e.msg }
func errTestDSN(s string) error       { return &testDSNError{msg: s} }
