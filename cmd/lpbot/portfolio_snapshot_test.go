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

func TestPortfolioSnapshotService_CaptureIncludesPnLFromMarksAndLedger(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "portfolio_pnl.sqlite"))
	require.NoError(t, err)

	ctx := context.Background()
	openPos := &domain.Position{
		ID:           "pos-open-pnl",
		PoolID:       "pool-open-pnl",
		Chain:        domain.ChainBase,
		Status:       domain.StatusOpen,
		AmountUSD:    domain.MustDecimal("20"),
		MetadataJSON: "{}",
		OpenedAt:     time.Now().Add(-2 * time.Hour).Unix(),
	}
	require.NoError(t, store.PositionRepo().Save(ctx, openPos))
	for _, alter := range []string{
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN chain TEXT NOT NULL DEFAULT 'base'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN block_number INTEGER NOT NULL DEFAULT 0`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN block_hash TEXT`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN block_time INTEGER NOT NULL DEFAULT 0`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN tx_hash TEXT`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN pool_id TEXT NOT NULL DEFAULT ''`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN kind TEXT NOT NULL DEFAULT ''`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN amount TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN token_symbol TEXT NOT NULL DEFAULT 'USD'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN source TEXT NOT NULL DEFAULT ''`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN position_value_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN fee_collected_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN fee_uncollected_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN gas_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN il_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN lvr_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN net_pnl_usd TEXT NOT NULL DEFAULT '0'`,
		`ALTER TABLE portfolio_pnl_pnl_ledger ADD COLUMN trace_id TEXT`,
	} {
		_, _ = store.DB().Exec(alter)
	}

	_, err = store.DB().Exec(`
		INSERT INTO portfolio_pnl_position_marks (
			id, position_id, pool_id, chain, token_id, status, amount_usd, position_value_usd,
			fee_collected_usd, fee_uncollected_usd, gas_usd, il_usd, lvr_usd, net_pnl_usd,
			source, metadata_json, mark_time, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "mark-1", "pos-open-pnl", "pool-open-pnl", "base", "123", "open", "20", "27",
		"0", "0", "0", "0", "0", "7", "position_mark", "{}", 1700000000, 1700000000)
	require.NoError(t, err)
	_, err = store.DB().Exec(`
		INSERT INTO portfolio_pnl_pnl_ledger (
			id, position_id, pool_id, kind, amount, token_symbol, chain, block_number, block_hash, block_time,
			tx_hash, source, position_value_usd, fee_collected_usd, fee_uncollected_usd, gas_usd,
			il_usd, lvr_usd, net_pnl_usd, trace_id
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "ledger-1", "pos-open-pnl", "pool-open-pnl", "settle", "2", "USD", "base", 1, "", 1700000000,
		"0xabc", "base_settle", "0", "2", "0", "0", "0", "0", "2", "test")
	require.NoError(t, err)

	service := &portfolioSnapshotService{
		mode:     "live",
		store:    store,
		provider: fakePortfolioBalanceSource{balance: big.NewInt(42)},
		wallet:   domain.MustParseAddress("0x9999999999999999999999999999999999999999"),
		db:       store.DB(),
		dialect:  "sqlite",
		table:    store.Prefix() + "_portfolio_snapshots",
	}

	now := time.Unix(1700000100, 0).UTC()
	require.NoError(t, service.Capture(ctx, now))

	row := store.DB().QueryRow(`SELECT realized_pnl_usd, unrealized_pnl_usd
		FROM portfolio_pnl_portfolio_snapshots ORDER BY created_at DESC LIMIT 1`)

	var realizedPnL, unrealizedPnL string
	require.NoError(t, row.Scan(&realizedPnL, &unrealizedPnL))
	require.Equal(t, "2", realizedPnL)
	require.Equal(t, "7", unrealizedPnL)
}
