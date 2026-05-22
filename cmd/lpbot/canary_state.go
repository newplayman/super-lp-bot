package main

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

type canaryEvent struct {
	Chain           string
	Command         string
	Stage           string
	Status          string
	PositionID      string
	PoolID          string
	Wallet          string
	TokenID         string
	TxHash          string
	AmountUSD       string
	RequiredUSDCRaw string
	RequiredWETHRaw string
	InputMint       string
	OutputMint      string
	InputAmountRaw  string
	OutputAmountRaw string
	SOLBalanceRaw   string
	USDCBalanceRaw  string
	GasEstimate     uint64
	Message         string
	ErrorMsg        string
	CreatedAt       int64
}

type canaryEventWriter struct {
	store interface {
		DB() *sql.DB
		Close() error
	}
	db *sql.DB
}

type canaryStrategyApproval struct {
	TickTime       int64
	AgeSeconds     int64
	ScoreTotal     float64
	FinalAction    string
	PipelineStage  string
	PipelineReason string
}

const (
	canaryShadowApprovalMaxAge    = 3 * time.Hour
	canaryShadowApprovalStaleGrace = 12 * time.Hour
)

func newCanaryEventWriter(ctx context.Context, cfg *config.Config) (*canaryEventWriter, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config is nil")
	}
	dsn := strings.TrimSpace(cfg.Store.PostgresDSN)
	if dsn == "" {
		return nil, fmt.Errorf("store.postgres_dsn is empty; cannot persist canary state")
	}
	store, err := postgres.NewFromDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("open postgres for canary state: %w", err)
	}
	writer := &canaryEventWriter{store: store, db: store.DB()}
	if err := writer.ensure(ctx); err != nil {
		_ = writer.Close()
		return nil, err
	}
	return writer, nil
}

func (w *canaryEventWriter) Close() error {
	if w == nil || w.store == nil {
		return nil
	}
	return w.store.Close()
}

func (w *canaryEventWriter) ensure(ctx context.Context) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	_, err := w.db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS canary_events (
			id TEXT PRIMARY KEY,
			chain TEXT NOT NULL DEFAULT '',
			command TEXT NOT NULL DEFAULT '',
			stage TEXT NOT NULL DEFAULT '',
			status TEXT NOT NULL DEFAULT '',
			position_id TEXT NOT NULL DEFAULT '',
			pool_id TEXT NOT NULL DEFAULT '',
			wallet TEXT NOT NULL DEFAULT '',
			token_id TEXT NOT NULL DEFAULT '',
			tx_hash TEXT NOT NULL DEFAULT '',
			amount_usd TEXT NOT NULL DEFAULT '',
			required_usdc_raw TEXT NOT NULL DEFAULT '',
			required_weth_raw TEXT NOT NULL DEFAULT '',
			input_mint TEXT NOT NULL DEFAULT '',
			output_mint TEXT NOT NULL DEFAULT '',
			input_amount_raw TEXT NOT NULL DEFAULT '',
			output_amount_raw TEXT NOT NULL DEFAULT '',
			sol_balance_raw TEXT NOT NULL DEFAULT '',
			usdc_balance_raw TEXT NOT NULL DEFAULT '',
			gas_estimate BIGINT NOT NULL DEFAULT 0,
			message TEXT NOT NULL DEFAULT '',
			error_msg TEXT NOT NULL DEFAULT '',
			created_at BIGINT NOT NULL DEFAULT 0,
			updated_at BIGINT NOT NULL DEFAULT 0
		);
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS chain TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS input_mint TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS output_mint TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS input_amount_raw TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS output_amount_raw TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS sol_balance_raw TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_events
			ADD COLUMN IF NOT EXISTS usdc_balance_raw TEXT NOT NULL DEFAULT '';
		CREATE INDEX IF NOT EXISTS idx_canary_events_created_at
			ON canary_events(created_at DESC);
		CREATE INDEX IF NOT EXISTS idx_canary_events_position
			ON canary_events(position_id, created_at DESC);
		CREATE INDEX IF NOT EXISTS idx_canary_events_tx_hash
			ON canary_events(tx_hash);
	`)
	if err != nil {
		return fmt.Errorf("ensure canary_events table: %w", err)
	}
	return nil
}

func (w *canaryEventWriter) Record(ctx context.Context, event canaryEvent) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	now := time.Now().Unix()
	if event.CreatedAt <= 0 {
		event.CreatedAt = now
	}
	if event.Status == "" {
		event.Status = "ok"
	}
	if strings.TrimSpace(event.Chain) == "" {
		event.Chain = string(domain.ChainBase)
	}
	idInput := fmt.Sprintf("%s:%s:%s:%s:%d", event.Command, event.Stage, event.PositionID, event.TxHash, time.Now().UnixNano())
	id := shadowID("canary-event", idInput, time.Now().UnixNano())
	_, err := w.db.ExecContext(ctx, `
		INSERT INTO canary_events (
			id, chain, command, stage, status, position_id, pool_id, wallet, token_id, tx_hash,
			amount_usd, required_usdc_raw, required_weth_raw, input_mint, output_mint,
			input_amount_raw, output_amount_raw, sol_balance_raw, usdc_balance_raw,
			gas_estimate, message, error_msg, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
	`,
		id,
		event.Chain,
		event.Command,
		event.Stage,
		event.Status,
		event.PositionID,
		event.PoolID,
		event.Wallet,
		event.TokenID,
		event.TxHash,
		event.AmountUSD,
		event.RequiredUSDCRaw,
		event.RequiredWETHRaw,
		event.InputMint,
		event.OutputMint,
		event.InputAmountRaw,
		event.OutputAmountRaw,
		event.SOLBalanceRaw,
		event.USDCBalanceRaw,
		event.GasEstimate,
		event.Message,
		event.ErrorMsg,
		event.CreatedAt,
		now,
	)
	if err != nil {
		return fmt.Errorf("insert canary event: %w", err)
	}
	return nil
}

func (w *canaryEventWriter) RecordSignedTx(ctx context.Context, signed domain.SignedTx, status domain.TxStatus) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	signed.Status = status
	return postgres.NewTxRepo(w.db).UpsertTx(ctx, signed)
}

func (w *canaryEventWriter) SaveOpeningPosition(ctx context.Context, positionID string, pool domain.Pool, amountUSD domain.Decimal, openedAt int64) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	if positionID == "" {
		return fmt.Errorf("position id is empty")
	}
	pos := &domain.Position{
		ID:        positionID,
		PoolID:    pool.ID,
		Chain:     pool.Chain,
		Status:    domain.StatusOpening,
		Tier:      pool.Tier_,
		AmountUSD: amountUSD,
		TickLower: int64(pool.Tick),
		TickUpper: int64(pool.Tick),
		OpenedAt:  openedAt,
	}
	return postgres.NewPositionRepo(w.db).Save(ctx, pos)
}

func (w *canaryEventWriter) RequireRecentShadowApproval(ctx context.Context, poolID string, maxAge time.Duration) (canaryStrategyApproval, error) {
	if w == nil || w.db == nil {
		return canaryStrategyApproval{}, fmt.Errorf("canary state writer is not initialized")
	}
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return canaryStrategyApproval{}, fmt.Errorf("pool id is empty")
	}
	if maxAge <= 0 {
		maxAge = canaryShadowApprovalMaxAge
	}

	var row struct {
		TickTime       int64
		ScoreTotal     float64
		Selected       bool
		IntentOpen     bool
		ChainStage     string
		PipelineStage  string
		PipelineOK     bool
		PipelineReason string
		FinalAction    string
	}
	err := w.db.QueryRowContext(ctx, `
		SELECT tick_time, score_total, selected, intent_open, chain_stage,
		       pipeline_stage, pipeline_ok, pipeline_reason, final_action
		FROM shadow_decision_trace
		WHERE lower(pool_id) = lower($1)
		ORDER BY tick_time DESC
		LIMIT 1
	`, poolID).Scan(
		&row.TickTime,
		&row.ScoreTotal,
		&row.Selected,
		&row.IntentOpen,
		&row.ChainStage,
		&row.PipelineStage,
		&row.PipelineOK,
		&row.PipelineReason,
		&row.FinalAction,
	)
	if err == sql.ErrNoRows {
		return canaryStrategyApproval{}, fmt.Errorf("canary quality gate blocked: no recent shadow decision for pool %s", poolID)
	}
	if err != nil {
		return canaryStrategyApproval{}, fmt.Errorf("read shadow decision for canary quality gate: %w", err)
	}

	ageSeconds := time.Now().Unix() - row.TickTime
	if ageSeconds < 0 {
		ageSeconds = 0
	}
	approval := canaryStrategyApproval{
		TickTime:       row.TickTime,
		AgeSeconds:     ageSeconds,
		ScoreTotal:     row.ScoreTotal,
		FinalAction:    row.FinalAction,
		PipelineStage:  row.PipelineStage,
		PipelineReason: row.PipelineReason,
	}
	age := time.Duration(ageSeconds) * time.Second
	if age > maxAge {
		staleGraceOK := age <= canaryShadowApprovalStaleGrace &&
			row.Selected &&
			row.IntentOpen &&
			row.ScoreTotal >= shadowOpenScoreThreshold &&
			(row.PipelineOK || row.FinalAction == "reuse_shadow_position")
		if !staleGraceOK {
			return approval, fmt.Errorf("canary quality gate blocked: latest shadow decision is stale age=%ds max=%s", ageSeconds, maxAge)
		}
		if approval.PipelineReason != "" {
			approval.PipelineReason += "; "
		}
		approval.PipelineReason += fmt.Sprintf("stale shadow approval accepted within grace window (%s)", canaryShadowApprovalStaleGrace)
	}
	if row.ScoreTotal < shadowOpenScoreThreshold {
		return approval, fmt.Errorf("canary quality gate blocked: score %.2f below threshold %.2f", row.ScoreTotal, shadowOpenScoreThreshold)
	}
	if !row.Selected || !row.IntentOpen || !row.PipelineOK {
		return approval, fmt.Errorf("canary quality gate blocked: selected=%t intent_open=%t pipeline_ok=%t stage=%s reason=%s", row.Selected, row.IntentOpen, row.PipelineOK, row.PipelineStage, row.PipelineReason)
	}
	if row.ChainStage != "chain_state_ok" && row.ChainStage != "chain_v3_validated" {
		return approval, fmt.Errorf("canary quality gate blocked: chain_stage=%s", row.ChainStage)
	}
	if row.FinalAction != "open_shadow_position" && row.FinalAction != "reuse_shadow_position" {
		return approval, fmt.Errorf("canary quality gate blocked: final_action=%s", row.FinalAction)
	}
	return approval, nil
}
