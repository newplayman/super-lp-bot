// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"database/sql"
	"fmt"
	"os"

	_ "github.com/mattn/go-sqlite3"

	"github.com/lpbot/lpbot/internal/ports"
)

// Store implements ports.Store using SQLite.
type Store struct {
	db     *sql.DB
	txRepo *TxRepo
	posRepo *PositionRepo
	poolRepo *PoolRepo
	ledgerRepo *LedgerRepo
	riskRepo *RiskRepo
}

// NewStore creates a new SQLite store.
func NewStore(dbPath string) (*Store, error) {
	if dbPath == "" {
		return nil, fmt.Errorf("db path is required")
	}

	// Ensure directory exists
	dir := dbPath[:len(dbPath)-len("/data.db")]
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

	store := &Store{
		db:          db,
		txRepo:      NewTxRepo(db, "shadow_"),
		posRepo:     NewPositionRepo(db),
		poolRepo:    NewPoolRepo(db),
		ledgerRepo:  NewLedgerRepo(db),
		riskRepo:    NewRiskRepo(),
	}

	// Run migrations
	if err := store.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("migration failed: %w", err)
	}

	return store, nil
}

// migrate runs database migrations.
func (s *Store) migrate() error {
	// Create tables if they don't exist
	tables := []string{
		`CREATE TABLE IF NOT EXISTS shadow_transactions (
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
		)`,
		`CREATE TABLE IF NOT EXISTS shadow_positions (
			id TEXT PRIMARY KEY,
			chain TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			token0 TEXT NOT NULL,
			token1 TEXT NOT NULL,
			tick_lower INTEGER NOT NULL,
			tick_upper INTEGER NOT NULL,
			liquidity TEXT NOT NULL,
			amount0 TEXT NOT NULL,
			amount1 TEXT NOT NULL,
			tvl_usd TEXT,
			fee_growth_0 TEXT,
			fee_growth_1 TEXT,
			collected_fee_0 TEXT,
			collected_fee_1 TEXT,
			status TEXT NOT NULL,
			opened_at INTEGER NOT NULL,
			updated_at INTEGER NOT NULL,
			closed_at INTEGER
		)`,
		`CREATE TABLE IF NOT EXISTS shadow_pools (
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
		)`,
		`CREATE TABLE IF NOT EXISTS shadow_risk_events (
			id TEXT PRIMARY KEY,
			event_type TEXT NOT NULL,
			severity TEXT NOT NULL,
			description TEXT NOT NULL,
			data TEXT,
			resolved INTEGER DEFAULT 0,
			resolved_at INTEGER,
			created_at INTEGER NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS shadow_kill_switch_state (
			id TEXT PRIMARY KEY,
			switch_type TEXT NOT NULL,
			triggered_at INTEGER NOT NULL,
			trigger_reason TEXT,
			auto_resume_at INTEGER,
			resumed_at INTEGER,
			resume_allowed INTEGER DEFAULT 1,
			total_triggers INTEGER DEFAULT 1,
			updated_at INTEGER NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS shadow_ledger (
			id TEXT PRIMARY KEY,
			position_id TEXT,
			tx_hash TEXT,
			entry_type TEXT NOT NULL,
			amount TEXT NOT NULL,
			currency TEXT NOT NULL,
			description TEXT,
			timestamp INTEGER NOT NULL
		)`,
	}

	for _, sql := range tables {
		if _, err := s.db.Exec(sql); err != nil {
			return fmt.Errorf("failed to create table: %w", err)
		}
	}

	return nil
}

// Compile-time interface assertion
var _ ports.Store = (*Store)(nil)

// TxRepo returns the transaction repository.
func (s *Store) TxRepo() ports.TxRepo { return s.txRepo }

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