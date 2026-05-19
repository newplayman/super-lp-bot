package geckoterminal_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestGeckoTerminalAdapterInterface verifies the adapter implements ports.Datasource.
func TestGeckoTerminalAdapterInterface(t *testing.T) {
	adapter := geckoterminal.NewGeckoTerminalAdapter()
	var _ ports.Datasource = adapter
}

// TestGeckoTerminalDiscoverPoolsStub verifies DiscoverPools returns not implemented.
func TestGeckoTerminalDiscoverPoolsStub(t *testing.T) {
	adapter := geckoterminal.NewGeckoTerminalAdapter()
	_, err := adapter.DiscoverPools(context.Background(), domain.ChainBase, "uniswap_v3", domain.Decimal{}, 10)
	require.Error(t, err)
	require.Equal(t, geckoterminal.ErrNotImplemented, err)
}

// TestGeckoTerminalGetPoolMetadataStub verifies GetPoolMetadata returns not implemented.
func TestGeckoTerminalGetPoolMetadataStub(t *testing.T) {
	adapter := geckoterminal.NewGeckoTerminalAdapter()
	_, err := adapter.GetPoolMetadata(context.Background(), domain.ChainBase, "0x123")
	require.Error(t, err)
	require.Equal(t, geckoterminal.ErrNotImplemented, err)
}

// TestGeckoTerminalHealthCheckStub verifies HealthCheck returns not implemented.
func TestGeckoTerminalHealthCheckStub(t *testing.T) {
	adapter := geckoterminal.NewGeckoTerminalAdapter()
	err := adapter.HealthCheck(context.Background())
	require.Error(t, err)
	require.Equal(t, geckoterminal.ErrNotImplemented, err)
}