// Package health provides Kubernetes-compatible health check endpoints for lp-bot.
package health

import (
	"fmt"
	"net/http"
	"strings"
)

// Dependencies holds the health check dependencies for the readiness probe.
// All fields must be true for the service to be considered ready.
type Dependencies struct {
	// DBHealthy indicates the database connection is healthy.
	DBHealthy bool
	// BusHealthy indicates the message bus is healthy.
	BusHealthy bool
	// ChainHealthy indicates all chain adapters are connected.
	ChainHealthy bool
	// BootstrapDone indicates the bootstrap process has completed.
	BootstrapDone bool
}

// LivenessHandler handles the /healthz liveness probe.
// It always returns 200 OK, indicating the process is alive.
// This is used by Kubernetes/supervisor to know when to restart the process.
func LivenessHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

// ReadinessHandler handles the /readyz readiness probe.
// It checks all dependencies and returns 200 if all are healthy,
// or 503 Service Unavailable if any dependency is unhealthy.
func ReadinessHandler(w http.ResponseWriter, r *http.Request, deps *Dependencies) {
	w.Header().Set("Content-Type", "text/plain")

	var failures []string

	if deps == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte("dependencies not configured"))
		return
	}

	if !deps.BootstrapDone {
		failures = append(failures, "bootstrap not done")
	}
	if !deps.ChainHealthy {
		failures = append(failures, "chain unhealthy")
	}
	if !deps.BusHealthy {
		failures = append(failures, "bus unhealthy")
	}
	if !deps.DBHealthy {
		failures = append(failures, "db unhealthy")
	}

	if len(failures) > 0 {
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte(fmt.Sprintf("not ready: %s", strings.Join(failures, ", "))))
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}