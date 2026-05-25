package main

import (
	"context"
	"encoding/json"
	"math/big"
	"path/filepath"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

type fakePortfolioBalanceSource struct {
	balance *big.Int
}

func (f fakePortfolioBalanceSource) BalanceAt(context.Context, domain.Address, *big.Int) (*big.Int, error) {
	return new(big.Int).Set(f.balance), nil
}

func TestPortfolioSnapshotService_CaptureWritesSnapshot(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "portfolio.sqlite"))
	require.NoError(t, err)

	ctx := context.Background()
	openPos := &domain.Position{
		ID:           "pos-open",
		PoolID:       "pool-open",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpen,
		AmountUSD:    domain.MustDecimal("15"),
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Add(-time.Hour).Unix(),
	}
	openingPos := &domain.Position{
		ID:           "pos-opening",
		PoolID:       "pool-opening",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpening,
		AmountUSD:    domain.MustDecimal("5"),
		OpenTxHash:   "0x123",
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Add(-time.Minute).Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, openPos))
	require.NoError(t, store.PositionRepo().Save(ctx, openingPos))
	require.NoError(t, store.TxRepo().UpsertTx(ctx, domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:    "tx-123",
			Chain: domain.ChainBase,
			From:  zeroEVMAddress(),
			To:    zeroEVMAddress(),
		},
		Hash:   "0x123",
		Status: domain.TxSubmittedPrivate,
	}))

	service := &portfolioSnapshotService{
		mode:     "live",
		store:    store,
		provider: fakePortfolioBalanceSource{balance: big.NewInt(42)},
		wallet:   domain.MustParseAddress("0x9999999999999999999999999999999999999999"),
		db:       store.DB(),
		dialect:  "sqlite",
		table:    store.Prefix() + "_portfolio_snapshots",
	}

	now := time.Unix(1700000000, 0).UTC()
	require.NoError(t, service.Capture(ctx, now))

	row := store.DB().QueryRow(`SELECT native_balance_wei, open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd, balances_json, positions_json
		FROM portfolio_portfolio_snapshots ORDER BY created_at DESC LIMIT 1`)

	var nativeBalance, openExposure, pendingExposure, submittedPrivateExposure, balancesJSON, positionsJSON string
	var openCount int
	require.NoError(t, row.Scan(&nativeBalance, &openCount, &openExposure, &pendingExposure, &submittedPrivateExposure, &balancesJSON, &positionsJSON))
	require.Equal(t, "42", nativeBalance)
	require.Equal(t, 1, openCount)
	require.Equal(t, "15", openExposure)
	require.Equal(t, "5", pendingExposure)
	require.Equal(t, "5", submittedPrivateExposure)

	var balances map[string]string
	require.NoError(t, json.Unmarshal([]byte(balancesJSON), &balances))
	require.Equal(t, "42", balances["native_balance_wei"])

	var positions []map[string]any
	require.NoError(t, json.Unmarshal([]byte(positionsJSON), &positions))
	require.Len(t, positions, 2)
}
