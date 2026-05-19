package geckoterminal_test

import (
	"net/http"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestGeckoTerminalAdapterImplementsDatasource verifies compile-time interface compliance.
func TestGeckoTerminalAdapterImplementsDatasource(t *testing.T) {
	var adapter *geckoterminal.Adapter
	var _ ports.Datasource = adapter
}

// TestGeckoTerminalAdapterImplementsHistoricalDatasource verifies compile-time interface compliance.
func TestGeckoTerminalAdapterImplementsHistoricalDatasource(t *testing.T) {
	var adapter *geckoterminal.Adapter
	var _ ports.HistoricalDatasource = adapter
}

// TestGeckoTerminalNewAdapterWithClient verifies custom HTTP client works.
func TestGeckoTerminalNewAdapterWithClient(t *testing.T) {
	client := &http.Client{Timeout: 10 * time.Second}
	adapter := geckoterminal.NewAdapterWithClient(client)
	require.NotNil(t, adapter)
}

// TestGeckoTerminalNewAdapter verifies default adapter creation.
func TestGeckoTerminalNewAdapter(t *testing.T) {
	adapter := geckoterminal.NewAdapter()
	require.NotNil(t, adapter)
}