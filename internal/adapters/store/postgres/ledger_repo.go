// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
// Phase 3 - Tiny Live: Migrated from SQLite to Postgres with connection pooling and transaction support.
package postgres

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// LedgerRepo implements ports.LedgerRepo using PostgreSQL.
type LedgerRepo struct {
	db *sql.DB
}

// NewLedgerRepo creates a new LedgerRepo backed by the given database.
func NewLedgerRepo(db *sql.DB) *LedgerRepo {
	return &LedgerRepo{db: db}
}

// Compile-time interface assertion
var _ ports.LedgerRepo = (*LedgerRepo)(nil)

// Append adds a new ledger entry to the append-only ledger.
func (r *LedgerRepo) Append(ctx context.Context, entry ports.LedgerEntry) (ports.LedgerEntry, error) {
	// Generate ID if empty
	if entry.ID == "" {
		entry.ID = fmt.Sprintf("le-%d", entry.BlockRef.Number)
	}

	_, err := r.db.ExecContext(ctx, `
		INSERT INTO pnl_ledger (
			id, position_id, kind, amount, token_symbol,
			chain, block_number, block_hash, block_time, tx_hash
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		ON CONFLICT (id) DO NOTHING
	`,
		entry.ID,
		entry.PositionID,
		string(entry.Kind),
		entry.Amount.String(),
		entry.TokenSymbol,
		chainIDToInt(entry.BlockRef.Chain),
		entry.BlockRef.Number,
		entry.BlockRef.Hash,
		entry.BlockRef.TimeUnix,
		entry.TxHash,
	)
	if err != nil {
		return entry, fmt.Errorf("failed to append ledger entry: %w", err)
	}
	return entry, nil
}

// ByPosition returns all ledger entries for a given position.
func (r *LedgerRepo) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, position_id, kind, amount, token_symbol, chain, block_number, block_hash, block_time, tx_hash
		FROM pnl_ledger
		WHERE position_id = $1
		ORDER BY block_number ASC
	`, positionID)
	if err != nil {
		return nil, fmt.Errorf("failed to query ledger entries: %w", err)
	}
	defer rows.Close()

	var entries []ports.LedgerEntry
	for rows.Next() {
		var entry ports.LedgerEntry
		var chain int
		var amountStr string

		err := rows.Scan(
			&entry.ID,
			&entry.PositionID,
			&entry.Kind,
			&amountStr,
			&entry.TokenSymbol,
			&chain,
			&entry.BlockRef.Number,
			&entry.BlockRef.Hash,
			&entry.BlockRef.TimeUnix,
			&entry.TxHash,
		)
		if err != nil {
			continue
		}

		entry.BlockRef.Chain = intToChainID(chain)
		entry.Amount = domain.MustDecimal(amountStr)

		entries = append(entries, entry)
	}

	return entries, rows.Err()
}

// ByPositionAndKind returns ledger entries filtered by position and kind.
func (r *LedgerRepo) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, position_id, kind, amount, token_symbol, chain, block_number, block_hash, block_time, tx_hash
		FROM pnl_ledger
		WHERE position_id = $1 AND kind = $2
		ORDER BY block_number ASC
	`, positionID, string(kind))
	if err != nil {
		return nil, fmt.Errorf("failed to query ledger entries: %w", err)
	}
	defer rows.Close()

	var entries []ports.LedgerEntry
	for rows.Next() {
		var entry ports.LedgerEntry
		var chain int
		var amountStr string

		err := rows.Scan(
			&entry.ID,
			&entry.PositionID,
			&entry.Kind,
			&amountStr,
			&entry.TokenSymbol,
			&chain,
			&entry.BlockRef.Number,
			&entry.BlockRef.Hash,
			&entry.BlockRef.TimeUnix,
			&entry.TxHash,
		)
		if err != nil {
			continue
		}

		entry.BlockRef.Chain = intToChainID(chain)
		entry.Amount = domain.MustDecimal(amountStr)

		entries = append(entries, entry)
	}

	return entries, rows.Err()
}

// AggregateByKind computes the total net PnL for a position by entry kind.
func (r *LedgerRepo) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT kind, SUM(CAST(amount AS NUMERIC)) as total
		FROM pnl_ledger
		WHERE position_id = $1
		GROUP BY kind
	`, positionID)
	if err != nil {
		return nil, fmt.Errorf("failed to aggregate ledger entries: %w", err)
	}
	defer rows.Close()

	result := make(map[ports.LedgerEntryKind]domain.Decimal)
	for rows.Next() {
		var kind ports.LedgerEntryKind
		var totalStr string

		if err := rows.Scan(&kind, &totalStr); err != nil {
			continue
		}

		result[kind] = domain.MustDecimal(totalStr)
	}

	// Initialize all kinds to zero if not present
	for _, k := range []ports.LedgerEntryKind{
		ports.LedgerEntryFee,
		ports.LedgerEntryIL,
		ports.LedgerEntrySwap,
		ports.LedgerEntryGas,
		ports.LedgerEntrySlippage,
		ports.LedgerEntryRug,
	} {
		if _, ok := result[k]; !ok {
			result[k] = domain.MustDecimal("0")
		}
	}

	return result, rows.Err()
}

// LatestBlock returns the highest block number with any ledger entry.
func (r *LedgerRepo) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	var blockRef domain.BlockRef
	var chain int

	err := r.db.QueryRowContext(ctx, `
		SELECT chain, block_number, block_hash, block_time
		FROM pnl_ledger
		ORDER BY block_number DESC
		LIMIT 1
	`).Scan(&chain, &blockRef.Number, &blockRef.Hash, &blockRef.TimeUnix)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query latest block: %w", err)
	}

	blockRef.Chain = intToChainID(chain)
	return &blockRef, nil
}