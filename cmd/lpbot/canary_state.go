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
			gas_estimate BIGINT NOT NULL DEFAULT 0,
			message TEXT NOT NULL DEFAULT '',
			error_msg TEXT NOT NULL DEFAULT '',
			created_at BIGINT NOT NULL DEFAULT 0,
			updated_at BIGINT NOT NULL DEFAULT 0
		);
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
	idInput := fmt.Sprintf("%s:%s:%s:%s:%d", event.Command, event.Stage, event.PositionID, event.TxHash, time.Now().UnixNano())
	id := shadowID("canary-event", idInput, time.Now().UnixNano())
	_, err := w.db.ExecContext(ctx, `
		INSERT INTO canary_events (
			id, command, stage, status, position_id, pool_id, wallet, token_id, tx_hash,
			amount_usd, required_usdc_raw, required_weth_raw, gas_estimate,
			message, error_msg, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
	`,
		id,
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
