// Package sqlite provides SQLite-backed storage adapters for lp-bot.
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// TxRepo implements ports.TxRepo using SQLite.
type TxRepo struct {
	db     *sql.DB
	prefix string
}

// NewTxRepo creates a new TxRepo backed by the given database.
// The prefix is used to match the schema prefix applied during migrations.
func NewTxRepo(db *sql.DB, prefix string) *TxRepo {
	return &TxRepo{db: db, prefix: prefix}
}

// Compile-time interface assertion
var _ ports.TxRepo = (*TxRepo)(nil)

// UpsertTx creates or updates a transaction record.
func (r *TxRepo) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	now := time.Now().UnixMilli()
	table := r.prefix + "transactions"

	query := fmt.Sprintf(`
		INSERT INTO %s (
			id, chain, tx_hash, from_address, to_address, data, value,
			nonce, deadline, min_out, signature, status,
			block_number, block_hash, broadcast_at,
			gas_used, gas_price, gas_limit, rfb_attempts,
			error_msg, trace_id, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(tx_hash) DO UPDATE SET
			status = excluded.status,
			block_number = COALESCE(excluded.block_number, %[1]s.block_number),
			block_hash = COALESCE(excluded.block_hash, %[1]s.block_hash),
			broadcast_at = COALESCE(excluded.broadcast_at, %[1]s.broadcast_at),
			gas_used = COALESCE(excluded.gas_used, %[1]s.gas_used),
			gas_price = COALESCE(excluded.gas_price, %[1]s.gas_price),
			rfb_attempts = excluded.rfb_attempts,
			error_msg = COALESCE(excluded.error_msg, %[1]s.error_msg),
			updated_at = excluded.updated_at
	`, table)

	// Determine status - use tx.Status if set, otherwise default to built
	status := tx.Status
	if status == "" {
		status = domain.TxBuilt
	}
	var broadcastAt interface{}
	switch status {
	case domain.TxSubmittedPrivate, domain.TxBroadcast, domain.TxMined, domain.TxConfirmed, domain.TxStuck, domain.TxRFBBumped, domain.TxReverted, domain.TxReorged, domain.TxFailed:
		broadcastAt = now
	}

	_, err := r.db.ExecContext(ctx, query,
		tx.ID, tx.Chain, tx.Hash, tx.From.String(), tx.To.String(), tx.Data, tx.Value.String(),
		tx.Nonce, tx.Deadline, tx.MinOut.String(), tx.Signature,
		status,                // Initial status
		nil, nil, broadcastAt, // block refs
		nil, nil, nil, // gas
		tx.RFBAttempts,
		nil,      // error_msg
		nil,      // trace_id
		now, now, // created_at, updated_at
	)
	if err != nil {
		return fmt.Errorf("failed to upsert tx: %w", err)
	}
	return nil
}

// GetTxByHash retrieves a transaction by its chain and hash.
func (r *TxRepo) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	table := r.prefix + "transactions"

	query := fmt.Sprintf(`
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM %s
		WHERE chain = ? AND tx_hash = ?
	`, table)

	var tx domain.SignedTx
	var data, signature []byte
	var valueStr, minOutStr string
	var fromStr, toStr string
	var blockNumber sql.NullInt64
	var blockHash sql.NullString
	var broadcastAt sql.NullInt64
	var errorMsg, traceID sql.NullString
	var createdAt, updatedAt int64

	err := r.db.QueryRowContext(ctx, query, chain, hash).Scan(
		&tx.ID, &tx.Chain, &tx.Hash, &fromStr, &toStr, &data, &valueStr,
		&tx.Nonce, &tx.Deadline, &minOutStr, &signature, &tx.Status,
		&blockNumber, &blockHash, &broadcastAt,
		&sql.NullString{}, &sql.NullString{}, &sql.NullString{}, &tx.RFBAttempts,
		&errorMsg, &traceID, &createdAt, &updatedAt,
	)
	if err == sql.ErrNoRows {
		return domain.SignedTx{}, ports.ErrTxNotFound
	}
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("failed to get tx: %w", err)
	}

	// Convert string addresses back to domain.Address
	tx.From, _ = domain.ParseAddress(fromStr)
	tx.To, _ = domain.ParseAddress(toStr)
	// Restore byte slices
	tx.Data = data
	tx.Signature = signature

	return tx, nil
}

// ListTxsByStatus returns transactions matching the given status.
func (r *TxRepo) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	table := r.prefix + "transactions"

	var query string
	var args []interface{}

	if status == "" {
		query = fmt.Sprintf(`
			SELECT id, chain, tx_hash, from_address, to_address, data, value,
				   nonce, deadline, min_out, signature, status,
				   block_number, block_hash, broadcast_at,
				   gas_used, gas_price, gas_limit, rfb_attempts,
				   error_msg, trace_id, created_at, updated_at
			FROM %s
			WHERE chain = ?
			ORDER BY created_at DESC
		`, table)
		args = []interface{}{chain}
	} else {
		query = fmt.Sprintf(`
			SELECT id, chain, tx_hash, from_address, to_address, data, value,
				   nonce, deadline, min_out, signature, status,
				   block_number, block_hash, broadcast_at,
				   gas_used, gas_price, gas_limit, rfb_attempts,
				   error_msg, trace_id, created_at, updated_at
			FROM %s
			WHERE chain = ? AND status = ?
			ORDER BY created_at DESC
		`, table)
		args = []interface{}{chain, status}
	}

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list txs: %w", err)
	}
	defer rows.Close()

	return scanTxs(rows)
}

// UpdateTxStatus transitions a transaction to a new status.
func (r *TxRepo) UpdateTxStatus(ctx context.Context, chain domain.ChainID, hash string, newStatus domain.TxStatus, ref *domain.BlockRef) error {
	table := r.prefix + "transactions"

	// Validate transition
	var currentStatus domain.TxStatus
	err := r.db.QueryRowContext(ctx,
		fmt.Sprintf("SELECT status FROM %s WHERE chain = ? AND tx_hash = ?", table),
		chain, hash,
	).Scan(&currentStatus)
	if err == sql.ErrNoRows {
		return ports.ErrTxNotFound
	}
	if err != nil {
		return fmt.Errorf("failed to get current status: %w", err)
	}

	if !currentStatus.CanTransitionTo(newStatus) {
		return fmt.Errorf("%w: %s → %s", ports.ErrInvalidTxTransition, currentStatus, newStatus)
	}

	// Build update query with optional block ref
	query := fmt.Sprintf(`UPDATE %s SET status = ?, updated_at = ?`, table)
	args := []interface{}{newStatus, time.Now().UnixMilli()}

	if ref != nil {
		query += `, block_number = ?, block_hash = ?`
		args = append(args, ref.Number, ref.Hash)
	}

	query += ` WHERE chain = ? AND tx_hash = ?`
	args = append(args, chain, hash)

	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("failed to update tx status: %w", err)
	}

	rowsAffected, _ := result.RowsAffected()
	if rowsAffected == 0 {
		return ports.ErrTxNotFound
	}

	return nil
}

// ListPendingTxs returns transactions that are still in progress.
func (r *TxRepo) ListPendingTxs(ctx context.Context, chain domain.ChainID) ([]domain.SignedTx, error) {
	table := r.prefix + "transactions"

	query := fmt.Sprintf(`
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM %s
		WHERE chain = ? AND status IN ('built', 'submitted_private', 'broadcast', 'mined', 'stuck', 'rfb_bumped', 'reverted', 'reorged')
		ORDER BY created_at ASC
	`, table)

	rows, err := r.db.QueryContext(ctx, query, chain)
	if err != nil {
		return nil, fmt.Errorf("failed to list pending txs: %w", err)
	}
	defer rows.Close()

	return scanTxs(rows)
}

// ListStuckTxs returns transactions that have exceeded the stuck timeout.
func (r *TxRepo) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	table := r.prefix + "transactions"
	cutoff := time.Now().Add(-time.Duration(stuckTimeoutSeconds) * time.Second).UnixMilli()

	query := fmt.Sprintf(`
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM %s
		WHERE chain = ? AND status IN ('submitted_private', 'broadcast', 'rfb_bumped')
		  AND broadcast_at > 0 AND broadcast_at < ?
		ORDER BY broadcast_at ASC
	`, table)

	rows, err := r.db.QueryContext(ctx, query, chain, cutoff)
	if err != nil {
		return nil, fmt.Errorf("failed to list stuck txs: %w", err)
	}
	defer rows.Close()

	return scanTxs(rows)
}

// IncrementRFBAttempts increments the RFB attempt counter for a tx.
func (r *TxRepo) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	table := r.prefix + "transactions"
	maxAttempts := domain.MaxRBFAttempts()

	result, err := r.db.ExecContext(ctx, fmt.Sprintf(`
		UPDATE %s
		SET rfb_attempts = rfb_attempts + 1, updated_at = ?
		WHERE chain = ? AND tx_hash = ? AND rfb_attempts < ?
	`, table), time.Now().UnixMilli(), chain, hash, maxAttempts)
	if err != nil {
		return fmt.Errorf("failed to increment RFB attempts: %w", err)
	}

	rowsAffected, _ := result.RowsAffected()
	if rowsAffected == 0 {
		var attempts int
		err = r.db.QueryRowContext(ctx,
			fmt.Sprintf("SELECT rfb_attempts FROM %s WHERE chain = ? AND tx_hash = ?", table),
			chain, hash,
		).Scan(&attempts)
		if err == sql.ErrNoRows {
			return ports.ErrTxNotFound
		}
		if err != nil {
			return fmt.Errorf("failed to check RFB attempts: %w", err)
		}
		if attempts >= maxAttempts {
			return ports.ErrMaxRFBAttemptsExceeded
		}
		return ports.ErrTxNotFound
	}

	return nil
}

// GetRFBAttempts returns the current RFB attempt count for a tx.
func (r *TxRepo) GetRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) (int, error) {
	table := r.prefix + "transactions"

	var attempts int
	err := r.db.QueryRowContext(ctx,
		fmt.Sprintf("SELECT rfb_attempts FROM %s WHERE chain = ? AND tx_hash = ?", table),
		chain, hash,
	).Scan(&attempts)
	if err == sql.ErrNoRows {
		return 0, ports.ErrTxNotFound
	}
	if err != nil {
		return 0, fmt.Errorf("failed to get RFB attempts: %w", err)
	}
	return attempts, nil
}

// scanTxs scans multiple rows into a slice of SignedTx.
func scanTxs(rows *sql.Rows) ([]domain.SignedTx, error) {
	var txs []domain.SignedTx

	for rows.Next() {
		var tx domain.SignedTx
		var data, signature []byte
		var valueStr, minOutStr string
		var fromStr, toStr string
		var blockNumber sql.NullInt64
		var blockHash sql.NullString
		var broadcastAt sql.NullInt64
		var errorMsg, traceID sql.NullString
		var createdAt, updatedAt int64

		err := rows.Scan(
			&tx.ID, &tx.Chain, &tx.Hash, &fromStr, &toStr, &data, &valueStr,
			&tx.Nonce, &tx.Deadline, &minOutStr, &signature, &tx.Status,
			&blockNumber, &blockHash, &broadcastAt,
			&sql.NullString{}, &sql.NullString{}, &sql.NullString{}, &tx.RFBAttempts,
			&errorMsg, &traceID, &createdAt, &updatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan tx: %w", err)
		}

		// Convert string addresses back to domain.Address
		tx.From, _ = domain.ParseAddress(fromStr)
		tx.To, _ = domain.ParseAddress(toStr)
		tx.Data = data
		tx.Signature = signature
		txs = append(txs, tx)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating txs: %w", err)
	}

	return txs, nil
}
