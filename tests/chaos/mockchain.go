package chaos

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"time"
)

// MockChain provides a mock HTTP server that can inject various failure modes.
// It's used for testing system resilience under adverse network conditions.
type MockChain struct {
	server *httptest.Server
	mu     sync.RWMutex

	// Configurable failure modes
	failMode   FailureMode
	delay     time.Duration
	errCode   int
	errMsg    string
	timeout   time.Duration
	flakyRate float64 // 0.0 to 1.0

	requestCount int
	flakyCount   int
}

// FailureMode defines the type of failure to inject.
type FailureMode int

const (
	FailureNone FailureMode = iota
	FailureNetworkError   // connection failures
	FailureServerError   // 5xx responses
	FailureHighLatency   // delayed responses
	FailureFlaky         // intermittent failures
	FailureTimeout       // hung requests
)

// NewMockChain creates a new mock HTTP server with chaos injection.
func NewMockChain() *MockChain {
	mc := &MockChain{
		failMode: FailureNone,
		errCode: http.StatusInternalServerError,
		errMsg:  "internal server error",
	}
	mc.server = httptest.NewServer(http.HandlerFunc(mc.handle))
	return mc
}

// URL returns the base URL of the mock server.
func (m *MockChain) URL() string {
	return m.server.URL
}

// Close shuts down the mock server.
func (m *MockChain) Close() {
	m.server.Close()
}

// SetFailureMode configures the failure injection mode.
func (m *MockChain) SetFailureMode(mode FailureMode) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.failMode = mode
}

// SetDelay configures a fixed delay for all responses.
func (m *MockChain) SetDelay(d time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.delay = d
}

// SetErrorResponse configures the error code and message for server errors.
// Also sets the failure mode to FailureServerError.
func (m *MockChain) SetErrorResponse(code int, msg string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.errCode = code
	m.errMsg = msg
	m.failMode = FailureServerError
}

// SetFlakyRate sets the probability (0.0-1.0) of returning an error on each request.
func (m *MockChain) SetFlakyRate(rate float64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.flakyRate = rate
}

// Stats returns statistics about the mock server's request handling.
func (m *MockChain) Stats() (requestCount, flakyCount int) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.requestCount, m.flakyCount
}

// handle processes incoming requests based on the configured failure mode.
func (m *MockChain) handle(w http.ResponseWriter, r *http.Request) {
	m.mu.Lock()
	m.requestCount++
	m.mu.Unlock()

	m.mu.RLock()
	mode := m.failMode
	delay := m.delay
	errCode := m.errCode
	errMsg := m.errMsg
	flakyRate := m.flakyRate
	m.mu.RUnlock()

	// Handle timeout mode by not responding
	if mode == FailureTimeout {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(120 * time.Second): // Long timeout, won't happen in normal tests
			return
		}
	}

	// Handle high latency mode
	if mode == FailureHighLatency || delay > 0 {
		time.Sleep(10 * time.Second)
	}

	// Handle flaky mode
	if mode == FailureFlaky || flakyRate > 0 {
		if time.Now().UnixNano()%100 < int64(flakyRate*100) {
			m.mu.Lock()
			m.flakyCount++
			m.mu.Unlock()
			http.Error(w, errMsg, errCode)
			return
		}
	}

	// Handle network error mode
	if mode == FailureNetworkError {
		// Close connection without response
		hijacker, ok := w.(http.Hijacker)
		if ok {
			conn, _, _ := hijacker.Hijack()
			conn.Close()
		}
		return
	}

	// Handle server error mode
	if mode == FailureServerError {
		http.Error(w, errMsg, errCode)
		return
	}

	// Normal response
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// ScenarioNetworkPartition configures the mock for a complete network partition.
// All requests will fail with connection errors.
func ScenarioNetworkPartition(mc *MockChain) {
	mc.SetFailureMode(FailureNetworkError)
}

// ScenarioHighLatency configures the mock for high latency responses.
// All responses will be delayed by 10+ seconds.
func ScenarioHighLatency(mc *MockChain) {
	mc.SetFailureMode(FailureHighLatency)
}

// ScenarioFlaky configures the mock for intermittent failures.
// Requests will randomly fail based on the flaky rate.
func ScenarioFlaky(mc *MockChain, rate float64) {
	mc.SetFlakyRate(rate)
}

// ScenarioTimeout configures the mock for request timeouts.
// Requests will hang indefinitely.
func ScenarioTimeout(mc *MockChain) {
	mc.SetFailureMode(FailureTimeout)
}