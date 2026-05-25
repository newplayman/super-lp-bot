package main

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestLiveSafetyGate_CheckOpenBlocksOnStuckSnapshot(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "gate.sqlite"))
	require.NoError(t, err)

	now := time.Now().UTC()
	_, err = store.DB().Exec(`
		INSERT INTO gate_portfolio_snapshots (
			id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
			open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
			realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
			unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "snap-1", "live", "base", "0x999", "1000000000000000", "300000000000000",
		1, "10", "0", "0", "0", "0", 1, 0, 0, 0, "{}", "[]", now.UnixMilli())
	require.NoError(t, err)

	gate := &liveSafetyGate{
		buildMode:                  "live",
		enabled:                    true,
		allowedChains:              map[string]struct{}{"base": {}},
		allowedPools:               map[string]struct{}{"pool-1": {}},
		maxOrderUSD:                20,
		dailyLossLimitUSD:          100,
		store:                      store,
		snapshotMaxAge:             5 * time.Minute,
		walletAddress:              "0x999",
		sizingPathReady:            true,
		executionBackendConfigured: true,
		executionBackendWired:      true,
		npmBaseConfigured:          true,
	}
	err = gate.checkOpen(domain.Pool{ID: "pool-1", Chain: domain.ChainBase}, domain.MustDecimal("5"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "stuck tx")
}

func TestLiveSafetyGate_CheckOpenBlocksOnProjectedExposureCap(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "gate_cap.sqlite"))
	require.NoError(t, err)

	now := time.Now().UTC()
	_, err = store.DB().Exec(`
		INSERT INTO gate_cap_portfolio_snapshots (
			id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
			open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
			realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
			unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "snap-1", "live", "base", "0x999", "1000000000000000", "300000000000000",
		1, "12", "3", "0", "0", "0", 0, 0, 0, 0, "{}", "[]", now.UnixMilli())
	require.NoError(t, err)

	gate := &liveSafetyGate{
		buildMode:                  "live",
		enabled:                    true,
		allowedChains:              map[string]struct{}{"base": {}},
		allowedPools:               map[string]struct{}{"pool-1": {}},
		maxOrderUSD:                20,
		dailyLossLimitUSD:          15,
		store:                      store,
		snapshotMaxAge:             5 * time.Minute,
		walletAddress:              "0x999",
		sizingPathReady:            true,
		executionBackendConfigured: true,
		executionBackendWired:      true,
		npmBaseConfigured:          true,
	}
	err = gate.checkOpen(domain.Pool{ID: "pool-1", Chain: domain.ChainBase}, domain.MustDecimal("5"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "projected exposure")
}

func TestLiveSafetyGate_CheckOpenAllowsHealthySnapshot(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "gate_ok.sqlite"))
	require.NoError(t, err)

	now := time.Now().UTC()
	_, err = store.DB().Exec(`
		INSERT INTO gate_ok_portfolio_snapshots (
			id, mode, chain, wallet_address, native_balance_wei, gas_reserve_wei,
			open_position_count, open_position_exposure_usd, pending_exposure_usd, submitted_private_exposure_usd,
			realized_pnl_usd, unrealized_pnl_usd, stuck_tx_count, exit_failed_position_count,
			unreconciled_opening_count, unreconciled_opening_timeout_count, balances_json, positions_json, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "snap-1", "live", "base", "0x999", "1000000000000000", "300000000000000",
		1, "5", "0", "0", "0", "0", 0, 0, 0, 0, "{}", "[]", now.UnixMilli())
	require.NoError(t, err)

	gate := &liveSafetyGate{
		buildMode:                  "live",
		enabled:                    true,
		allowedChains:              map[string]struct{}{"base": {}},
		allowedPools:               map[string]struct{}{"pool-1": {}},
		maxOrderUSD:                20,
		dailyLossLimitUSD:          100,
		store:                      store,
		snapshotMaxAge:             5 * time.Minute,
		walletAddress:              "0x999",
		sizingPathReady:            true,
		executionBackendConfigured: true,
		executionBackendWired:      true,
		npmBaseConfigured:          true,
	}
	require.NoError(t, gate.checkOpen(domain.Pool{ID: "pool-1", Chain: domain.ChainBase}, domain.MustDecimal("5")))
}

func TestLoadLatestPortfolioSnapshot_NoRows(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "gate_empty.sqlite"))
	require.NoError(t, err)

	_, ok, err := loadLatestPortfolioSnapshot(context.Background(), store)
	require.NoError(t, err)
	require.False(t, ok)
}
