// Package metrics provides Prometheus metrics wrappers for lp-bot.
package metrics

import (
	"errors"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/shopspring/decimal"
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

// Standard metric bucket definitions
var (
	// latencyBuckets for RPC request durations
	LatencyBuckets = []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10}

	// sizeBuckets for data sizes
	SizeBuckets = []float64{100, 500, 1000, 5000, 10000, 50000, 100000}

	// countBuckets for counts
	CountBuckets = []float64{1, 5, 10, 25, 50, 100, 250, 500, 1000}
)

// Standard labels for all metrics
var standardLabels = []string{"chain", "pool"}

// Pre-registered metrics (initialized once)
var (
	// PnL metrics
	lpbotPnlTotalUSD      = Gauge("lpbot_pnl_total_usd", "Total PnL in USD across all positions")
	lpbotPositionStatus   = Gauge("lpbot_position_status", "Number of open positions by status (1=open, 0=closed)")
	lpbotFeesCollectedUSD = Counter("lpbot_fees_collected_usd", "Total fees collected in USD")
	lpbotILImpactPct      = Gauge("lpbot_il_impact_pct", "Impermanent loss impact percentage")

	// Exposure metrics
	lpbotRiskExposurePct = Gauge("lpbot_risk_exposure_pct", "Current risk exposure as percentage of total capital")

	// Transaction metrics
	lpbotTxFailedTotal       = CounterVec("lpbot_tx_failed_total", "Total failed transactions", []string{"chain", "pool", "reason"})
	lpbotTxPendingAgeSeconds = Histogram("lpbot_tx_pending_age_seconds", "Age of pending transactions in seconds", LatencyBuckets)

	// Risk metrics
	lpbotRiskBlockTotal  = Counter("lpbot_risk_block_total", "Total number of risk blocks (position blocked by risk)")
	lpbotAllocBlockTotal = Counter("lpbot_alloc_block_total", "Total number of allocation blocks (position blocked by allocation limits)")

	// Simulation metrics
	lpbotSimulateFailTotal = Counter("lpbot_simulate_fail_total", "Total simulation failures")

	// Approval metrics
	lpbotApproveFailTotal = Counter("lpbot_approve_fail_total", "Total approval failures")

	// Broadcast metrics
	lpbotBroadcastLatencySeconds = Histogram("lpbot_broadcast_latency_seconds", "Time to broadcast transaction in seconds", LatencyBuckets)

	// MEV metrics
	lpbotMevFallbackTotal = Counter("lpbot_mev_fallback_total", "Total MEV fallback events (when MEV protection fails)")

	// Watchdog metrics
	lpbotWatchdogTriggerTotal = CounterVec("lpbot_watchdog_trigger_total", "Total watchdog triggers", []string{"check_type", "level"})
	lpbotLoopHeartbeatSeconds = Gauge("lpbot_loop_heartbeat_seconds", "Last loop heartbeat timestamp (Unix seconds)")

	// Bootstrap/reconcile metrics
	lpbotBootstrapReconcileDurationSeconds = Histogram("lpbot_bootstrap_reconcile_duration_seconds", "Duration of bootstrap reconciliation in seconds", LatencyBuckets)

	// RPC metrics
	lpbotRpcEndpointErrorsTotal    = CounterVec("lpbot_rpc_endpoint_errors_total", "Total RPC endpoint errors", []string{"chain", "endpoint", "error_type"})
	lpbotRpcRequestDurationSeconds = HistogramVec("lpbot_rpc_request_duration_seconds", "RPC request duration in seconds", []string{"chain", "method", "endpoint"}, LatencyBuckets)

	// Dryrun invariant metrics
	lpbotDryrunBroadcastCallsTotal = Counter("lpbot_dryrun_broadcast_calls_total", "Total broadcast attempts in dryrun mode (should always be 0)")

	// Shadow operations metrics
	lpbotShadowScannedPools       = Gauge("lpbot_shadow_scanned_pools", "Pools scanned in the latest shadow tick")
	lpbotShadowCandidates         = Gauge("lpbot_shadow_candidates", "Candidate pools selected in the latest shadow tick")
	lpbotShadowEvaluated          = Gauge("lpbot_shadow_evaluated", "Pools evaluated by strategy in the latest shadow tick")
	lpbotShadowOrders             = Gauge("lpbot_shadow_orders", "Shadow orders opened or matched in the latest shadow tick")
	lpbotDatasourceRateLimitTotal = CounterVec("lpbot_datasource_rate_limit_total", "Total datasource rate limit responses", []string{"source"})
	lpbotDatasourceCacheHitTotal  = CounterVec("lpbot_datasource_cache_hit_total", "Total datasource cache hits", []string{"source", "state"})
	lpbotDatasourceFallbackTotal  = CounterVec("lpbot_datasource_fallback_total", "Total datasource fallback uses", []string{"primary", "fallback", "operation"})
	lpbotShadowMarkedPositions    = Gauge("lpbot_shadow_marked_positions", "Shadow positions marked in the latest cycle")
	lpbotShadowMarkValueUSD       = Gauge("lpbot_shadow_mark_value_usd", "Total latest shadow marked valuation in USD")
	lpbotShadowMarkNetPnLUSD      = Gauge("lpbot_shadow_mark_net_pnl_usd", "Total latest shadow mark net PnL in USD")
	lpbotShadowExitSignals        = Gauge("lpbot_shadow_exit_signals", "Shadow positions that currently meet exit conditions")
)

// CounterVec creates and registers a new Prometheus CounterVec.
func CounterVec(name, help string, labels []string) *prometheus.CounterVec {
	counter := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: name,
		Help: help,
	}, labels)
	if err := defaultRegistry.Register(counter); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(*prometheus.CounterVec)
		}
	}
	return counter
}

// GaugeVec creates and registers a new Prometheus GaugeVec.
func GaugeVec(name, help string, labels []string) *prometheus.GaugeVec {
	gauge := prometheus.NewGaugeVec(prometheus.GaugeOpts{
		Name: name,
		Help: help,
	}, labels)
	if err := defaultRegistry.Register(gauge); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(*prometheus.GaugeVec)
		}
	}
	return gauge
}

// HistogramVec creates and registers a new Prometheus HistogramVec.
func HistogramVec(name, help string, labels []string, buckets []float64) *prometheus.HistogramVec {
	hist := prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    name,
		Help:    help,
		Buckets: buckets,
	}, labels)
	if err := defaultRegistry.Register(hist); err != nil {
		if are, ok := err.(prometheus.AlreadyRegisteredError); ok {
			return are.ExistingCollector.(*prometheus.HistogramVec)
		}
	}
	return hist
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

// RecordPnL records the current PnL value.
func RecordPnL(pnl decimal.Decimal) {
	f, _ := pnl.Float64()
	lpbotPnlTotalUSD.Set(f)
}

// RecordExposure records the current risk exposure percentage.
func RecordExposure(exposurePct float64) {
	lpbotRiskExposurePct.Set(exposurePct)
}

// RecordILImpact records the impermanent loss impact percentage.
func RecordILImpact(ilPct float64) {
	lpbotILImpactPct.Set(ilPct)
}

// RecordFeesCollected records fees collected in USD.
func RecordFeesCollected(amountUSD float64) {
	lpbotFeesCollectedUSD.Add(amountUSD)
}

// IncRiskBlock increments the risk block counter.
func IncRiskBlock() {
	lpbotRiskBlockTotal.Inc()
}

// IncAllocBlock increments the allocation block counter.
func IncAllocBlock() {
	lpbotAllocBlockTotal.Inc()
}

// IncSimulateFail increments the simulation failure counter.
func IncSimulateFail() {
	lpbotSimulateFailTotal.Inc()
}

// IncApproveFail increments the approval failure counter.
func IncApproveFail() {
	lpbotApproveFailTotal.Inc()
}

// IncTxFailed increments the transaction failure counter.
func IncTxFailed(chain, pool, reason string) {
	lpbotTxFailedTotal.WithLabelValues(chain, pool, reason).Inc()
}

// ObserveTxPendingAge records the age of a pending transaction.
func ObserveTxPendingAge(seconds float64) {
	lpbotTxPendingAgeSeconds.Observe(seconds)
}

// ObserveBroadcastLatency records the time to broadcast a transaction.
func ObserveBroadcastLatency(seconds float64) {
	lpbotBroadcastLatencySeconds.Observe(seconds)
}

// IncMevFallback increments the MEV fallback counter.
func IncMevFallback() {
	lpbotMevFallbackTotal.Inc()
}

// IncWatchdogTrigger increments the watchdog trigger counter.
func IncWatchdogTrigger(checkType, level string) {
	lpbotWatchdogTriggerTotal.WithLabelValues(checkType, level).Inc()
}

// RecordLoopHeartbeat records the current time as the loop heartbeat.
func RecordLoopHeartbeat() {
	lpbotLoopHeartbeatSeconds.Set(float64(time.Now().Unix()))
}

// ObserveReconcileDuration records the duration of a reconciliation run.
func ObserveReconcileDuration(seconds float64) {
	lpbotBootstrapReconcileDurationSeconds.Observe(seconds)
}

// IncRpcEndpointError increments the RPC endpoint error counter.
func IncRpcEndpointError(chain, endpoint, errorType string) {
	lpbotRpcEndpointErrorsTotal.WithLabelValues(chain, endpoint, errorType).Inc()
}

// ObserveRpcRequestDuration records the duration of an RPC request.
func ObserveRpcRequestDuration(chain, method, endpoint string, seconds float64) {
	lpbotRpcRequestDurationSeconds.WithLabelValues(chain, method, endpoint).Observe(seconds)
}

// IncDryrunBroadcast increments the dryrun broadcast counter (should always be 0).
func IncDryrunBroadcast() {
	lpbotDryrunBroadcastCallsTotal.Inc()
}

// RecordShadowTick records the latest shadow business loop counts.
func RecordShadowTick(scanned, candidates, evaluated, shadowOrders int) {
	lpbotShadowScannedPools.Set(float64(scanned))
	lpbotShadowCandidates.Set(float64(candidates))
	lpbotShadowEvaluated.Set(float64(evaluated))
	lpbotShadowOrders.Set(float64(shadowOrders))
}

// IncDatasourceRateLimit increments a datasource rate-limit counter.
func IncDatasourceRateLimit(source string) {
	lpbotDatasourceRateLimitTotal.WithLabelValues(source).Inc()
}

// IncDatasourceCacheHit increments a datasource cache-hit counter.
func IncDatasourceCacheHit(source, state string) {
	lpbotDatasourceCacheHitTotal.WithLabelValues(source, state).Inc()
}

// IncDatasourceFallback increments a datasource fallback counter.
func IncDatasourceFallback(primary, fallback, operation string) {
	lpbotDatasourceFallbackTotal.WithLabelValues(primary, fallback, operation).Inc()
}

// RecordShadowPositionMarks records the latest aggregate mark state.
func RecordShadowPositionMarks(marked int, valuationUSD, netPnLUSD float64) {
	lpbotShadowMarkedPositions.Set(float64(marked))
	lpbotShadowMarkValueUSD.Set(valuationUSD)
	lpbotShadowMarkNetPnLUSD.Set(netPnLUSD)
}

// RecordShadowExitSignals records the latest number of shadow exit signals.
func RecordShadowExitSignals(signals int) {
	lpbotShadowExitSignals.Set(float64(signals))
}

// SetPositionStatus sets the position status gauge (1=open, 0=closed).
// Note: This is a simple gauge without pool labels. For detailed tracking,
// use the CounterVec pattern with chain/pool labels.
func SetPositionStatus(open bool) {
	if open {
		lpbotPositionStatus.Set(1)
	} else {
		lpbotPositionStatus.Set(0)
	}
}
