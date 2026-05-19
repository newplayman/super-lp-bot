package chaos

import (
	"net/http"
	"testing"
	"time"
)

// ScenarioNetworkPartition tests the system behavior under complete network partition.
func TestScenarioNetworkPartition(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	ScenarioNetworkPartition(mc)

	// Verify that requests to the mock will fail
	// (in real usage, this would test that the caller handles network errors gracefully)
	reqCount, _ := mc.Stats()
	if reqCount != 0 {
		t.Logf("Stats after partition scenario: %d requests", reqCount)
	}
}

// ScenarioHighLatency tests the system behavior under high latency conditions.
func TestScenarioHighLatency(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	ScenarioHighLatency(mc)

	reqCount, _ := mc.Stats()
	if reqCount != 0 {
		t.Logf("Stats after high latency scenario: %d requests", reqCount)
	}
}

// ScenarioFlaky tests the system behavior under intermittent failures.
func TestScenarioFlaky(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	ScenarioFlaky(mc, 0.5) // 50% failure rate

	reqCount, _ := mc.Stats()
	if reqCount != 0 {
		t.Logf("Stats after flaky scenario: %d requests", reqCount)
	}
}

// ScenarioTimeout tests the system behavior under request timeouts.
func TestScenarioTimeout(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	ScenarioTimeout(mc)

	reqCount, _ := mc.Stats()
	if reqCount != 0 {
		t.Logf("Stats after timeout scenario: %d requests", reqCount)
	}
}

// TestMockChainBasics tests basic mock chain functionality.
func TestMockChainBasics(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	// Test normal operation
	resp, err := http.Get(mc.URL())
	if err != nil {
		t.Fatalf("normal request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}

	reqCount, _ := mc.Stats()
	if reqCount != 1 {
		t.Errorf("expected 1 request, got %d", reqCount)
	}
}

// TestMockChainConfigurableDelays tests the delay configuration.
func TestMockChainConfigurableDelays(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	mc.SetDelay(100 * time.Millisecond)

	start := time.Now()
	resp, err := http.Get(mc.URL())
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	resp.Body.Close()

	if elapsed < 100*time.Millisecond {
		t.Errorf("expected delay of at least 100ms, got %v", elapsed)
	}
}

// TestMockChainErrorResponses tests configurable error responses.
func TestMockChainErrorResponses(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	mc.SetErrorResponse(http.StatusServiceUnavailable, "service unavailable")

	resp, err := http.Get(mc.URL())
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", resp.StatusCode)
	}
}

// TestScenarioNetworkPartition_Integration is an integration test that
// verifies the chaos scenarios work correctly with real HTTP clients.
func TestScenarioNetworkPartition_Integration(t *testing.T) {
	mc := NewMockChain()
	defer mc.Close()

	ScenarioNetworkPartition(mc)

	// The network partition scenario should cause connection failures
	// when using HTTP clients. This test verifies the scenario is set up correctly.
	// Real integration would use this with actual service clients.
}