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
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

const portfolioSnapshotInterval = time.Minute

type portfolioBalanceSource interface {
	BalanceAt(ctx context.Context, account domain.Address, blockNumber *big.Int) (*big.Int, error)
}

type portfolioGasPriceSource interface {
	SuggestGasPrice(ctx context.Context) (*big.Int, error)
}

type portfolioSnapshotRecord struct {
	ID                              string
	Mode                            string
	Chain                           domain.ChainID
	WalletAddress                   string
	NativeBalanceWei                string
	GasReserveWei                   string
	OpenPositionCount               int
	OpenPositionExposureUSD         string
	PendingExposureUSD              string
	SubmittedPrivateExposureUSD     string
	RealizedPnLUSD                  string
	UnrealizedPnLUSD                string
	StuckTxCount                    int
	ExitFailedPositionCount         int
	UnreconciledOpeningCount        int
	UnreconciledOpeningTimeoutCount int
	BalancesJSON                    string
	PositionsJSON                   string
	CreatedAt                       int64
}

type portfolioSnapshotService struct {
	mode     string
	store    ports.Store
	provider portfolioBalanceSource
	wallet   domain.Address
	config   *config.Config
	db       *sql.DB
	dialect  string
	table    string
	tables   *runtimeSQLTables
	logger   *zap.Logger
}

func newPortfolioSnapshotService(app *App) (*portfolioSnapshotService, error) {
	if app == nil || app.store == nil || app.config == nil {
		return nil, fmt.Errorf("portfolio snapshot requires app store and config")
	}
	tables, err := newRuntimeSQLTables(app.store)
	if err != nil {
		return nil, err
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
		config:   app.config,
		db:       dbHolder.DB(),
		dialect:  dialect,
		table:    table,
		tables:   tables,
		logger:   app.logger,
	}, nil
}

func (s *portfolioSnapshotService) Capture(ctx context.Context, now time.Time) error {
	if s == nil || s.store == nil || s.db == nil {
		return fmt.Errorf("portfolio snapshot service not configured")
	}
	if s.tables == nil {
		tables, err := newRuntimeSQLTables(s.store)
		if err != nil {
			return err
		}
		s.tables = tables
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
	gasReserveWei := estimatePortfolioGasReserveWei(ctx, s.provider)
	if configured := configuredMinGasReserveWei(s.config); configured.Sign() > 0 && gasReserveWei.Cmp(configured) < 0 {
		gasReserveWei = configured
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
	exitFailedPositions, err := s.store.PositionRepo().FindByChainAndStatus(ctx, domain.ChainBase, domain.StatusExitFailed)
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

	realizedPnL := domain.ZeroDecimal()
	if s.tables != nil {
		if total, err := s.tables.sumRealizedPnL(ctx); err == nil {
			realizedPnL = total
		}
	}
	unrealizedPnL := domain.ZeroDecimal()
	if s.tables != nil {
		for _, position := range openPositions {
			if position == nil {
				continue
			}
			mark, ok, err := s.tables.loadLatestPositionMark(ctx, position.ID)
			if err != nil || !ok {
				continue
			}
			unrealizedPnL = unrealizedPnL.Add(mark.NetPnLUSD)
		}
	}

	stuckTxCount, err := countTxsByStatus(ctx, s.store, domain.ChainBase, domain.TxStuck)
	if err != nil {
		return portfolioSnapshotRecord{}, err
	}
	openingTimeoutCount := 0
	openingTimeoutSeconds := int64(180)
	if s.config != nil {
		openingTimeoutSeconds = int64(positiveOrDefault(s.config.LiveRisk.MaxUnreconciledOpeningAgeSeconds, 180))
	}
	for _, position := range openingPositions {
		if position == nil {
			continue
		}
		if position.OpenedAt > 0 && now.Unix()-position.OpenedAt >= openingTimeoutSeconds {
			openingTimeoutCount++
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
		ID:                              "portfolio-" + shortHash(fmt.Sprintf("%s:%s:%d", s.mode, s.wallet.String(), now.UnixMilli())),
		Mode:                            s.mode,
		Chain:                           domain.ChainBase,
		WalletAddress:                   s.wallet.String(),
		NativeBalanceWei:                nativeBalance.String(),
		GasReserveWei:                   gasReserveWei.String(),
		OpenPositionCount:               len(openPositions),
		OpenPositionExposureUSD:         openExposure.String(),
		PendingExposureUSD:              pendingExposure.String(),
		SubmittedPrivateExposureUSD:     submittedPrivateExposure.String(),
		RealizedPnLUSD:                  realizedPnL.String(),
		UnrealizedPnLUSD:                unrealizedPnL.String(),
		StuckTxCount:                    stuckTxCount,
		ExitFailedPositionCount:         len(exitFailedPositions),
		UnreconciledOpeningCount:        len(openingPositions),
		UnreconciledOpeningTimeoutCount: openingTimeoutCount,
		BalancesJSON:                    balancesJSON,
		PositionsJSON:                   positionsJSON,
		CreatedAt:                       now.UnixMilli(),
	}, nil
}

func (s *portfolioSnapshotService) insertRecord(ctx context.Context, record portfolioSnapshotRecord) error {
	switch s.dialect {
	case "sqlite":
		_, err := s.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
				open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
				realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
				unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`, s.table),
			record.ID, record.Mode, string(record.Chain), record.WalletAddress, record.NativeBalanceWei, record.GasReserveWei,
			record.OpenPositionCount, record.OpenPositionExposureUSD, record.PendingExposureUSD, record.SubmittedPrivateExposureUSD,
			record.RealizedPnLUSD, record.UnrealizedPnLUSD, record.StuckTxCount, record.ExitFailedPositionCount,
			record.UnreconciledOpeningCount, record.UnreconciledOpeningTimeoutCount, record.BalancesJSON, record.PositionsJSON, record.CreatedAt,
		)
		return err
	default:
		_, err := s.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
				open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
				realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
				unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17::jsonb, $18::jsonb, $19)
		`, s.table),
			record.ID, record.Mode, string(record.Chain), record.WalletAddress, record.NativeBalanceWei, record.GasReserveWei,
			record.OpenPositionCount, record.OpenPositionExposureUSD, record.PendingExposureUSD, record.SubmittedPrivateExposureUSD,
			record.RealizedPnLUSD, record.UnrealizedPnLUSD, record.StuckTxCount, record.ExitFailedPositionCount,
			record.UnreconciledOpeningCount, record.UnreconciledOpeningTimeoutCount, record.BalancesJSON, record.PositionsJSON, record.CreatedAt,
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

func estimatePortfolioGasReserveWei(ctx context.Context, provider portfolioBalanceSource) *big.Int {
	minimum := new(big.Int).Mul(big.NewInt(300000), big.NewInt(1_000_000_000))
	if provider == nil {
		return minimum
	}
	gasPricer, ok := provider.(portfolioGasPriceSource)
	if !ok {
		return minimum
	}
	gasPrice, err := gasPricer.SuggestGasPrice(ctx)
	if err != nil || gasPrice == nil || gasPrice.Sign() <= 0 {
		return minimum
	}
	estimatedUnits := big.NewInt(600000)
	buffered := new(big.Int).Mul(gasPrice, estimatedUnits)
	buffered.Mul(buffered, big.NewInt(2))
	if buffered.Cmp(minimum) < 0 {
		return minimum
	}
	return buffered
}

func configuredMinGasReserveWei(cfg *config.Config) *big.Int {
	if cfg == nil {
		return big.NewInt(0)
	}
	value := strings.TrimSpace(cfg.LiveRisk.MinGasReserveWei)
	if value == "" {
		return big.NewInt(0)
	}
	out, ok := new(big.Int).SetString(value, 10)
	if !ok || out.Sign() < 0 {
		return big.NewInt(0)
	}
	return out
}

func countTxsByStatus(ctx context.Context, store ports.Store, chain domain.ChainID, status domain.TxStatus) (int, error) {
	if store == nil {
		return 0, nil
	}
	txs, err := store.TxRepo().ListTxsByStatus(ctx, chain, status)
	if err != nil {
		return 0, err
	}
	return len(txs), nil
}

func loadLatestPortfolioSnapshot(ctx context.Context, store ports.Store) (portfolioSnapshotRecord, bool, error) {
	tables, err := newRuntimeSQLTables(store)
	if err != nil {
		return portfolioSnapshotRecord{}, false, err
	}
	query := fmt.Sprintf(`
		SELECT id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
		       open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
		       realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
		       unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
		FROM %s
		ORDER BY created_at DESC
		LIMIT 1
	`, tables.portfolioSnapshotTable)
	row := portfolioSnapshotRecord{}
	var chain string
	err = tables.db.QueryRowContext(ctx, query).Scan(
		&row.ID, &row.Mode, &chain, &row.WalletAddress, &row.NativeBalanceWei, &row.GasReserveWei,
		&row.OpenPositionCount, &row.OpenPositionExposureUSD, &row.PendingExposureUSD, &row.SubmittedPrivateExposureUSD,
		&row.RealizedPnLUSD, &row.UnrealizedPnLUSD, &row.StuckTxCount, &row.ExitFailedPositionCount,
		&row.UnreconciledOpeningCount, &row.UnreconciledOpeningTimeoutCount, &row.BalancesJSON, &row.PositionsJSON, &row.CreatedAt,
	)
	if err == sql.ErrNoRows {
		return portfolioSnapshotRecord{}, false, nil
	}
	if err != nil {
		return portfolioSnapshotRecord{}, false, err
	}
	row.Chain = domain.ChainID(chain)
	return row, true, nil
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
