package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

type ExecutionIntentRepo struct {
	db *sql.DB
}

func NewExecutionIntentRepo(db *sql.DB) *ExecutionIntentRepo {
	return &ExecutionIntentRepo{db: db}
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
	_, err := r.db.ExecContext(ctx, `
		INSERT INTO execution_intents (
			id, mode, chain, pool_id, position_id, action, status, idempotency_key,
			unsigned_tx_hash, signed_tx_hash, tx_hash, reason,
			risk_snapshot_json, sizing_snapshot_json, decision_trace_id,
			created_at, updated_at
		) VALUES (
			$1,$2,$3,$4,$5,$6,$7,$8,
			$9,$10,$11,$12,
			$13::jsonb,$14::jsonb,$15,
			$16,$17
		)
	`,
		intent.ID, intent.Mode, string(intent.Chain), intent.PoolID, intent.PositionID, intent.Action, string(intent.Status), intent.IdempotencyKey,
		intent.UnsignedTxHash, intent.SignedTxHash, intent.TxHash, intent.Reason,
		defaultPositionMetadataJSON(intent.RiskSnapshotJSON), defaultPositionMetadataJSON(intent.SizingSnapshotJSON), intent.DecisionTraceID,
		intent.CreatedAt, intent.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("reserve execution intent: %w", err)
	}
	return nil
}

func (r *ExecutionIntentRepo) FindByID(ctx context.Context, id string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, `SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json::text,'{}'), COALESCE(sizing_snapshot_json::text,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at
		FROM execution_intents WHERE id = $1`, id)
}

func (r *ExecutionIntentRepo) FindByIdempotencyKey(ctx context.Context, key string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, `SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json::text,'{}'), COALESCE(sizing_snapshot_json::text,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at
		FROM execution_intents WHERE idempotency_key = $1`, key)
}

func (r *ExecutionIntentRepo) FindByTxHash(ctx context.Context, chain domain.ChainID, txHash string) (*domain.ExecutionIntent, error) {
	return r.findOne(ctx, `SELECT id, mode, chain, pool_id, position_id, action, status, idempotency_key,
		COALESCE(unsigned_tx_hash,''), COALESCE(signed_tx_hash,''), COALESCE(tx_hash,''), COALESCE(reason,''),
		COALESCE(risk_snapshot_json::text,'{}'), COALESCE(sizing_snapshot_json::text,'{}'), COALESCE(decision_trace_id,''),
		created_at, updated_at
		FROM execution_intents WHERE chain = $1 AND tx_hash = $2`, string(chain), txHash)
}

func (r *ExecutionIntentRepo) Update(ctx context.Context, intent *domain.ExecutionIntent) error {
	if intent == nil {
		return fmt.Errorf("execution intent is nil")
	}
	intent.UpdatedAt = time.Now().UnixMilli()
	result, err := r.db.ExecContext(ctx, `
		UPDATE execution_intents
		SET status = $2,
		    unsigned_tx_hash = $3,
		    signed_tx_hash = $4,
		    tx_hash = $5,
		    reason = $6,
		    risk_snapshot_json = $7::jsonb,
		    sizing_snapshot_json = $8::jsonb,
		    decision_trace_id = $9,
		    updated_at = $10
		WHERE id = $1
	`, intent.ID, string(intent.Status), intent.UnsignedTxHash, intent.SignedTxHash, intent.TxHash, intent.Reason,
		defaultPositionMetadataJSON(intent.RiskSnapshotJSON), defaultPositionMetadataJSON(intent.SizingSnapshotJSON), intent.DecisionTraceID, intent.UpdatedAt,
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
