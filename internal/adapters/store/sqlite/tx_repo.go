// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// TxRepo implements ports.TxRepo using SQLite.
// This is a Phase 0 stub implementation.
type TxRepo struct {
	db *sql.DB
}

// NewTxRepo creates a new TxRepo backed by the given database.
func NewTxRepo(db *sql.DB) *TxRepo {
	return &TxRepo{db: db}
}

// Compile-time interface assertion
var _ ports.TxRepo = (*TxRepo)(nil)

// UpsertTx creates or updates a transaction record.
func (r *TxRepo) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO dryrun_positions (position_id) VALUES ('stub_tx_placeholder')
	`, tx.Chain, tx.Hash)
	if err != nil {
		return fmt.Errorf("not implemented: T-130 TxRepo.UpsertTx")
	}
	return nil
}

// GetTxByHash retrieves a transaction by its chain and hash.
func (r *TxRepo) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	return domain.SignedTx{}, fmt.Errorf("not implemented: T-130 TxRepo.GetTxByHash")
}

// ListTxsByStatus returns transactions matching the given status.
func (r *TxRepo) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	return nil, fmt.Errorf("not implemented: T-130 TxRepo.ListTxsByStatus")
}

// UpdateTxStatus transitions a transaction to a new status.
func (r *TxRepo) UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error {
	return fmt.Errorf("not implemented: T-130 TxRepo.UpdateTxStatus")
}

// ListPendingTxs returns transactions that are still in progress.
func (r *TxRepo) ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error) {
	return nil, fmt.Errorf("not implemented: T-130 TxRepo.ListPendingTxs")
}

// ListStuckTxs returns transactions that have exceeded the stuck timeout.
func (r *TxRepo) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	return nil, fmt.Errorf("not implemented: T-130 TxRepo.ListStuckTxs")
}

// IncrementRFBAttempts increments the RFB attempt counter for a tx.
func (r *TxRepo) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	return fmt.Errorf("not implemented: T-130 TxRepo.IncrementRFBAttempts")
}

// GetRFBAttempts returns the current RFB attempt count for a tx.
func (r *TxRepo) GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error) {
	return 0, fmt.Errorf("not implemented: T-130 TxRepo.GetRFBAttempts")
}