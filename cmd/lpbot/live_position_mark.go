package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"go.uber.org/zap"
)

const livePositionMarkInterval = time.Minute

type livePositionMarkService struct {
	app    *App
	tables *runtimeSQLTables
	logger *zap.Logger
}

func newLivePositionMarkService(app *App) (*livePositionMarkService, error) {
	if app == nil || app.store == nil {
		return nil, fmt.Errorf("live position mark service requires store")
	}
	tables, err := newRuntimeSQLTables(app.store)
	if err != nil {
		return nil, err
	}
	return &livePositionMarkService{
		app:    app,
		tables: tables,
		logger: app.logger,
	}, nil
}

func (s *livePositionMarkService) Capture(ctx context.Context, now time.Time) error {
	if s == nil || s.app == nil || s.app.store == nil {
		return fmt.Errorf("live position mark service not configured")
	}
	positions, err := s.app.store.PositionRepo().FindByChainAndStatus(ctx, domain.ChainBase, domain.StatusOpen)
	if err != nil {
		return err
	}
	for _, position := range positions {
		if position == nil || position.TokenID == "" {
			continue
		}
		record, err := s.buildRecord(ctx, position, now)
		if err != nil {
			if s.logger != nil {
				s.logger.Warn("live position mark failed", zap.String("position_id", position.ID), zap.Error(err))
			}
			continue
		}
		if err := s.tables.insertPositionMark(ctx, record); err != nil {
			return err
		}
	}
	return nil
}

func (s *livePositionMarkService) buildRecord(ctx context.Context, position *domain.Position, now time.Time) (positionMarkRecord, error) {
	active := activeShadowPosition{
		ID:        position.ID,
		PoolID:    position.PoolID,
		TokenID:   position.TokenID,
		Chain:     position.Chain,
		Status:    position.Status,
		Tier:      position.Tier,
		AmountUSD: position.AmountUSD,
		TickLower: position.TickLower,
		TickUpper: position.TickUpper,
		OpenedAt:  position.OpenedAt,
		ClosedAt:  position.ClosedAt,
	}
	state, err := s.app.loadNPMPositionState(ctx, active)
	if err != nil {
		return positionMarkRecord{}, err
	}
	positionValueUSD, err := s.app.estimateNPMPositionValueUSD(ctx, active, state)
	if err != nil {
		return positionMarkRecord{}, err
	}
	feeUncollectedUSD, err := s.app.estimateNPMUncollectedFeeUSD(ctx, active, state)
	if err != nil {
		return positionMarkRecord{}, err
	}
	feeCollectedUSD, gasUSD, _, err := s.tables.loadPositionRealizedTotals(ctx, position.ID)
	if err != nil {
		return positionMarkRecord{}, err
	}
	netPnLUSD := positionValueUSD.Add(feeUncollectedUSD).Sub(position.AmountUSD)
	liquidity := "0"
	if state.Liquidity != nil {
		liquidity = state.Liquidity.String()
	}
	metadata, err := json.Marshal(map[string]string{
		"token_id":            position.TokenID,
		"liquidity":           liquidity,
		"fee_collected_usd":   feeCollectedUSD.String(),
		"fee_uncollected_usd": feeUncollectedUSD.String(),
	})
	if err != nil {
		return positionMarkRecord{}, err
	}
	return positionMarkRecord{
		ID:                fmt.Sprintf("live-mark:%s:%d", position.ID, now.Unix()),
		PositionID:        position.ID,
		PoolID:            position.PoolID,
		Chain:             position.Chain,
		TokenID:           position.TokenID,
		Status:            position.Status,
		AmountUSD:         position.AmountUSD,
		PositionValueUSD:  positionValueUSD,
		FeeCollectedUSD:   feeCollectedUSD,
		FeeUncollectedUSD: feeUncollectedUSD,
		GasUSD:            gasUSD,
		ILUSD:             domain.ZeroDecimal(),
		LVRUSD:            domain.ZeroDecimal(),
		NetPnLUSD:         netPnLUSD,
		Source:            "position_mark",
		MetadataJSON:      string(metadata),
		MarkTime:          now.Unix(),
		CreatedAt:         now.UnixMilli(),
	}, nil
}

func (app *App) shouldRunLivePositionMarkLoop() bool {
	return app != nil &&
		app.liveGate != nil &&
		app.liveGate.isExecutionMode() &&
		app.store != nil &&
		app.rpcProviderForChain(domain.ChainBase) != nil
}

func (app *App) runLivePositionMarkLoop(ctx context.Context) {
	service, err := newLivePositionMarkService(app)
	if err != nil {
		if app.logger != nil {
			app.logger.Warn("live position mark service disabled", zap.Error(err))
		}
		return
	}
	ticker := time.NewTicker(livePositionMarkInterval)
	defer ticker.Stop()
	for {
		if err := service.Capture(ctx, time.Now().UTC()); err != nil && ctx.Err() == nil && app.logger != nil {
			app.logger.Warn("live position mark capture failed", zap.Error(err))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
