package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

const portfolioSnapshotInterval = time.Minute

type portfolioBalanceSource interface {
	BalanceAt(ctx context.Context, account domain.Address, blockNumber *big.Int) (*big.Int, error)
}

type portfolioSnapshotRecord struct {
	ID                          string
	Mode                        string
	Chain                       domain.ChainID
	WalletAddress               string
	NativeBalanceWei            string
	GasReserveWei               string
	OpenPositionCount           int
	OpenPositionExposureUSD     string
	PendingExposureUSD          string
	SubmittedPrivateExposureUSD string
	RealizedPnLUSD              string
	UnrealizedPnLUSD            string
	BalancesJSON                string
	PositionsJSON               string
	CreatedAt                   int64
}

type portfolioSnapshotService struct {
	mode     string
	store    ports.Store
	provider portfolioBalanceSource
	wallet   domain.Address
	db       *sql.DB
	dialect  string
	table    string
	logger   *zap.Logger
}

func newPortfolioSnapshotService(app *App) (*portfolioSnapshotService, error) {
	if app == nil || app.store == nil || app.config == nil {
		return nil, fmt.Errorf("portfolio snapshot requires app store and config")
	}
	dbHolder, ok := any(app.store).(interface{ DB() *sql.DB })
	if !ok || dbHolder.DB() == nil {
		return nil, fmt.Errorf("portfolio snapshot requires store DB access")
	}
	table := "portfolio_snapshots"
	dialect := "postgres"
	if prefixed, ok := any(app.store).(interface{ Prefix() string }); ok {
		table = prefixed.Prefix() + "_portfolio_snapshots"
		dialect = "sqlite"
	}
	return &portfolioSnapshotService{
		mode:     strings.TrimSpace(BuildMode),
		store:    app.store,
		provider: app.rpc["base"],
		wallet:   parseAddressOrZero(strings.TrimSpace(app.config.Live.WalletAddress)),
		db:       dbHolder.DB(),
		dialect:  dialect,
		table:    table,
		logger:   app.logger,
	}, nil
}

func (s *portfolioSnapshotService) Capture(ctx context.Context, now time.Time) error {
	if s == nil || s.store == nil || s.db == nil {
		return fmt.Errorf("portfolio snapshot service not configured")
	}
	record, err := s.buildRecord(ctx, now)
	if err != nil {
		return err
	}
	return s.insertRecord(ctx, record)
}

func (s *portfolioSnapshotService) buildRecord(ctx context.Context, now time.Time) (portfolioSnapshotRecord, error) {
	nativeBalance := big.NewInt(0)
	if s.provider != nil && !s.wallet.IsZero() {
		balance, err := s.provider.BalanceAt(ctx, s.wallet, nil)
		if err != nil {
			return portfolioSnapshotRecord{}, err
		}
		nativeBalance = balance
	}

	openPositions, err := s.store.PositionRepo().FindByChainAndStatus(ctx, domain.ChainBase, domain.StatusOpen)
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}
	openingPositions, err := s.store.PositionRepo().FindByChainAndStatus(ctx, domain.ChainBase, domain.StatusOpening)
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}
	exitingPositions, err := s.store.PositionRepo().FindByChainAndStatus(ctx, domain.ChainBase, domain.StatusExiting)
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}

	openExposure := sumPositionExposure(openPositions)
	pendingExposure := sumPositionExposure(openingPositions).Add(sumPositionExposure(exitingPositions))
	submittedPrivateExposure := domain.ZeroDecimal()
	for _, position := range openingPositions {
		if strings.TrimSpace(position.OpenTxHash) == "" {
			continue
		}
		tx, err := s.store.TxRepo().GetTxByHash(ctx, domain.ChainBase, position.OpenTxHash)
		if err != nil {
			continue
		}
		if tx.Status == domain.TxSubmittedPrivate {
			submittedPrivateExposure = submittedPrivateExposure.Add(position.AmountUSD)
		}
	}

	positionsJSON, err := marshalPortfolioPositions(append(append(openPositions, openingPositions...), exitingPositions...))
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}
	balancesJSON, err := marshalPortfolioBalances(s.wallet, nativeBalance)
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}

	return portfolioSnapshotRecord{
		ID:                          "portfolio-" + shortHash(fmt.Sprintf("%s:%s:%d", s.mode, s.wallet.String(), now.UnixMilli())),
		Mode:                        s.mode,
		Chain:                       domain.ChainBase,
		WalletAddress:               s.wallet.String(),
		NativeBalanceWei:            nativeBalance.String(),
		GasReserveWei:               nativeBalance.String(),
		OpenPositionCount:           len(openPositions),
		OpenPositionExposureUSD:     openExposure.String(),
		PendingExposureUSD:          pendingExposure.String(),
		SubmittedPrivateExposureUSD: submittedPrivateExposure.String(),
		RealizedPnLUSD:              domain.ZeroDecimal().String(),
		UnrealizedPnLUSD:            domain.ZeroDecimal().String(),
		BalancesJSON:                balancesJSON,
		PositionsJSON:               positionsJSON,
		CreatedAt:                   now.UnixMilli(),
	}, nil
}

func (s *portfolioSnapshotService) insertRecord(ctx context.Context, record portfolioSnapshotRecord) error {
	switch s.dialect {
	case "sqlite":
		_, err := s.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
				open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
				realized_pnl_usd, unrealized_pnl_usd, balances_json, positions_json, created_at
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`, s.table),
			record.ID, record.Mode, string(record.Chain), record.WalletAddress, record.NativeBalanceWei, record.GasReserveWei,
			record.OpenPositionCount, record.OpenPositionExposureUSD, record.PendingExposureUSD, record.SubmittedPrivateExposureUSD,
			record.RealizedPnLUSD, record.UnrealizedPnLUSD, record.BalancesJSON, record.PositionsJSON, record.CreatedAt,
		)
		return err
	default:
		_, err := s.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
				open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
				realized_pnl_usd, unrealized_pnl_usd, balances_json, positions_json, created_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb, $15)
		`, s.table),
			record.ID, record.Mode, string(record.Chain), record.WalletAddress, record.NativeBalanceWei, record.GasReserveWei,
			record.OpenPositionCount, record.OpenPositionExposureUSD, record.PendingExposureUSD, record.SubmittedPrivateExposureUSD,
			record.RealizedPnLUSD, record.UnrealizedPnLUSD, record.BalancesJSON, record.PositionsJSON, record.CreatedAt,
		)
		return err
	}
}

func (app *App) shouldRunPortfolioSnapshotLoop() bool {
	return app != nil &&
		app.liveGate != nil &&
		app.liveGate.isExecutionMode() &&
		app.store != nil
}

func (app *App) runPortfolioSnapshotLoop(ctx context.Context) {
	service, err := newPortfolioSnapshotService(app)
	if err != nil {
		if app.logger != nil {
			app.logger.Warn("portfolio snapshot service disabled", zap.Error(err))
		}
		return
	}
	ticker := time.NewTicker(portfolioSnapshotInterval)
	defer ticker.Stop()
	for {
		if err := service.Capture(ctx, time.Now().UTC()); err != nil && ctx.Err() == nil && app.logger != nil {
			app.logger.Warn("portfolio snapshot capture failed", zap.Error(err))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func sumPositionExposure(positions []*domain.Position) domain.Decimal {
	total := domain.ZeroDecimal()
	for _, position := range positions {
		if position == nil {
			continue
		}
		total = total.Add(position.AmountUSD)
	}
	return total
}

func marshalPortfolioBalances(wallet domain.Address, nativeBalance *big.Int) (string, error) {
	payload := map[string]string{
		"wallet":             wallet.String(),
		"native_balance_wei": nativeBalance.String(),
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func marshalPortfolioPositions(positions []*domain.Position) (string, error) {
	type item struct {
		ID         string `json:"id"`
		PoolID     string `json:"pool_id"`
		Status     string `json:"status"`
		AmountUSD  string `json:"amount_usd"`
		TokenID    string `json:"token_id,omitempty"`
		OpenTxHash string `json:"open_tx_hash,omitempty"`
	}
	out := make([]item, 0, len(positions))
	for _, position := range positions {
		if position == nil {
			continue
		}
		out = append(out, item{
			ID:         position.ID,
			PoolID:     position.PoolID,
			Status:     string(position.Status),
			AmountUSD:  position.AmountUSD.String(),
			TokenID:    position.TokenID,
			OpenTxHash: position.OpenTxHash,
		})
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}
