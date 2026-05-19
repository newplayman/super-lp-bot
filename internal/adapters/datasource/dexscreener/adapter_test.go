package dexscreener_test

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestDexScreenerAdapterInterface verifies the adapter implements ports.Datasource.
func TestDexScreenerAdapterInterface(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	var _ ports.Datasource = adapter
}

// TestDexScreenerAdapterHistoricalInterface verifies the adapter implements ports.HistoricalDatasource.
func TestDexScreenerAdapterHistoricalInterface(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	var _ ports.HistoricalDatasource = adapter
}

// TestDexScreenerDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestDexScreenerDiscoverPoolsStub(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestDexScreenerGetPoolMetadataStub(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerHealthCheckStub verifies HealthCheck returns not implemented.
func TestDexScreenerHealthCheckStub(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	err := adapter.HealthCheck(context.Background())
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerGetPriceHistoryStub verifies GetPriceHistory returns not implemented.
func TestDexScreenerGetPriceHistoryStub(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	_, err := adapter.GetPriceHistory(context.Background(), domain.ChainBase, "0x123", time.Time{}, time.Now(), time.Hour)
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerGetPoolStateAtStub verifies GetPoolStateAt returns not implemented.
func TestDexScreenerGetPoolStateAtStub(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	_, err := adapter.GetPoolStateAt(context.Background(), domain.ChainBase, "0x123", 1000)
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}