package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math/big"
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
	entryValueUSD, holdValueUSD, currentPrice0USD, currentPrice1USD, err := s.estimateEntryAndHoldValues(ctx, position, state)
	if err != nil {
		return positionMarkRecord{}, err
	}
	ilUSD, netPnLUSD := computeLivePositionMarkPnL(entryValueUSD, positionValueUSD, feeCollectedUSD, feeUncollectedUSD, gasUSD, holdValueUSD)
	liquidity := "0"
	if state.Liquidity != nil {
		liquidity = state.Liquidity.String()
	}
	metadata, err := json.Marshal(map[string]string{
		"token_id":            position.TokenID,
		"liquidity":           liquidity,
		"entry_value_usd":     entryValueUSD.String(),
		"hold_value_usd":      holdValueUSD.String(),
		"current_token0_usd":  currentPrice0USD.String(),
		"current_token1_usd":  currentPrice1USD.String(),
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
		ILUSD:             ilUSD,
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

func (s *livePositionMarkService) estimateEntryAndHoldValues(ctx context.Context, position *domain.Position, state npmPositionState) (entryValueUSD, holdValueUSD, currentPrice0USD, currentPrice1USD domain.Decimal, err error) {
	entryValueUSD = position.AmountUSD
	metadata := loadPositionMetadata(position.MetadataJSON)
	if value := metadataDecimal(metadata, "entry_value_usd"); value.GreaterThan(domain.ZeroDecimal()) {
		entryValueUSD = value
	}

	rawAmount0 := metadataString(metadata, "actual_amount0")
	rawAmount1 := metadataString(metadata, "actual_amount1")
	if rawAmount0 == "" || rawAmount1 == "" {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), nil
	}

	provider := s.app.rpcProviderForChain(domain.ChainBase)
	if provider == nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), fmt.Errorf("base rpc provider is not configured")
	}
	poolAddress, parseErr := domain.ParseAddress(position.PoolID)
	if parseErr != nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), parseErr
	}
	slot0, readErr := readV3PoolSlot0ForMark(ctx, provider, poolAddress)
	if readErr != nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), readErr
	}
	decimals0, decErr := tokenDecimals(ctx, provider, state.Token0)
	if decErr != nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), decErr
	}
	decimals1, decErr := tokenDecimals(ctx, provider, state.Token1)
	if decErr != nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), decErr
	}
	currentPrice0USD, currentPrice1USD, err = inferBaseTokenPricesUSD(domain.Pool{
		ID:       position.PoolID,
		Chain:    position.Chain,
		Protocol: "uniswap_v3",
		Token0:   state.Token0,
		Token1:   state.Token1,
		FeeBPS:   uint(state.Fee / 100),
		Tick:     slot0.Tick,
	}, decimals0, decimals1)
	if err != nil {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), err
	}

	amount0Raw, ok := new(big.Int).SetString(rawAmount0, 10)
	if !ok {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), fmt.Errorf("invalid actual_amount0 for position %s", position.ID)
	}
	amount1Raw, ok := new(big.Int).SetString(rawAmount1, 10)
	if !ok {
		return entryValueUSD, domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), fmt.Errorf("invalid actual_amount1 for position %s", position.ID)
	}
	amount0 := decimalFromRawAmount(amount0Raw, decimals0)
	amount1 := decimalFromRawAmount(amount1Raw, decimals1)
	holdValueUSD = amount0.Mul(currentPrice0USD).Add(amount1.Mul(currentPrice1USD))
	return entryValueUSD, holdValueUSD, currentPrice0USD, currentPrice1USD, nil
}

func computeLivePositionMarkPnL(entryValueUSD, positionValueUSD, feeCollectedUSD, feeUncollectedUSD, gasUSD, holdValueUSD domain.Decimal) (ilUSD, netPnLUSD domain.Decimal) {
	lpGrossValueUSD := positionValueUSD.Add(feeCollectedUSD).Add(feeUncollectedUSD)
	if holdValueUSD.GreaterThan(domain.ZeroDecimal()) {
		ilUSD = lpGrossValueUSD.Sub(holdValueUSD)
	}
	netPnLUSD = lpGrossValueUSD.Sub(entryValueUSD).Sub(gasUSD)
	return ilUSD, netPnLUSD
}
