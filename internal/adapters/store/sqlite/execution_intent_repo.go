package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

type ExecutionIntentRepo struct {
	db     *sql.DB
	prefix string
}

func NewExecutionIntentRepo(db *sql.DB, prefix string) *ExecutionIntentRepo {
	return &ExecutionIntentRepo{db: db, prefix: prefix}
}

var _ ports.ExecutionIntentRepo = (*ExecutionIntentRepo)(nil)

func (r *ExecutionIntentRepo) Reserve(ctx context.Context, intent *domain.ExecutionIntent) error {
	if intent == nil {
		return fmt.Errorf("execution intent is nil")
	}
	now := time.Now().UnixMilli()
	if intent.CreatedAt == 0 {
		intent.CreatedAt = now
	}
	intent.UpdatedAt = now
	if intent.Status == "" {
		intent.Status = domain.IntentStatusIntended
	}
	table := r.prefix + "execution_intents"
	_, err := r.db.ExecContext(ctx, fmt.Sprintf(`
		INSERT INTO %s (
			id, mode, chain, pool_id, position_id, action, status, idempotency_key,
			unsigned_tx_hash, signed_tx_hash, tx_hash, reason,
			risk_snapshot_json, sizing_snapshot_json, decision_trace_id,
			created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, table),
		intent.ID, intent.Mode, string(intent.Chain), intent.PoolID, intent.PositionID, intent.Action, string(intent.Status), intent.IdempotencyKey,
		intent.UnsignedTxHash, intent.SignedTxHash, intent.TxHash, intent.Reason,
		defaultSQLiteMetadataJSON(intent.RiskSnapshotJSON), defaultSQLiteMetadataJSON(intent.SizingSnapshotJSON), intent.DecisionTraceID,
		intent.CreatedAt, intent.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("reserve execution intent: %w", err)
	}
	return nil
}

func (r *ExecutionIntentRepo) FindByID(ctx context.Context, id string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, fmt.Sprintf(`SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json,'{}'), COALESCE(sizing_snapshot_json,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at FROM %sexecution_intents WHERE id = ?`, r.prefix), id)
}

func (r *ExecutionIntentRepo) FindByIdempotencyKey(ctx context.Context, key string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, fmt.Sprintf(`SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json,'{}'), COALESCE(sizing_snapshot_json,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at FROM %sexecution_intents WHERE idempotency_key = ?`, r.prefix), key)
}

func (r *ExecutionIntentRepo) FindByTxHash(ctx context.Context, chain domain.ChainID, txHash string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, fmt.Sprintf(`SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json,'{}'), COALESCE(sizing_snapshot_json,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at FROM %sexecution_intents WHERE chain = ? AND tx_hash = ?`, r.prefix), string(chain), txHash)
}

func (r *ExecutionIntentRepo) Update(ctx context.Context, intent *domain.ExecutionIntent) error {
	if intent == nil {
		return fmt.Errorf("execution intent is nil")
	}
	intent.UpdatedAt = time.Now().UnixMilli()
	table := r.prefix + "execution_intents"
	result, err := r.db.ExecContext(ctx, fmt.Sprintf(`
		UPDATE %s
		SET status = ?, unsigned_tx_hash = ?, signed_tx_hash = ?, tx_hash = ?, reason = ?,
		    risk_snapshot_json = ?, sizing_snapshot_json = ?, decision_trace_id = ?, updated_at = ?
		WHERE id = ?
	`, table),
		string(intent.Status), intent.UnsignedTxHash, intent.SignedTxHash, intent.TxHash, intent.Reason,
		defaultSQLiteMetadataJSON(intent.RiskSnapshotJSON), defaultSQLiteMetadataJSON(intent.SizingSnapshotJSON), intent.DecisionTraceID, intent.UpdatedAt, intent.ID,
	)
	if err != nil {
		return fmt.Errorf("update execution intent: %w", err)
	}
	rows, _ := result.RowsAffected()
	if rows == 0 {
		return ports.ErrExecutionIntentNotFound
	}
	return nil
}

func (r *ExecutionIntentRepo) findOne(ctx context.Context, query string, args ...interface{}) (*domain.ExecutionIntent, error) {
	var intent domain.ExecutionIntent
	var chain string
	err := r.db.QueryRowContext(ctx, query, args...).Scan(
		&intent.ID, &intent.Mode, &chain, &intent.PoolID, &intent.PositionID, &intent.Action, &intent.Status, &intent.IdempotencyKey,
		&intent.UnsignedTxHash, &intent.SignedTxHash, &intent.TxHash, &intent.Reason,
		&intent.RiskSnapshotJSON, &intent.SizingSnapshotJSON, &intent.DecisionTraceID,
		&intent.CreatedAt, &intent.UpdatedAt,
	)
	if err == sql.ErrNoRows {
		return nil, ports.ErrExecutionIntentNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("query execution intent: %w", err)
	}
	intent.Chain = domain.ChainID(chain)
	return &intent, nil
}
