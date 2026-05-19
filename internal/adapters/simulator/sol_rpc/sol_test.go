package sol_rpc

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion
var _ ports.Simulator = (*simulator)(nil)

func TestSimulator_InterfaceAssertion(t *testing.T) {
	// Verify the simulator implements the ports.Simulator interface
	s := New(Config{})
	var _ ports.Simulator = s
}

func TestSimulator_New(t *testing.T) {
	cfg := Config{
		RPCEndpoint: "https://api.mainnet-beta.solana.com",
	}

	s := New(cfg)
	assert.Equal(t, "https://api.mainnet-beta.solana.com", s.rpcEndpoint)
}

func TestSimulator_NewDefault(t *testing.T) {
	s := New(Config{})
	assert.Equal(t, DefaultRPCEndpoint, s.rpcEndpoint)
}

// mockServer is a test JSON-RPC server that returns mock responses.
type mockServer struct {
	t           *testing.T
	callHandler func(req map[string]interface{}) map[string]interface{}
	server      *httptest.Server
}

func newMockServer(t *testing.T) *mockServer {
	m := &mockServer{t: t}
	m.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req map[string]interface{}
		err := json.NewDecoder(r.Body).Decode(&req)
		if err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}

		var resp map[string]interface{}
		if m.callHandler != nil {
			resp = m.callHandler(req)
		} else {
			resp = defaultMockHandler(req)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	return m
}

func defaultMockHandler(req map[string]interface{}) map[string]interface{} {
	method, _ := req["method"].(string)

	result := map[string]interface{}{}
	result["jsonrpc"] = "2.0"
	result["id"] = 1

	switch method {
	case "simulateTransaction":
		// Default successful simulation
		result["result"] = map[string]interface{}{
			"context": map[string]interface{}{
				"apiVersion": "1.18.4",
				"slot":       123456,
			},
			"value": map[string]interface{}{
				"err":             nil,
				"logs":            []string{"Program 11111 logged: success"},
				"unitsConsumed":   5000,
				"returnData":      nil,
			},
		}
	default:
		result["result"] = nil
	}

	return result
}

func (m *mockServer) Close() {
	m.server.Close()
}

func (m *mockServer) URL() string {
	return m.server.URL
}

// testSimulator wraps the real simulator for testing with mock RPC endpoint.
type testSimulator struct {
	simulator *simulator
}

func newTestSimulator(rpcEndpoint string) *testSimulator {
	return &testSimulator{
		simulator: &simulator{
			rpcEndpoint: rpcEndpoint,
			httpClient:  &http.Client{},
		},
	}
}

func (t *testSimulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	return t.simulator.Simulate(ctx, tx, blockRef)
}

func (t *testSimulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	return t.simulator.SimulateSequence(ctx, txs, blockRef)
}

// Verify testSimulator implements ports.Simulator
var _ ports.Simulator = (*testSimulator)(nil)

func TestSimulator_Simulate(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns successful simulation
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		method, _ := req["method"].(string)
		if method == "simulateTransaction" {
			return map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]interface{}{
					"context": map[string]interface{}{
						"apiVersion": "1.18.4",
						"slot":       123456,
					},
					"value": map[string]interface{}{
						"err":           nil,
						"logs":          []string{"Program 11111 logged: Transfer successful"},
						"unitsConsumed": 5000,
						"returnData":    nil,
					},
				},
			}
		}
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result":  nil,
		}
	}

	// Create test simulator with mock endpoint
	ts := newTestSimulator(mock.URL())

	// Create a test transaction
	tx := domain.UnsignedTx{
		Chain: domain.ChainSolana,
		From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
		To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
		Data:  []byte{},
		Value: domain.MustDecimal("1000000"), // 0.001 SOL in lamports
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainSolana,
		Number: 123456,
	}

	// Test simulation
	result, err := ts.Simulate(t.Context(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.True(t, result.Success)
	assert.Equal(t, uint64(5000), result.GasUsed)
	assert.Empty(t, result.Error)
}

func TestSimulator_SimulateWithLogs(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns simulation with logs
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		method, _ := req["method"].(string)
		if method == "simulateTransaction" {
			return map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]interface{}{
					"value": map[string]interface{}{
						"err":           nil,
						"logs":          []string{"Program 11111 instruction 0", "Program 11111 success"},
						"unitsConsumed": 10000,
					},
				},
			}
		}
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result":  nil,
		}
	}

	ts := newTestSimulator(mock.URL())

	tx := domain.UnsignedTx{
		Chain: domain.ChainSolana,
		From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
		To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
		Data:  []byte{},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainSolana,
		Number: 123456,
	}

	result, err := ts.Simulate(t.Context(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.True(t, result.Success)
	assert.NotEmpty(t, result.ReturnData)
	assert.Contains(t, string(result.ReturnData), "Program 11111")
}

func TestSimulator_SimulateError(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns a simulation error
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		method, _ := req["method"].(string)
		if method == "simulateTransaction" {
			return map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]interface{}{
					"value": map[string]interface{}{
						"err":   "InsufficientFunds",
						"logs":  []string{"Error: InsufficientFunds"},
						"unitsConsumed": 0,
					},
				},
			}
		}
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result":  nil,
		}
	}

	ts := newTestSimulator(mock.URL())

	tx := domain.UnsignedTx{
		Chain: domain.ChainSolana,
		From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
		To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
		Data:  []byte{},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainSolana,
		Number: 123456,
	}

	result, err := ts.Simulate(t.Context(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.False(t, result.Success)
	assert.Contains(t, result.Error, "InsufficientFunds")
}

func TestSimulator_SimulateRPCError(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns an RPC error
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"error": map[string]interface{}{
				"code":    -32600,
				"message": "Invalid Request",
			},
		}
	}

	ts := newTestSimulator(mock.URL())

	tx := domain.UnsignedTx{
		Chain: domain.ChainSolana,
		From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
		To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
	}

	blockRef := domain.BlockRef{
		Chain: domain.ChainSolana,
	}

	result, err := ts.Simulate(t.Context(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.False(t, result.Success)
	assert.Contains(t, result.Error, "Invalid Request")
}

func TestSimulator_SimulateSequence(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result": map[string]interface{}{
				"value": map[string]interface{}{
					"err":           nil,
					"logs":          []string{"Program 11111 logged: success"},
					"unitsConsumed": 5000,
				},
			},
		}
	}

	ts := newTestSimulator(mock.URL())

	txs := []domain.UnsignedTx{
		{
			Chain: domain.ChainSolana,
			From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
			To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
			Data:  []byte{},
		},
		{
			Chain: domain.ChainSolana,
			From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
			To:    domain.MustParseAddress("9Qy45DT9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq9"),
			Data:  []byte{},
		},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainSolana,
		Number: 123456,
	}

	results, err := ts.SimulateSequence(t.Context(), txs, blockRef)
	require.NoError(t, err)
	assert.Len(t, results, 2)
	for _, r := range results {
		assert.True(t, r.Success)
		assert.Equal(t, blockRef, r.BlockRef)
	}
}

func TestSimulator_SimulateSequenceWithError(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	callCount := 0
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		callCount++
		if callCount == 1 {
			// First tx succeeds
			return map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result": map[string]interface{}{
					"value": map[string]interface{}{
						"err":           nil,
						"logs":          []string{"Program 11111 logged: success"},
						"unitsConsumed": 5000,
					},
				},
			}
		}
		// Second tx fails
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result": map[string]interface{}{
				"value": map[string]interface{}{
					"err":   "CustomError",
					"logs":  []string{"Error: CustomError"},
				},
			},
		}
	}

	ts := newTestSimulator(mock.URL())

	txs := []domain.UnsignedTx{
		{
			Chain: domain.ChainSolana,
			From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
			To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
		},
		{
			Chain: domain.ChainSolana,
			From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
			To:    domain.MustParseAddress("9Qy45DT9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq9"),
		},
	}

	blockRef := domain.BlockRef{
		Chain: domain.ChainSolana,
	}

	results, err := ts.SimulateSequence(t.Context(), txs, blockRef)
	require.NoError(t, err)
	assert.Len(t, results, 2)
	assert.True(t, results[0].Success)
	assert.False(t, results[1].Success)
	assert.Contains(t, results[1].Error, "CustomError")
}

func TestFormatSolanaError(t *testing.T) {
	tests := []struct {
		name     string
		input    interface{}
		expected string
	}{
		{
			name:     "nil error",
			input:    nil,
			expected: "",
		},
		{
			name:     "string error",
			input:    "InsufficientFunds",
			expected: "InsufficientFunds",
		},
		{
			name:     "map error",
			input:    map[string]interface{}{"InstructionError": []interface{}{0, "InsufficientFunds"}},
			expected: "InstructionError: [0 InsufficientFunds]",
		},
		{
			name:     "unknown type",
			input:    12345,
			expected: "12345",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := formatSolanaError(tt.input)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestToContext(t *testing.T) {
	t.Run("nil context", func(t *testing.T) {
		result := toContext(nil)
		assert.NotNil(t, result)
	})

	t.Run("valid context", func(t *testing.T) {
		ctx := context.Background()
		result := toContext(ctx)
		assert.Equal(t, ctx, result)
	})

	t.Run("other type", func(t *testing.T) {
		result := toContext("string")
		assert.NotNil(t, result)
	})
}

func TestSimulator_ComplexTransaction(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result": map[string]interface{}{
				"value": map[string]interface{}{
					"err":           nil,
					"logs":          []string{"Program TokenkegQfeZyiNwAjbOdcfLyVoFGmvk7WC5nuGqxZHzb logged: instruction success"},
					"unitsConsumed": 250000,
					"returnData": map[string]interface{}{
						"programId": "TokenkegQfeZyiNwAjbOdcfLyVoFGmvk7WC5nuGqxZHzb",
						"data":      "AAAAAAEAAQ==",
					},
				},
			},
		}
	}

	ts := newTestSimulator(mock.URL())

	// Create a transaction with data (simulating a token transfer)
	tx := domain.UnsignedTx{
		Chain: domain.ChainSolana,
		From:  domain.MustParseAddress("7EcDhSYGxXyscszYEp35KNV9zYvtikJJrP7M5u7JwbEq"),
		To:    domain.MustParseAddress("8Px36CS9bRYqRWBvGTR4Lw9sSQ53Gwb8kbvZTcG6vZq8"),
		Data:  []byte{0x01, 0x02, 0x03, 0x04}, // custom instruction data
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainSolana,
		Number: 123456,
	}

	result, err := ts.Simulate(t.Context(), tx, blockRef)
	require.NoError(t, err)
	assert.True(t, result.Success)
	assert.Equal(t, uint64(250000), result.GasUsed)
	assert.NotEmpty(t, result.ReturnData)
}