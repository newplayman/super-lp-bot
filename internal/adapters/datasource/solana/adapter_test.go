package solana_test

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/solana"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestSolanaAdapterInterface verifies the adapter implements ports.Datasource.
func TestSolanaAdapterInterface(t *testing.T) {
	adapter := solana.NewAdapter()
	var _ ports.Datasource = adapter
}

// TestSolanaAdapterHistoricalInterface verifies the adapter implements ports.HistoricalDatasource.
func TestSolanaAdapterHistoricalInterface(t *testing.T) {
	adapter := solana.NewAdapter()
	var _ ports.HistoricalDatasource = adapter
}

// TestSolanaDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestSolanaDiscoverPoolsStub(t *testing.T) {
	adapter := solana.NewAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainSolana, "raydium", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, solana.ErrNotImplemented, err)
}

// TestSolanaGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestSolanaGetPoolMetadataStub(t *testing.T) {
	adapter := solana.NewAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainSolana, "APnKis9...")
	require.Error(t, err)
	require.Equal(t, solana.ErrNotImplemented, err)
}

// TestSolanaGetPriceHistoryStub verifies GetPriceHistory returns not implemented.
func TestSolanaGetPriceHistoryStub(t *testing.T) {
	adapter := solana.NewAdapter()
	_, err := adapter.GetPriceHistory(context.Background(), domain.ChainSolana, "APnKis9...", time.Time{}, time.Now(), time.Hour)
	require.Error(t, err)
	require.Equal(t, solana.ErrNotImplemented, err)
}

// TestSolanaGetPoolStateAtStub verifies GetPoolStateAt returns not implemented.
func TestSolanaGetPoolStateAtStub(t *testing.T) {
	adapter := solana.NewAdapter()
	_, err := adapter.GetPoolStateAt(context.Background(), domain.ChainSolana, "APnKis9...", 1000)
	require.Error(t, err)
	require.Equal(t, solana.ErrNotImplemented, err)
}