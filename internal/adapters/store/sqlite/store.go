// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	_ "github.com/mattn/go-sqlite3"

	"github.com/lpbot/lpbot/internal/ports"
)

// Store implements ports.Store using SQLite.
type Store struct {
	db         *sql.DB
	txRepo     *TxRepo
	intentRepo *ExecutionIntentRepo
	posRepo    *PositionRepo
	poolRepo   *PoolRepo
	ledgerRepo *LedgerRepo
	riskRepo   *RiskRepo
	prefix     string
}

// NewStore creates a new SQLite store.
func NewStore(dbPath string) (*Store, error) {
	if dbPath == "" {
		return nil, fmt.Errorf("db path is required")
	}

	// Ensure directory exists
	dir := filepath.Dir(dbPath)
	if dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("failed to create db directory: %w", err)
		}
	}

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open db: %w", err)
	}

	// Configure connection pool
	db.SetMaxOpenConns(1) // SQLite doesn't support concurrent writes
	db.SetMaxIdleConns(1)

	// Derive prefix from db filename (e.g., "shadow" from "shadow.db")
	prefix := derivePrefix(dbPath)

	tablePrefix := prefix + "_"

	store := &Store{
		db:         db,
		prefix:     prefix,
		txRepo:     NewTxRepo(db, tablePrefix),
		intentRepo: NewExecutionIntentRepo(db, tablePrefix),
		posRepo:    NewPositionRepo(db, tablePrefix),
		poolRepo:   NewPoolRepo(db, tablePrefix),
		ledgerRepo: NewLedgerRepo(db, tablePrefix),
		riskRepo:   NewRiskRepo(db, tablePrefix),
	}

	// Run migrations
	if err := store.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("migration failed: %w", err)
	}

	return store, nil
}

// derivePrefix extracts the mode prefix from the db path.
func derivePrefix(dbPath string) string {
	base := filepath.Base(dbPath)
	ext := filepath.Ext(base)
	name := base[:len(base)-len(ext)] // Remove .db
	// Remove _db suffix if present
	if len(name) > 3 && name[len(name)-3:] == "_db" {
		name = name[:len(name)-3]
	}
	return name
}

// migrate runs database migrations.
func (s *Store) migrate() error {
	tablePrefix := s.prefix + "_"

	// Create tables using the correct prefix
	tables := []string{
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %stransactions (
			id TEXT PRIMARY KEY,
			chain TEXT NOT NULL,
			tx_hash TEXT UNIQUE NOT NULL,
			from_address TEXT NOT NULL,
			to_address TEXT NOT NULL,
			data BLOB,
			value TEXT,
			nonce INTEGER,
			deadline INTEGER,
			min_out TEXT,
			signature BLOB,
			status TEXT NOT NULL,
			block_number INTEGER,
			block_hash TEXT,
			broadcast_at INTEGER,
			gas_used INTEGER,
			gas_price TEXT,
			gas_limit INTEGER,
			rfb_attempts INTEGER DEFAULT 0,
			error_msg TEXT,
			trace_id TEXT,
			created_at INTEGER NOT NULL,
			updated_at INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %sexecution_intents (
			id TEXT PRIMARY KEY,
			mode TEXT NOT NULL,
			chain TEXT NOT NULL,
			pool_id TEXT,
			position_id TEXT,
			action TEXT NOT NULL,
			status TEXT NOT NULL,
			idempotency_key TEXT NOT NULL UNIQUE,
			unsigned_tx_hash TEXT,
			signed_tx_hash TEXT,
			tx_hash TEXT,
			reason TEXT,
			risk_snapshot_json TEXT NOT NULL DEFAULT '{}',
			sizing_snapshot_json TEXT NOT NULL DEFAULT '{}',
			decision_trace_id TEXT,
			created_at INTEGER NOT NULL,
			updated_at INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %sportfolio_snapshots (
			id TEXT PRIMARY KEY,
			mode TEXT NOT NULL,
			chain TEXT NOT NULL,
			wallet_address TEXT NOT NULL,
			native_balance_wei TEXT NOT NULL DEFAULT '0',
			gas_reserve_wei TEXT NOT NULL DEFAULT '0',
			open_position_count INTEGER NOT NULL DEFAULT 0,
			open_position_exposure_usd TEXT NOT NULL DEFAULT '0',
			pending_exposure_usd TEXT NOT NULL DEFAULT '0',
			submitted_private_exposure_usd TEXT NOT NULL DEFAULT '0',
			realized_pnl_usd TEXT NOT NULL DEFAULT '0',
			unrealized_pnl_usd TEXT NOT NULL DEFAULT '0',
			balances_json TEXT NOT NULL DEFAULT '{}',
			positions_json TEXT NOT NULL DEFAULT '[]',
			created_at INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %spositions (
			id TEXT PRIMARY KEY,
			token_id TEXT,
			chain TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			protocol TEXT,
			token0 TEXT NOT NULL,
			token1 TEXT NOT NULL,
			tick_lower INTEGER NOT NULL,
			tick_upper INTEGER NOT NULL,
			liquidity TEXT NOT NULL,
			amount0 TEXT NOT NULL,
			amount1 TEXT NOT NULL,
			tvl_usd TEXT,
			amount_usd TEXT,
			tier TEXT,
			open_tx_hash TEXT,
			metadata TEXT NOT NULL DEFAULT '{}',
			fee_growth_0 TEXT,
			fee_growth_1 TEXT,
			collected_fee_0 TEXT,
			collected_fee_1 TEXT,
			status TEXT NOT NULL,
			opened_at INTEGER NOT NULL,
			updated_at INTEGER NOT NULL,
			closed_at INTEGER
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %spools (
			id TEXT PRIMARY KEY,
			chain TEXT NOT NULL,
			protocol TEXT NOT NULL,
			token0 TEXT NOT NULL,
			token1 TEXT NOT NULL,
			fee_bps INTEGER NOT NULL,
			tier TEXT NOT NULL,
			tvl_usd TEXT,
			vol_24h TEXT,
			fee_apr_24h TEXT,
			last_score REAL,
			updated_at INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %srisk_events (
			id TEXT PRIMARY KEY,
			position_id TEXT,
			pool_key TEXT,
			event_type TEXT NOT NULL,
			action TEXT,
			severity TEXT NOT NULL,
			description TEXT NOT NULL,
			data TEXT,
			resolved INTEGER DEFAULT 0,
			resolved_at INTEGER,
			created_at INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %sledger (
			id TEXT PRIMARY KEY,
			position_id TEXT,
			tx_hash TEXT,
			entry_type TEXT NOT NULL,
			amount TEXT NOT NULL,
			currency TEXT NOT NULL,
			description TEXT,
			timestamp INTEGER NOT NULL
		)`, tablePrefix),
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %skill_switch_state (
			id TEXT PRIMARY KEY,
			switch_type TEXT NOT NULL,
			triggered_at INTEGER NOT NULL,
			trigger_reason TEXT,
			auto_resume_at INTEGER,
			resumed_at INTEGER,
			resume_allowed INTEGER DEFAULT 1,
			total_triggers INTEGER DEFAULT 1,
			updated_at INTEGER NOT NULL
		)`, tablePrefix),
	}

	for _, sql := range tables {
		if _, err := s.db.Exec(sql); err != nil {
			return fmt.Errorf("failed to create table: %w", err)
		}
	}

	// Run ALTER TABLE statements for existing databases
	// Use PRAGMA table_info to check if columns exist before adding
	if err := s.runMigrations(); err != nil {
		return err
	}

	return nil
}

// runMigrations adds new columns to existing tables.
func (s *Store) runMigrations() error {
	// Columns to add to positions table
	positionCols := []struct {
		name    string
		colType string
	}{
		{"amount_usd", "TEXT"},
		{"tier", "TEXT"},
		{"protocol", "TEXT"},
		{"open_tx_hash", "TEXT"},
		{"metadata", "TEXT NOT NULL DEFAULT '{}'"},
	}

	// Columns to add to risk_events table
	riskCols := []struct {
		name    string
		colType string
	}{
		{"position_id", "TEXT"},
		{"pool_key", "TEXT"},
		{"action", "TEXT"},
	}

	// Add columns to positions
	for _, col := range positionCols {
		if err := s.addColumnIfNotExists(s.prefix+"_positions", col.name, col.colType); err != nil {
			return fmt.Errorf("failed to add column %s to positions: %w", col.name, err)
		}
	}

	// Add columns to risk_events
	for _, col := range riskCols {
		if err := s.addColumnIfNotExists(s.prefix+"_risk_events", col.name, col.colType); err != nil {
			return fmt.Errorf("failed to add column %s to risk_events: %w", col.name, err)
		}
	}

	return nil
}

// addColumnIfNotExists adds a column to a table if it doesn't already exist.
func (s *Store) addColumnIfNotExists(tableName, columnName, columnType string) error {
	// Check if column exists using PRAGMA table_info
	rows, err := s.db.Query(fmt.Sprintf("PRAGMA table_info(%s)", tableName))
	if err != nil {
		return err
	}
	defer rows.Close()

	for rows.Next() {
		var cid int
		var name, colType string
		var notnull, pk int
		var dflt_value interface{}
		if err := rows.Scan(&cid, &name, &colType, &notnull, &dflt_value, &pk); err != nil {
			continue
		}
		if name == columnName {
			// Column already exists
			return nil
		}
	}

	// Column doesn't exist, add it
	_, err = s.db.Exec(fmt.Sprintf("ALTER TABLE %s ADD COLUMN %s %s", tableName, columnName, columnType))
	return err
}

// Compile-time interface assertion
var _ ports.Store = (*Store)(nil)

// TxRepo returns the transaction repository.
func (s *Store) TxRepo() ports.TxRepo { return s.txRepo }

// ExecutionIntentRepo returns the execution intent repository.
func (s *Store) ExecutionIntentRepo() ports.ExecutionIntentRepo { return s.intentRepo }

// PositionRepo returns the position repository.
func (s *Store) PositionRepo() ports.PositionRepo { return s.posRepo }

// PoolRepo returns the pool repository.
func (s *Store) PoolRepo() ports.PoolRepo { return s.poolRepo }

// LedgerRepo returns the ledger repository.
func (s *Store) LedgerRepo() ports.LedgerRepo { return s.ledgerRepo }

// RiskRepo returns the risk repository.
func (s *Store) RiskRepo() ports.RiskRepo { return s.riskRepo }

// ConfigSnap returns nil (not implemented in SQLite adapter).
func (s *Store) ConfigSnap() ports.ConfigSnap { return nil }

// Close closes the database connection.
func (s *Store) Close() error {
	return s.db.Close()
}

// DB returns the underlying database handle for tests and targeted maintenance queries.
func (s *Store) DB() *sql.DB {
	return s.db
}

// Prefix returns the table prefix used by this store.
func (s *Store) Prefix() string {
	return s.prefix
}
