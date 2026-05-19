package metrics_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lpbot/lpbot/internal/platform/metrics"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
	dto "github.com/prometheus/client_model/go"
	"github.com/stretchr/testify/require"
)

func TestCounter(t *testing.T) {
	counter := metrics.Counter("test_counter", "A test counter")

	// Record some values
	counter.Inc()
	counter.Inc()
	counter.Add(3)

	// Verify the counter value
	value := testutil.ToFloat64(counter)
	require.Equal(t, 5.0, value)
}

func TestGauge(t *testing.T) {
	gauge := metrics.Gauge("test_gauge", "A test gauge")

	// Set and modify value
	gauge.Set(42)
	require.Equal(t, 42.0, testutil.ToFloat64(gauge))

	gauge.Add(8)
	require.Equal(t, 50.0, testutil.ToFloat64(gauge))

	gauge.Sub(10)
	require.Equal(t, 40.0, testutil.ToFloat64(gauge))
}

func TestHistogram(t *testing.T) {
	buckets := []float64{0.1, 0.5, 1.0, 5.0, 10.0}
	hist := metrics.Histogram("test_histogram", "A test histogram", buckets)

	// Record some observations
	hist.Observe(0.3)
	hist.Observe(0.7)
	hist.Observe(2.5)
	hist.Observe(15.0)

	// Verify the histogram was registered and observations were recorded
	metric, err := metrics.GetRegistry().Gather()
	require.NoError(t, err)
	require.NotEmpty(t, metric)

	// Find our histogram metric
	var found bool
	for _, m := range metric {
		if m.GetName() == "test_histogram" {
			found = true
			// Verify it has histogram type
			require.Equal(t, dto.MetricType_HISTOGRAM, m.GetType())
			// Verify count is 4 (we observed 4 values)
			require.Equal(t, uint64(4), m.GetMetric()[0].Histogram.GetSampleCount())
		}
	}
	require.True(t, found, "Histogram metric should be registered")
}

func TestMetricsHandler(t *testing.T) {
	// Create a counter to ensure there's something to scrape
	counter := metrics.Counter("handler_test_counter", "Counter for handler test")
	counter.Inc()

	// Create handler and record response
	handler := http.HandlerFunc(metrics.Handler)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest("GET", "/metrics", nil))

	require.Equal(t, http.StatusOK, recorder.Code)
	require.Contains(t, recorder.Body.String(), "handler_test_counter")
}

func TestFactoryFunctionsReturnPrometheusTypes(t *testing.T) {
	// Counter should return prometheus.Counter
	counter := metrics.Counter("factory_counter", "Factory counter test")
	_, ok := counter.(prometheus.Counter)
	require.True(t, ok, "Counter should return prometheus.Counter")

	// Gauge should return prometheus.Gauge
	gauge := metrics.Gauge("factory_gauge", "Factory gauge test")
	_, ok = gauge.(prometheus.Gauge)
	require.True(t, ok, "Gauge should return prometheus.Gauge")

	// Histogram should return prometheus.Histogram
	hist := metrics.Histogram("factory_hist", "Factory histogram test", []float64{0.1, 0.5, 1.0})
	_, ok = hist.(prometheus.Histogram)
	require.True(t, ok, "Histogram should return prometheus.Histogram")
}

func TestGetRegistry(t *testing.T) {
	reg := metrics.GetRegistry()
	require.NotNil(t, reg)

	// Should be the same registry each time
	reg2 := metrics.GetRegistry()
	require.Equal(t, reg, reg2)
}

func TestDuplicateRegistration(t *testing.T) {
	// Registering the same name twice should not panic
	counter1 := metrics.Counter("dup_test_counter", "First registration")
	counter2 := metrics.Counter("dup_test_counter", "Second registration (same name)")

	// Both should work - second registration returns the existing one
	require.NotNil(t, counter1)
	require.NotNil(t, counter2)
}
