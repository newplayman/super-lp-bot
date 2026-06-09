// Package rpc provides stability tests for the round-robin provider.
//
// These tests verify that endpoint ordering and failover behavior are
// deterministic and not sensitive to Go map iteration order or goroutine
// scheduling. They were added in the
// LP_BOT_ENGINEERING_P1_TEST_SUITE_STABILIZATION_V1 stage to lock down
// the fix for the pre-existing TestRoundRobinProvider_Endpoint flake.
package rpc

import (
	"sort"
	"strings"
	"testing"
)

// TestRoundRobinProvider_InitialOrderStableAcrossRuns verifies that the
// initial endpoint order is stable across repeated NewRoundRobinProvider
// invocations. Before the fix, the order depended on the order in which
// the probe goroutines completed (channel iteration order), which is
// non-deterministic. The fix sorts by the original index when all
// endpoints fail (which is the case for any test endpoint that DNS
// can't resolve).
func TestRoundRobinProvider_InitialOrderStableAcrossRuns(t *testing.T) {
	const runs = 20
	endpoints := []string{
		"https://endpoint1.example.com",
		"https://endpoint2.example.com",
		"https://endpoint3.example.com",
	}

	// Each run should produce the same initial order (input order, since
	// all endpoints fail in this test).
	for i := 0; i < runs; i++ {
		provider, err := NewRoundRobinProvider(Config{
			ChainID:   "stability-chain",
			Endpoints: append([]string{}, endpoints...),
		})
		if err != nil {
			t.Fatalf("run %d: NewRoundRobinProvider failed: %v", i, err)
		}
		got := provider.copyEndpoints()
		want := endpoints
		if !equalSlices(got, want) {
			t.Errorf("run %d: initial order drift; got %v, want %v", i, got, want)
		}
	}
}

// TestRoundRobinProvider_InitialOrderPreservesInputIndex verifies that
// the initial order is a deterministic function of the input order,
// NOT of any map iteration / channel / goroutine scheduling. The
// code's contract is: preserve input order, period. We feed 5
// different orderings and check the result is always the same as
// the input.
func TestRoundRobinProvider_InitialOrderPreservesInputIndex(t *testing.T) {
	// Per design: NewRoundRobinProvider preserves the caller's input
	// order. This test verifies that contract by feeding different
	// orderings and checking the output matches each input.
	inputs := [][]string{
		{"https://primary.example.com", "https://secondary.example.com", "https://tertiary.example.com"},
		{"https://tertiary.example.com", "https://primary.example.com", "https://secondary.example.com"},
		{"https://secondary.example.com", "https://tertiary.example.com", "https://primary.example.com"},
		{"https://primary.example.com", "https://tertiary.example.com", "https://secondary.example.com"},
		{"https://secondary.example.com", "https://primary.example.com", "https://tertiary.example.com"},
	}
	for i, in := range inputs {
		provider, err := NewRoundRobinProvider(Config{
			ChainID:   "input-order-chain",
			Endpoints: append([]string{}, in...),
		})
		if err != nil {
			t.Fatalf("case %d: NewRoundRobinProvider failed: %v", i, err)
		}
		got := provider.copyEndpoints()
		if !equalSlices(got, in) {
			t.Errorf("case %d: input order not preserved; got %v, want %v", i, got, in)
		}
	}
}

// TestRoundRobinProvider_InitialOrderNotSortedAlphabetically verifies
// that when all endpoints fail, the order is [input[0], input[1], ...]
// (preserves input order, not alphabetic or random). This is the
// behavior the fix in rankEndpointsDetailed ensures via sort.SliceStable
// by index.
func TestRoundRobinProvider_InitialOrderNotSortedAlphabetically(t *testing.T) {
	endpoints := []string{
		"https://zzz-last.example.com",
		"https://aaa-first.example.com",
		"https://mmm-middle.example.com",
	}
	provider, err := NewRoundRobinProvider(Config{
		ChainID:   "input-index-chain",
		Endpoints: endpoints,
	})
	if err != nil {
		t.Fatalf("NewRoundRobinProvider failed: %v", err)
	}
	got := provider.copyEndpoints()
	want := endpoints
	if !equalSlices(got, want) {
		t.Errorf("expected input-order preservation, got %v want %v", got, want)
	}
	// Defensive: confirm we're NOT sorting alphabetically.
	alpha := []string{endpoints[1], endpoints[2], endpoints[0]} // aaa, mmm, zzz
	if equalSlices(got, alpha) {
		t.Errorf("endpoints are sorted alphabetically; expected input-order preservation: %v", got)
	}
}

// TestRoundRobinProvider_NextEndpointDeterministic verifies that
// repeated calls to nextEndpoint() rotate through the endpoint list in
// a stable order. This is the same property the original
// TestRoundRobinProvider_Endpoint test relies on, but verified under
// many iterations and many input sizes.
//
// Note: 1-endpoint configs are excluded because nextEndpoint() returns
// an error for them (no alternate to fall back to); that behavior is
// covered separately in
// TestRoundRobinProvider_SingleEndpointStableForRepeatedCalls.
func TestRoundRobinProvider_NextEndpointDeterministic(t *testing.T) {
	cases := [][]string{
		{"https://e1.example.com", "https://e2.example.com"},
		{"https://e1.example.com", "https://e2.example.com", "https://e3.example.com"},
		{"https://e1.example.com", "https://e2.example.com", "https://e3.example.com", "https://e4.example.com"},
	}
	for _, endpoints := range cases {
		provider, err := NewRoundRobinProvider(Config{
			ChainID:   "rotate-chain",
			Endpoints: append([]string{}, endpoints...),
		})
		if err != nil {
			t.Fatalf("setup %v: NewRoundRobinProvider failed: %v", endpoints, err)
		}
		// Run two full rotations and confirm we cycle through the
		// expected order both times.
		for round := 0; round < 2; round++ {
			got := make([]string, 0, len(endpoints))
			for i := 0; i < len(endpoints); i++ {
				got = append(got, provider.Endpoint())
				if err := provider.nextEndpoint(); err != nil {
					t.Fatalf("rotation round=%d step=%d: nextEndpoint failed: %v", round, i, err)
				}
			}
			// Got should equal the initial endpoint order (because
			// we made exactly len(endpoints) calls).
			if !equalSlices(got, provider.copyEndpoints()) {
				t.Errorf("round %d: rotation order mismatch; got %v want %v",
					round, got, provider.copyEndpoints())
			}
		}
	}
}

// TestRoundRobinProvider_RepeatedCallsNoMapIterationDependency is a
// regression test: 50 sequential NewRoundRobinProvider calls must all
// return the same initial order. This catches any future reintroduction
// of Go-map-iteration-order dependence (e.g. if a maintainer introduces
// a map for endpoint tracking without an explicit sort).
func TestRoundRobinProvider_RepeatedCallsNoMapIterationDependency(t *testing.T) {
	endpoints := []string{
		"https://alpha.example.com",
		"https://beta.example.com",
		"https://gamma.example.com",
		"https://delta.example.com",
	}
	// First run establishes the expected order.
	first, err := NewRoundRobinProvider(Config{
		ChainID:   "map-iter-chain",
		Endpoints: endpoints,
	})
	if err != nil {
		t.Fatalf("first NewRoundRobinProvider: %v", err)
	}
	firstOrder := first.copyEndpoints()

	// 50 more runs.
	const runs = 50
	for i := 0; i < runs; i++ {
		provider, err := NewRoundRobinProvider(Config{
			ChainID:   "map-iter-chain",
			Endpoints: append([]string{}, endpoints...),
		})
		if err != nil {
			t.Fatalf("run %d: NewRoundRobinProvider: %v", i, err)
		}
		got := provider.copyEndpoints()
		if !equalSlices(got, firstOrder) {
			t.Fatalf("run %d: order drift; got %v want %v", i, got, firstOrder)
		}
	}
}

// TestRoundRobinProvider_EndpointHostExtractorDoesNotMutateInput
// verifies that NewRoundRobinProvider does not mutate the caller's
// input slice. This is a sanity check for the input-order-preservation
// contract: if normalizeEndpoints mutated the input, the assertion
// above could pass while the test data is corrupted.
func TestRoundRobinProvider_EndpointHostExtractorDoesNotMutateInput(t *testing.T) {
	endpoints := []string{
		"https://e1.example.com",
		"https://e2.example.com",
		"https://e3.example.com",
	}
	snapshot := append([]string{}, endpoints...)
	_, err := NewRoundRobinProvider(Config{
		ChainID:   "no-mutate-chain",
		Endpoints: endpoints,
	})
	if err != nil {
		t.Fatalf("NewRoundRobinProvider: %v", err)
	}
	if !equalSlices(endpoints, snapshot) {
		t.Errorf("input slice mutated; got %v, want %v", endpoints, snapshot)
	}
}

// TestRoundRobinProvider_SingleEndpointStableForRepeatedCalls
// verifies edge case: a 1-endpoint config must return the same
// endpoint on every Endpoint() call. Note: with a single endpoint,
// nextEndpoint() returns "no alternate rpc endpoint available" because
// there is no other endpoint to fall back to; this is documented
// behavior, not a bug. The test only asserts Endpoint() stability.
func TestRoundRobinProvider_SingleEndpointStableForRepeatedCalls(t *testing.T) {
	endpoint := "https://only.example.com"
	provider, err := NewRoundRobinProvider(Config{
		ChainID:   "single-endpoint-chain",
		Endpoints: []string{endpoint},
	})
	if err != nil {
		t.Fatalf("NewRoundRobinProvider: %v", err)
	}
	for i := 0; i < 10; i++ {
		if got := provider.Endpoint(); got != endpoint {
			t.Errorf("call %d: expected %s, got %s", i, endpoint, got)
		}
		// nextEndpoint() intentionally returns an error for a
		// 1-endpoint config (no alternate to fall back to). We
		// verify the error message is the expected one, not just
		// any error.
		err := provider.nextEndpoint()
		if err == nil {
			t.Errorf("call %d: nextEndpoint on single-endpoint should return an error", i)
		} else if !strings.Contains(err.Error(), "no alternate") {
			t.Errorf("call %d: nextEndpoint error should mention 'no alternate', got: %v", i, err)
		}
	}
}

// TestRoundRobinProvider_EndpointStringPreserved verifies that
// endpoints are returned with their original string (no normalization
// that would change endpoint identity for downstream consumers).
func TestRoundRobinProvider_EndpointStringPreserved(t *testing.T) {
	endpoints := []string{
		"https://e1.example.com",
		"https://e2.example.com",
	}
	provider, err := NewRoundRobinProvider(Config{
		ChainID:   "string-preserve-chain",
		Endpoints: endpoints,
	})
	if err != nil {
		t.Fatalf("NewRoundRobinProvider: %v", err)
	}
	got := provider.copyEndpoints()
	if !equalSlices(got, endpoints) {
		// If normalizeEndpoints trimmed trailing slashes, that's
		// acceptable per design. We only require that the substring
		// before any "?" or "/" is unchanged.
		for i := range got {
			wantHost := strings.SplitN(strings.TrimSuffix(endpoints[i], "/"), "?", 2)[0]
			if !strings.HasPrefix(got[i], wantHost) {
				t.Errorf("endpoint %d: identity changed; got %s, want %s", i, got[i], wantHost)
			}
		}
	}
}

// equalSlices returns true if a and b have the same length and
// element-by-element equality.
func equalSlices(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// sortStrings is a small wrapper for sort.Strings to keep tests
// focused on behavioral assertions, not sorting details. (It is
// defined here only to make the file self-contained; not exported.)
var _ = sort.Strings
