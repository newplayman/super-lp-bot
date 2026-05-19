package dexscreener_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestDexScreenerAdapterInterface verifies the adapter implements ports.Datasource.
func TestDexScreenerAdapterInterface(t *testing.T) {
	adapter := dexscreener.NewDexScreenerAdapter()
	var _ ports.Datasource = adapter
}

// TestDexScreenerDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestDexScreenerDiscoverPoolsStub(t *testing.T) {
	adapter := dexscreener.NewDexScreenerAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestDexScreenerGetPoolMetadataStub(t *testing.T) {
	adapter := dexscreener.NewDexScreenerAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}

// TestDexScreenerHealthCheckStub verifies HealthCheck returns not implemented.
func TestDexScreenerHealthCheckStub(t *testing.T) {
	adapter := dexscreener.NewDexScreenerAdapter()
	err := adapter.HealthCheck(context.Background())
	require.Error(t, err)
	require.Equal(t, dexscreener.ErrNotImplemented, err)
}