package health_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lpbot/lpbot/internal/platform/health"
	"github.com/stretchr/testify/require"
)

// TestLivenessHandlerAlwaysReturnsOK verifies /healthz returns 200 always
func TestLivenessHandlerAlwaysReturnsOK(t *testing.T) {
	handler := http.HandlerFunc(health.LivenessHandler)

	// Should always return 200 regardless of context
	tests := []struct {
		name    string
		method  string
		path    string
	}{
		{"GET request", "GET", "/healthz"},
		{"POST request", "POST", "/healthz"},
		{"with empty context", "", "/healthz"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, tt.path, nil)
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)

			require.Equal(t, http.StatusOK, rec.Code, "liveness should always return 200")
			require.Equal(t, "OK", rec.Body.String(), "body should be OK")
		})
	}
}

// TestReadinessHandlerSuccess verifies /readyz returns 200 when all checks pass
func TestReadinessHandlerSuccess(t *testing.T) {
	// Setup dependencies that all succeed
	deps := &health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    true,
		ChainHealthy:  true,
		BootstrapDone: true,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code, "readiness should return 200 when all deps healthy")
	require.Equal(t, "OK", rec.Body.String(), "body should be OK")
}

// TestReadinessHandlerDBFailure verifies /readyz returns 503 when DB is unhealthy
func TestReadinessHandlerDBFailure(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     false,
		BusHealthy:    true,
		ChainHealthy:  true,
		BootstrapDone: true,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code, "readiness should return 503 when DB unhealthy")
	require.Contains(t, rec.Body.String(), "db", "body should indicate db failure")
}

// TestReadinessHandlerBusFailure verifies /readyz returns 503 when bus is unhealthy
func TestReadinessHandlerBusFailure(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    false,
		ChainHealthy:  true,
		BootstrapDone: true,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code, "readiness should return 503 when bus unhealthy")
	require.Contains(t, rec.Body.String(), "bus", "body should indicate bus failure")
}

// TestReadinessHandlerChainFailure verifies /readyz returns 503 when chain is unhealthy
func TestReadinessHandlerChainFailure(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    true,
		ChainHealthy:  false,
		BootstrapDone: true,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code, "readiness should return 503 when chain unhealthy")
	require.Contains(t, rec.Body.String(), "chain", "body should indicate chain failure")
}

// TestReadinessHandlerBootstrapNotDone verifies /readyz returns 503 when bootstrap not done
func TestReadinessHandlerBootstrapNotDone(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    true,
		ChainHealthy:  true,
		BootstrapDone: false,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code, "readiness should return 503 when bootstrap not done")
	require.Contains(t, rec.Body.String(), "bootstrap", "body should indicate bootstrap not done")
}

// TestReadinessHandlerMultipleFailures verifies /readyz reports all failures
func TestReadinessHandlerMultipleFailures(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     false,
		BusHealthy:    false,
		ChainHealthy:  true,
		BootstrapDone: false,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code)
	require.Contains(t, rec.Body.String(), "db")
	require.Contains(t, rec.Body.String(), "bus")
	require.Contains(t, rec.Body.String(), "bootstrap")
}

// TestLivenessHandlerNoDepContext verifies liveness doesn't need dependency context
func TestLivenessHandlerNoDepContext(t *testing.T) {
	handler := http.HandlerFunc(health.LivenessHandler)

	// Liveness should work without any dependency checks
	req := httptest.NewRequest("GET", "/healthz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
}

// TestReadinessHandlerWithContext verifies context is accepted but not used for basic checks
func TestReadinessHandlerWithContext(t *testing.T) {
	deps := &health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    true,
		ChainHealthy:  true,
		BootstrapDone: true,
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		health.ReadinessHandler(w, r, deps)
	})

	// Should work with a valid context
	ctx := context.Background()
	req := httptest.NewRequest("GET", "/readyz", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
}

// TestDependenciesStruct verifies Dependencies struct fields
func TestDependenciesStruct(t *testing.T) {
	deps := health.Dependencies{
		DBHealthy:     true,
		BusHealthy:    true,
		ChainHealthy:  true,
		BootstrapDone: true,
	}

	require.True(t, deps.DBHealthy)
	require.True(t, deps.BusHealthy)
	require.True(t, deps.ChainHealthy)
	require.True(t, deps.BootstrapDone)
}