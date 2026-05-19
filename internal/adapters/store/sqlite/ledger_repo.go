// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// LedgerRepo implements ports.LedgerRepo using SQLite.
// Phase 0 stub - uses fixture data in backtest CLI.
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
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO dryrun_pnl_ledger (
			position_id, pool_id, chain, block_number, block_hash, block_time,
			fee_usd, il_usd, swap_cost_usd, gas_usd, slippage_usd, rug_loss_usd, net_pnl_usd, trace_id
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`,
		entry.PositionID,
		"",
		chainIDToInt(entry.BlockRef.Chain),
		entry.BlockRef.Number,
		entry.BlockRef.Hash,
		entry.BlockRef.TimeUnix,
		entry.Amount.String(), // fee_usd
		"0",  // il_usd
		"0",  // swap_cost_usd
		"0",  // gas_usd
		"0",  // slippage_usd
		"0",  // rug_loss_usd
		entry.Amount.String(), // net_pnl_usd
		"",
	)
	if err != nil {
		return entry, fmt.Errorf("failed to append ledger entry: %w", err)
	}
	return entry, nil
}

// ByPosition returns all ledger entries for a given position.
func (r *LedgerRepo) ByPosition(ctx context.Context, positionID string) ([]ports.LedgerEntry, error) {
	rows, err := r.db.QueryContext(ctx, `
		SELECT position_id, pool_id, chain, block_number, block_hash, block_time, fee_usd
		FROM dryrun_pnl_ledger
		WHERE position_id = ?
		ORDER BY block_number ASC
	`, positionID)
	if err != nil {
		return nil, fmt.Errorf("failed to query ledger entries: %w", err)
	}
	defer rows.Close()

	var entries []ports.LedgerEntry
	for rows.Next() {
		var entry ports.LedgerEntry
		var chain, blockNumber, blockTime int
		var poolID, feeUSD string

		err := rows.Scan(&entry.PositionID, &poolID, &chain, &blockNumber, &entry.BlockRef.Hash, &blockTime, &feeUSD)
		if err != nil {
			continue
		}

		entry.BlockRef.Chain = intToChainID(chain)
		entry.BlockRef.Number = uint64(blockNumber)
		entry.BlockRef.TimeUnix = int64(blockTime)
		entry.Amount = domain.MustDecimal(feeUSD)

		entries = append(entries, entry)
	}

	return entries, rows.Err()
}

// ByPositionAndKind returns ledger entries filtered by position and kind.
func (r *LedgerRepo) ByPositionAndKind(ctx context.Context, positionID string, kind ports.LedgerEntryKind) ([]ports.LedgerEntry, error) {
	// Phase 0: return all entries (kind filtering not implemented)
	return r.ByPosition(ctx, positionID)
}

// AggregateByKind computes the total net PnL for a position by entry kind.
func (r *LedgerRepo) AggregateByKind(ctx context.Context, positionID string) (map[ports.LedgerEntryKind]domain.Decimal, error) {
	entries, err := r.ByPosition(ctx, positionID)
	if err != nil {
		return nil, err
	}

	result := make(map[ports.LedgerEntryKind]domain.Decimal)
	for _, entry := range entries {
		result[entry.Kind] = result[entry.Kind].Add(entry.Amount)
	}
	return result, nil
}

// LatestBlock returns the highest block number with any ledger entry.
func (r *LedgerRepo) LatestBlock(ctx context.Context) (*domain.BlockRef, error) {
	var blockRef domain.BlockRef
	err := r.db.QueryRowContext(ctx, `
		SELECT chain, block_number, block_hash, block_time
		FROM dryrun_pnl_ledger
		ORDER BY block_number DESC
		LIMIT 1
	`).Scan(
		&blockRef.Chain,
		&blockRef.Number,
		&blockRef.Hash,
		&blockRef.TimeUnix,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query latest block: %w", err)
	}
	return &blockRef, nil
}