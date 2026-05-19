package dexscreener_test

import (
	"net/http"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// TestDexScreenerAdapterImplementsDatasource verifies compile-time interface compliance.
func TestDexScreenerAdapterImplementsDatasource(t *testing.T) {
	var adapter *dexscreener.Adapter
	var _ ports.Datasource = adapter
}

// TestDexScreenerAdapterImplementsHistoricalDatasource verifies compile-time interface compliance.
func TestDexScreenerAdapterImplementsHistoricalDatasource(t *testing.T) {
	var adapter *dexscreener.Adapter
	var _ ports.HistoricalDatasource = adapter
}

// TestDexScreenerNewAdapterWithClient verifies custom HTTP client works.
func TestDexScreenerNewAdapterWithClient(t *testing.T) {
	client := &http.Client{Timeout: 10 * time.Second}
	adapter := dexscreener.NewAdapterWithClient(client)
	require.NotNil(t, adapter)
}

// TestDexScreenerNewAdapter verifies default adapter creation.
func TestDexScreenerNewAdapter(t *testing.T) {
	adapter := dexscreener.NewAdapter()
	require.NotNil(t, adapter)
}