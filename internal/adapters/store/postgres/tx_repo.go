// Package postgres provides PostgreSQL-backed storage adapters for lp-bot.
package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// TxRepo implements ports.TxRepo using PostgreSQL.
type TxRepo struct {
	db *sql.DB
}

// NewTxRepo creates a new TxRepo backed by the given database.
func NewTxRepo(db *sql.DB) *TxRepo {
	return &TxRepo{db: db}
}

// Compile-time interface assertion.
var _ ports.TxRepo = (*TxRepo)(nil)

// UpsertTx creates or updates a transaction record.
func (r *TxRepo) UpsertTx(ctx context.Context, tx domain.SignedTx) error {
	now := time.Now().UnixMilli()
	status := tx.Status
	if status == "" {
		status = domain.TxBuilt
	}
	txHash := tx.Hash
	if txHash == "" {
		txHash = tx.ID
	}
	broadcastAt := txBroadcastTimestamp(status, now)

	_, err := r.db.ExecContext(ctx, `
		INSERT INTO transactions (
			id, chain, tx_hash, from_address, to_address, data, value,
			nonce, deadline, min_out, signature, status,
			block_number, block_hash, broadcast_at,
			gas_used, gas_price, gas_limit,
			rfb_attempts, error_msg, trace_id, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
		ON CONFLICT (tx_hash) DO UPDATE SET
			status = EXCLUDED.status,
			block_number = COALESCE(EXCLUDED.block_number, transactions.block_number),
			block_hash = COALESCE(EXCLUDED.block_hash, transactions.block_hash),
			broadcast_at = COALESCE(EXCLUDED.broadcast_at, transactions.broadcast_at),
			gas_used = COALESCE(EXCLUDED.gas_used, transactions.gas_used),
			gas_price = COALESCE(EXCLUDED.gas_price, transactions.gas_price),
			gas_limit = COALESCE(EXCLUDED.gas_limit, transactions.gas_limit),
			rfb_attempts = EXCLUDED.rfb_attempts,
			error_msg = COALESCE(EXCLUDED.error_msg, transactions.error_msg),
			updated_at = EXCLUDED.updated_at
	`,
		tx.ID,
		tx.Chain,
		txHash,
		tx.From.String(),
		tx.To.String(),
		tx.Data,
		tx.Value.String(),
		tx.Nonce,
		tx.Deadline,
		tx.MinOut.String(),
		tx.Signature,
		status,
		nil,
		nil,
		broadcastAt,
		nil,
		nil,
		nil,
		tx.RFBAttempts,
		nil,
		nil,
		now,
		now,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert tx: %w", err)
	}
	return nil
}

func txBroadcastTimestamp(status domain.TxStatus, now int64) interface{} {
	switch status {
	case domain.TxBroadcast, domain.TxMined, domain.TxConfirmed, domain.TxStuck, domain.TxRFBBumped, domain.TxReverted, domain.TxReorged, domain.TxFailed:
		return now
	default:
		return nil
	}
}

// GetTxByHash retrieves a transaction by its chain and hash.
func (r *TxRepo) GetTxByHash(ctx context.Context, chain domain.ChainID, hash string) (domain.SignedTx, error) {
	var tx domain.SignedTx
	var data, signature []byte
	var valueStr, minOutStr string
	var fromStr, toStr string
	var txChain string
	var blockNumber sql.NullInt64
	var blockHash sql.NullString
	var broadcastAt sql.NullInt64
	var errorMsg, traceID sql.NullString
	var createdAt, updatedAt int64

	err := r.db.QueryRowContext(ctx, `
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM transactions
		WHERE chain = $1 AND tx_hash = $2
	`, string(chain), hash).Scan(
		&tx.ID, &txChain, &tx.Hash, &fromStr, &toStr, &data, &valueStr,
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

	tx.Chain = domain.ChainID(txChain)
	tx.From, _ = domain.ParseAddress(fromStr)
	tx.To, _ = domain.ParseAddress(toStr)
	tx.Data = data
	tx.Signature = signature
	if valueStr != "" {
		tx.Value = domain.MustDecimal(valueStr)
	}
	if minOutStr != "" {
		tx.MinOut = domain.MustDecimal(minOutStr)
	}

	_ = blockNumber
	_ = blockHash
	_ = broadcastAt
	_ = errorMsg
	_ = traceID
	_ = createdAt
	_ = updatedAt

	return tx, nil
}

// ListTxsByStatus returns transactions matching the given status.
func (r *TxRepo) ListTxsByStatus(ctx context.Context, chain domain.ChainID, status domain.TxStatus) ([]domain.SignedTx, error) {
	query := `
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM transactions
		WHERE chain = $1
		ORDER BY created_at DESC
	`
	args := []interface{}{string(chain)}

	if status != "" {
		query = `
			SELECT id, chain, tx_hash, from_address, to_address, data, value,
				   nonce, deadline, min_out, signature, status,
				   block_number, block_hash, broadcast_at,
				   gas_used, gas_price, gas_limit, rfb_attempts,
				   error_msg, trace_id, created_at, updated_at
			FROM transactions
			WHERE chain = $1 AND status = $2
			ORDER BY created_at DESC
		`
		args = append(args, status)
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
	var currentStatus domain.TxStatus
	err := r.db.QueryRowContext(ctx,
		"SELECT status FROM transactions WHERE chain = $1 AND tx_hash = $2",
		string(chain), hash,
	).Scan(&currentStatus)
	if err == sql.ErrNoRows {
		return ports.ErrTxNotFound
	}
	if err != nil {
		return fmt.Errorf("failed to get current tx status: %w", err)
	}
	if !currentStatus.CanTransitionTo(newStatus) {
		return fmt.Errorf("%w: %s -> %s", ports.ErrInvalidTxTransition, currentStatus, newStatus)
	}

	query := "UPDATE transactions SET status = $1, updated_at = $2"
	args := []interface{}{newStatus, time.Now().UnixMilli()}
	if newStatus == domain.TxBroadcast || newStatus == domain.TxRFBBumped {
		query += ", broadcast_at = COALESCE(broadcast_at, $3)"
		args = append(args, time.Now().UnixMilli())
	}
	if ref != nil {
		query += fmt.Sprintf(", block_number = $%d, block_hash = $%d", len(args)+1, len(args)+2)
		args = append(args, ref.Number, ref.Hash)
		query += fmt.Sprintf(" WHERE chain = $%d AND tx_hash = $%d", len(args)+1, len(args)+2)
		args = append(args, string(chain), hash)
	} else {
		query += fmt.Sprintf(" WHERE chain = $%d AND tx_hash = $%d", len(args)+1, len(args)+2)
		args = append(args, string(chain), hash)
	}

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
	rows, err := r.db.QueryContext(ctx, `
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM transactions
		WHERE chain = $1 AND status IN ('built', 'broadcast', 'mined', 'stuck', 'rfb_bumped', 'reverted', 'reorged')
		ORDER BY created_at ASC
	`, string(chain))
	if err != nil {
		return nil, fmt.Errorf("failed to list pending txs: %w", err)
	}
	defer rows.Close()
	return scanTxs(rows)
}

// ListStuckTxs returns transactions that have exceeded the stuck timeout.
func (r *TxRepo) ListStuckTxs(ctx context.Context, chain domain.ChainID, stuckTimeoutSeconds int64) ([]domain.SignedTx, error) {
	cutoff := time.Now().Add(-time.Duration(stuckTimeoutSeconds) * time.Second).UnixMilli()

	rows, err := r.db.QueryContext(ctx, `
		SELECT id, chain, tx_hash, from_address, to_address, data, value,
			   nonce, deadline, min_out, signature, status,
			   block_number, block_hash, broadcast_at,
			   gas_used, gas_price, gas_limit, rfb_attempts,
			   error_msg, trace_id, created_at, updated_at
		FROM transactions
		WHERE chain = $1
		  AND status IN ('broadcast', 'rfb_bumped')
		  AND broadcast_at > 0
		  AND broadcast_at < $2
		ORDER BY broadcast_at ASC
	`, string(chain), cutoff)
	if err != nil {
		return nil, fmt.Errorf("failed to list stuck txs: %w", err)
	}
	defer rows.Close()
	return scanTxs(rows)
}

// IncrementRFBAttempts increments the RFB attempt counter for a tx.
func (r *TxRepo) IncrementRFBAttempts(ctx context.Context, chain domain.ChainID, hash string) error {
	maxAttempts := domain.MaxRBFAttempts()
	result, err := r.db.ExecContext(ctx, `
		UPDATE transactions
		SET rfb_attempts = rfb_attempts + 1, updated_at = $1
		WHERE chain = $2 AND tx_hash = $3 AND rfb_attempts < $4
	`, time.Now().UnixMilli(), string(chain), hash, maxAttempts)
	if err != nil {
		return fmt.Errorf("failed to increment rfb attempts: %w", err)
	}
	rowsAffected, _ := result.RowsAffected()
	if rowsAffected == 0 {
		var attempts int
		err = r.db.QueryRowContext(ctx,
			"SELECT rfb_attempts FROM transactions WHERE chain = $1 AND tx_hash = $2",
			string(chain), hash,
		).Scan(&attempts)
		if err == sql.ErrNoRows {
			return ports.ErrTxNotFound
		}
		if err != nil {
			return fmt.Errorf("failed to check rfb attempts: %w", err)
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
	var attempts int
	err := r.db.QueryRowContext(ctx,
		"SELECT rfb_attempts FROM transactions WHERE chain = $1 AND tx_hash = $2",
		string(chain), hash,
	).Scan(&attempts)
	if err == sql.ErrNoRows {
		return 0, ports.ErrTxNotFound
	}
	if err != nil {
		return 0, fmt.Errorf("failed to get rfb attempts: %w", err)
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
		var fromStr, toStr, txChain string
		var blockNumber sql.NullInt64
		var blockHash sql.NullString
		var broadcastAt sql.NullInt64
		var createdAt, updatedAt int64
		var errorMsg, traceID sql.NullString

		err := rows.Scan(
			&tx.ID, &txChain, &tx.Hash, &fromStr, &toStr, &data, &valueStr,
			&tx.Nonce, &tx.Deadline, &minOutStr, &signature, &tx.Status,
			&blockNumber, &blockHash, &broadcastAt,
			&sql.NullString{}, &sql.NullString{}, &sql.NullString{}, &tx.RFBAttempts,
			&errorMsg, &traceID, &createdAt, &updatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan tx: %w", err)
		}

		tx.Chain = domain.ChainID(txChain)
		tx.From, _ = domain.ParseAddress(fromStr)
		tx.To, _ = domain.ParseAddress(toStr)
		tx.Data = data
		tx.Signature = signature
		if valueStr != "" {
			tx.Value = domain.MustDecimal(valueStr)
		}
		if minOutStr != "" {
			tx.MinOut = domain.MustDecimal(minOutStr)
		}
		_ = blockNumber
		_ = blockHash
		_ = broadcastAt
		_ = errorMsg
		_ = traceID
		_ = createdAt
		_ = updatedAt

		txs = append(txs, tx)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating tx rows: %w", err)
	}
	return txs, nil
}
