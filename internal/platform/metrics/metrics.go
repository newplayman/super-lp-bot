// Package metrics provides Prometheus metrics wrappers for lp-bot.
package metrics

import (
	"errors"
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// errMetricAlreadyRegistered is returned when a metric with the same name
// is already registered in the default registry.
var errMetricAlreadyRegistered = errors.New("metric already registered")

// defaultRegistry is the default Prometheus registry used by this package.
var defaultRegistry = prometheus.NewRegistry()

// GetRegistry returns the default Prometheus registry.
func GetRegistry() *prometheus.Registry {
	return defaultRegistry
}

// Counter creates and registers a new Prometheus Counter with the given name and help text.
// If a metric with the same name already exists, returns the existing counter (idempotent).
// Returns the registered counter for recording values.
func Counter(name, help string) prometheus.Counter {
	counter := prometheus.NewCounter(prometheus.CounterOpts{
		Name: name,
		Help: help,
	})
	if err := defaultRegistry.Register(counter); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(prometheus.Counter)
		}
	}
	return counter
}

// Gauge creates and registers a new Prometheus Gauge with the given name and help text.
// If a metric with the same name already exists, returns the existing gauge (idempotent).
// Returns the registered gauge for recording values.
func Gauge(name, help string) prometheus.Gauge {
	gauge := prometheus.NewGauge(prometheus.GaugeOpts{
		Name: name,
		Help: help,
	})
	if err := defaultRegistry.Register(gauge); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(prometheus.Gauge)
		}
	}
	return gauge
}

// Histogram creates and registers a new Prometheus Histogram with the given name, help text,
// and bucket boundaries. If a metric with the same name already exists, returns the existing
// histogram (idempotent). Returns the registered histogram for recording observations.
func Histogram(name, help string, buckets []float64) prometheus.Histogram {
	histogram := prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    name,
		Help:    help,
		Buckets: buckets,
	})
	if err := defaultRegistry.Register(histogram); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(prometheus.Histogram)
		}
	}
	return histogram
}

// Handler returns an HTTP handler for the /metrics endpoint that exposes
// all registered metrics in Prometheus format.
func Handler(w http.ResponseWriter, r *http.Request) {
	h := promhttp.HandlerFor(defaultRegistry, promhttp.HandlerOpts{})
	h.ServeHTTP(w, r)
}
