// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
// Phase 3 - Tiny Live: Migrated from SQLite to Postgres with connection pooling and transaction support.
package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"

	_ "github.com/lib/pq"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// PostgresConfig holds the connection configuration for PostgreSQL.
type PostgresConfig struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
	SSLMode  string
}

// DSN returns the PostgreSQL connection string.
func (c PostgresConfig) DSN() string {
	sslMode := "disable"
	if c.SSLMode != "" {
		sslMode = c.SSLMode
	}
	return fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		c.Host, c.Port, c.User, c.Password, c.Database, sslMode,
	)
}

// postgresAdapter is the main entry point for PostgreSQL storage.
// It holds the database connection pool and provides access to individual repositories.
type postgresAdapter struct {
	db  *sql.DB
	cfg PostgresConfig
}

// New creates a new postgresAdapter with the given configuration.
// It establishes a connection pool with sensible defaults for a production environment.
func New(cfg PostgresConfig) (*postgresAdapter, error) {
	db, err := sql.Open("postgres", cfg.DSN())
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Configure connection pool for production workloads
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetConnMaxIdleTime(1 * time.Minute)

	// Verify connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return &postgresAdapter{db: db, cfg: cfg}, nil
}

// NewFromDSN creates a new postgresAdapter by parsing a DSN-style URL.
func NewFromDSN(dsn string) (*postgresAdapter, error) {
	u, err := url.Parse(dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to parse postgres dsn: %w", err)
	}
	if u.Scheme != "postgres" && u.Scheme != "postgresql" {
		return nil, fmt.Errorf("unsupported postgres dsn scheme: %q", u.Scheme)
	}

	host := u.Hostname()
	if host == "" {
		host = "localhost"
	}
	port := 5432
	if p := u.Port(); p != "" {
		v, err := strconv.Atoi(p)
		if err != nil {
			return nil, fmt.Errorf("invalid postgres port %q: %w", p, err)
		}
		port = v
	}

	user := u.User.Username()
	password, _ := u.User.Password()
	dbName := strings.TrimPrefix(u.Path, "/")
	sslMode := "disable"
	if m := u.Query().Get("sslmode"); m != "" {
		sslMode = m
	}

	cfg := PostgresConfig{
		Host:     host,
		Port:     port,
		User:     user,
		Password: password,
		Database: dbName,
		SSLMode:  sslMode,
	}

	return New(cfg)
}

// Close closes the database connection pool.
func (a *postgresAdapter) Close() error {
	return a.db.Close()
}

// DB returns the underlying database connection for advanced operations.
func (a *postgresAdapter) DB() *sql.DB {
	return a.db
}

// LedgerRepo returns a new ledger repository.
func (a *postgresAdapter) LedgerRepo() ports.LedgerRepo {
	return NewLedgerRepo(a.db)
}

// PositionRepo returns a new position repository.
func (a *postgresAdapter) PositionRepo() ports.PositionRepo {
	return NewPositionRepo(a.db)
}

// PoolRepo returns a new pool repository.
func (a *postgresAdapter) PoolRepo() ports.PoolRepo {
	return NewPoolRepo(a.db)
}

// RiskRepo returns a new risk repository.
func (a *postgresAdapter) RiskRepo() ports.RiskRepo {
	return NewRiskRepo(a.db)
}

// TxRepo returns a new transaction repository.
func (a *postgresAdapter) TxRepo() ports.TxRepo {
	return NewTxRepo(a.db)
}

// ExecutionIntentRepo returns a new execution intent repository.
func (a *postgresAdapter) ExecutionIntentRepo() ports.ExecutionIntentRepo {
	return NewExecutionIntentRepo(a.db)
}

// ConfigSnap returns the config snapshot repository.
func (a *postgresAdapter) ConfigSnap() ports.ConfigSnap {
	return nil
}

// Compile-time interface assertion
var _ interface {
	ports.LedgerRepo
	ports.PositionRepo
	ports.PoolRepo
	ports.RiskRepo
	ports.TxRepo
} = (*postgresAdapter)(nil)

var _ ports.Store = (*postgresAdapter)(nil)

// LedgerRepo implements ports.LedgerRepo.
func (a *postgresAdapter) Append(ctx context.Context, entry ports.LedgerEntry) (ports.LedgerEntry, error) {
	return NewLedgerRepo(a.db).Append(ctx, entry)
}

// ByPosition implements ports.LedgerRepo.
func (a *postgresAdapter) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	return NewLedgerRepo(a.db).ByPosition(ctx, positionID)
}

// ByPositionAndKind implements ports.LedgerRepo.
func (a *postgresAdapter) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	return NewLedgerRepo(a.db).ByPositionAndKind(ctx, positionID, kind)
}

// AggregateByKind implements ports.LedgerRepo.
func (a *postgresAdapter) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	return NewLedgerRepo(a.db).AggregateByKind(ctx, positionID)
}

// LatestBlock implements ports.LedgerRepo.
func (a *postgresAdapter) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	return NewLedgerRepo(a.db).LatestBlock(ctx)
}

// Save implements ports.PositionRepo.
func (a *postgresAdapter) Save(ctx context.Context, pos *domain.Position) error {
	return NewPositionRepo(a.db).Save(ctx, pos)
}

// FindByID implements ports.PositionRepo.
func (a *postgresAdapter) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	return NewPositionRepo(a.db).FindByID(ctx, id)
}

// FindByPoolAndStatus implements ports.PositionRepo.
func (a *postgresAdapter) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	return NewPositionRepo(a.db).FindByPoolAndStatus(ctx, poolID, status)
}

// FindByChainAndStatus implements ports.PositionRepo.
func (a *postgresAdapter) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	return NewPositionRepo(a.db).FindByChainAndStatus(ctx, chain, status)
}

// UpdateStatus implements ports.PositionRepo.
func (a *postgresAdapter) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	return NewPositionRepo(a.db).UpdateStatus(ctx, id, status)
}

// Snapshot implements ports.PositionRepo.
// Returns the current positions for a pool without caching.
// Any error causes fail-closed behavior in the caller.
func (a *postgresAdapter) Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error) {
	return NewPositionRepo(a.db).FindByPoolAndStatus(ctx, poolID, domain.StatusOpen)
}

// UpsertPool implements ports.PoolRepo.
func (a *postgresAdapter) UpsertPool(ctx context.Context, pool ports.PoolWithScore) error {
	return NewPoolRepo(a.db).UpsertPool(ctx, pool)
}

// GetPool implements ports.PoolRepo.
func (a *postgresAdapter) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	return NewPoolRepo(a.db).GetPool(ctx, key)
}

// ListPools implements ports.PoolRepo.
func (a *postgresAdapter) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	return NewPoolRepo(a.db).ListPools(ctx, filter)
}

// GetScoreHistory implements ports.PoolRepo.
func (a *postgresAdapter) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
	return NewPoolRepo(a.db).GetScoreHistory(ctx, poolKey, limit)
}

// UpsertAuditVerdict implements ports.PoolRepo.
func (a *postgresAdapter) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
	return NewPoolRepo(a.db).UpsertAuditVerdict(ctx, poolKey, verdict, riskScore)
}

// AppendRiskEvent implements ports.RiskRepo.
func (a *postgresAdapter) AppendRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	return NewRiskRepo(a.db).AppendRiskEvent(ctx, event)
}

// ListRiskEvents implements ports.RiskRepo.
func (a *postgresAdapter) ListRiskEvents(ctx context.Context, filter ports.RiskEventFilter) ([]ports.RiskEvent, error) {
	return NewRiskRepo(a.db).ListRiskEvents(ctx, filter)
}

// GetKillState implements ports.RiskRepo.
func (a *postgresAdapter) GetKillState(ctx context.Context) (ports.KillState, error) {
	return NewRiskRepo(a.db).GetKillState(ctx)
}

// UpsertKillState implements ports.RiskRepo.
func (a *postgresAdapter) UpsertKillState(ctx context.Context, state ports.KillState) error {
	return NewRiskRepo(a.db).UpsertKillState(ctx, state)
}

// UpsertTx implements ports.TxRepo.
func (a *postgresAdapter) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	return NewTxRepo(a.db).UpsertTx(ctx, tx)
}

// GetTxByHash implements ports.TxRepo.
func (a *postgresAdapter) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	return NewTxRepo(a.db).GetTxByHash(ctx, chain, hash)
}

// ListTxsByStatus implements ports.TxRepo.
func (a *postgresAdapter) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	return NewTxRepo(a.db).ListTxsByStatus(ctx, chain, status)
}

// UpdateTxStatus implements ports.TxRepo.
func (a *postgresAdapter) UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error {
	return NewTxRepo(a.db).UpdateTxStatus(ctx, chain, hash, newStatus, ref)
}

// ListPendingTxs implements ports.TxRepo.
func (a *postgresAdapter) ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error) {
	return NewTxRepo(a.db).ListPendingTxs(ctx, chain)
}

// ListStuckTxs implements ports.TxRepo.
func (a *postgresAdapter) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	return NewTxRepo(a.db).ListStuckTxs(ctx, chain, stuckTimeoutSeconds)
}

// IncrementRFBAttempts implements ports.TxRepo.
func (a *postgresAdapter) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	return NewTxRepo(a.db).IncrementRFBAttempts(ctx, chain, hash)
}

// GetRFBAttempts implements ports.TxRepo.
func (a *postgresAdapter) GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error) {
	return NewTxRepo(a.db).GetRFBAttempts(ctx, chain, hash)
}

// chainIDToInt converts a ChainID to its integer representation.
func chainIDToInt(chain domain.ChainID) int {
	switch chain {
	case domain.ChainBase:
		return 1
	case domain.ChainSolana:
		return 2
	default:
		return 0
	}
}

// intToChainID converts an integer to a ChainID.
func intToChainID(n int) domain.ChainID {
	switch n {
	case 1:
		return domain.ChainBase
	case 2:
		return domain.ChainSolana
	default:
		return domain.ChainID("")
	}
}
