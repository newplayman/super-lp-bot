// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// LedgerRepo implements ports.LedgerRepo using SQLite.
type LedgerRepo struct {
	db     *sql.DB
	prefix string
}

// NewLedgerRepo creates a new LedgerRepo backed by the given database.
func NewLedgerRepo(db *sql.DB, prefix string) *LedgerRepo {
	return &LedgerRepo{db: db, prefix: prefix}
}

// Compile-time interface assertion
var _ ports.LedgerRepo = (*LedgerRepo)(nil)

// Append adds a new ledger entry to the append-only ledger.
func (r *LedgerRepo) Append(ctx context.Context, entry ports.LedgerEntry) (ports.LedgerEntry, error) {
	table := r.prefix + "ledger"
	query := fmt.Sprintf(`
		INSERT INTO %s (id, position_id, entry_type, amount, currency, description, timestamp, tx_hash)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`, table)

	now := time.Now().UnixMilli()

	// Use provided ID or generate unique one
	id := entry.ID
	if id == "" {
		id = fmt.Sprintf("ledger_%d_%s", now, entry.PositionID)
	}

	_, err := r.db.ExecContext(ctx, query,
		id,
		entry.PositionID,
		string(entry.Kind),
		entry.Amount.String(),
		entry.TokenSymbol,
		"", // description not in new schema
		now,
		entry.TxHash,
	)
	if err != nil {
		return entry, fmt.Errorf("failed to append ledger entry: %w", err)
	}

	entry.ID = id
	return entry, nil
}

// ByPosition returns all ledger entries for a position.
func (r *LedgerRepo) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	table := r.prefix + "ledger"
	query := fmt.Sprintf(`
		SELECT id, position_id, entry_type, amount, currency, timestamp, tx_hash
		FROM %s WHERE position_id = ?
		ORDER BY timestamp ASC
	`, table)

	rows, err := r.db.QueryContext(ctx, query, positionID)
	if err != nil {
		return nil, fmt.Errorf("failed to list ledger entries: %w", err)
	}
	defer rows.Close()

	var entries []ports.LedgerEntry
	for rows.Next() {
		var e ports.LedgerEntry
		var timestamp int64

		err := rows.Scan(&e.ID, &e.PositionID, &e.Kind, &e.Amount, &e.TokenSymbol, &timestamp, &e.TxHash)
		if err != nil {
			continue
		}
		entries = append(entries, e)
	}

	return entries, rows.Err()
}

// ByPositionAndKind returns ledger entries filtered by position and kind.
func (r *LedgerRepo) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	table := r.prefix + "ledger"
	query := fmt.Sprintf(`
		SELECT id, position_id, entry_type, amount, currency, timestamp, tx_hash
		FROM %s WHERE position_id = ? AND entry_type = ?
		ORDER BY timestamp ASC
	`, table)

	rows, err := r.db.QueryContext(ctx, query, positionID, string(kind))
	if err != nil {
		return nil, fmt.Errorf("failed to list ledger entries by kind: %w", err)
	}
	defer rows.Close()

	var entries []ports.LedgerEntry
	for rows.Next() {
		var e ports.LedgerEntry
		var timestamp int64

		err := rows.Scan(&e.ID, &e.PositionID, &e.Kind, &e.Amount, &e.TokenSymbol, &timestamp, &e.TxHash)
		if err != nil {
			continue
		}
		entries = append(entries, e)
	}

	return entries, rows.Err()
}

// AggregateByKind computes the total net PnL for a position by entry kind.
func (r *LedgerRepo) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	table := r.prefix + "ledger"
	query := fmt.Sprintf(`
		SELECT entry_type, SUM(amount) as total
		FROM %s WHERE position_id = ?
		GROUP BY entry_type
	`, table)

	rows, err := r.db.QueryContext(ctx, query, positionID)
	if err != nil {
		return nil, fmt.Errorf("failed to aggregate ledger entries: %w", err)
	}
	defer rows.Close()

	result := make(map[ports.LedgerEntryKind]domain.Decimal)
	// Initialize all kinds with zero
	for _, k := range []ports.LedgerEntryKind{
		ports.LedgerEntryFee,
		ports.LedgerEntryIL,
		ports.LedgerEntrySwap,
		ports.LedgerEntryGas,
		ports.LedgerEntrySlippage,
		ports.LedgerEntryRug,
	} {
		result[k] = domain.Zero
	}

	for rows.Next() {
		var kind string
		var totalStr string
		if err := rows.Scan(&kind, &totalStr); err != nil {
			continue
		}
		d, err := decimal.NewFromString(totalStr)
		if err != nil {
			continue
		}
		result[ports.LedgerEntryKind(kind)] = d
	}

	return result, rows.Err()
}

// LatestBlock returns the highest block number with any ledger entry.
func (r *LedgerRepo) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	table := r.prefix + "ledger"
	query := fmt.Sprintf(`SELECT MAX(timestamp) FROM %s`, table)

	var maxTimestamp sql.NullInt64
	err := r.db.QueryRowContext(ctx, query).Scan(&maxTimestamp)
	if err != nil {
		return nil, fmt.Errorf("failed to get latest block: %w", err)
	}

	if !maxTimestamp.Valid {
		return nil, nil
	}

	return &domain.BlockRef{Number: uint64(maxTimestamp.Int64)}, nil
}