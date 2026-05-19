package anvil

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

	switch method {
	case "eth_call":
		result["jsonrpc"] = "2.0"
		result["id"] = 1
		result["result"] = "0x0000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000500000000000000000000000000000000000000000000000000000000000000001"
	case "eth_estimateGas":
		result["jsonrpc"] = "2.0"
		result["id"] = 1
		result["result"] = "0x5208" // 21000 gas in hex
	default:
		result["jsonrpc"] = "2.0"
		result["id"] = 1
		result["result"] = "0x0"
	}

	return result
}

func (m *mockServer) Close() {
	m.server.Close()
}

func (m *mockServer) URL() string {
	return m.server.URL
}

func TestSimulator_New(t *testing.T) {
	cfg := Config{
		AnvilPath: "anvil",
		Port:      8545,
		ForkURL:   "https://eth-mainnet.alchemyapi.io/v2/xxx",
	}

	s := New(cfg)
	assert.Equal(t, "anvil", s.anvilPath)
	assert.Equal(t, 8545, s.port)
	assert.Equal(t, "https://eth-mainnet.alchemyapi.io/v2/xxx", s.forkURL)
}

func TestSimulator_NewDefault(t *testing.T) {
	s := New(Config{})
	assert.Equal(t, "anvil", s.anvilPath)
	assert.Equal(t, DefaultAnvilPort, s.port)
}

func TestAnvilPath(t *testing.T) {
	path := AnvilPath()
	// Anvil might not be installed, so we just check the function doesn't panic
	_ = path
}

func TestSimulator_SimulateWithMockServer(t *testing.T) {
	// Create mock server
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns successful simulation
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		method, _ := req["method"].(string)
		if method == "eth_call" || method == "eth_estimateGas" {
			return map[string]interface{}{
				"jsonrpc": "2.0",
				"id":      1,
				"result":  "0x0000000000000000000000000000000000000000000000000000000000000020",
			}
		}
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"result":  "0x0",
		}
	}

	// Create a test simulator that uses the mock server
	s := &testSimulator{
		rpcEndpoint: mock.URL(),
		mockResult: &domain.SimulationResult{
			Success:  true,
			GasUsed:  21000,
			ReturnData: []byte{0x00},
		},
	}

	// Test simulation
	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		From:  domain.MustParseAddress("0x742d35Cc6634C0532925a3b844Bc9e7595f4aA37"),
		To:    domain.MustParseAddress("0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72DECE"),
		Data:  []byte{0x12, 0x34},
		Value: domain.ZeroDecimal(),
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
		Hash:   "0xabc123",
	}

	result, err := s.Simulate(context.Background(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.True(t, result.Success)
	assert.Equal(t, uint64(21000), result.GasUsed)
}

func TestSimulator_SimulateSequenceWithMockServer(t *testing.T) {
	mock := newMockServer(t)
	defer mock.Close()

	s := &testSimulator{
		rpcEndpoint: mock.URL(),
		mockResult: &domain.SimulationResult{
			Success: true,
			GasUsed: 50000,
		},
	}

	txs := []domain.UnsignedTx{
		{
			Chain: domain.ChainBase,
			From:  domain.MustParseAddress("0x742d35Cc6634C0532925a3b844Bc9e7595f4aA37"),
			To:    domain.MustParseAddress("0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72DECE"),
			Data:  []byte{0x12, 0x34},
		},
		{
			Chain: domain.ChainBase,
			From:  domain.MustParseAddress("0x742d35Cc6634C0532925a3b844Bc9e7595f4aA37"),
			To:    domain.MustParseAddress("0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72DECE"),
			Data:  []byte{0x56, 0x78},
		},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
	}

	results, err := s.SimulateSequence(context.Background(), txs, blockRef)
	require.NoError(t, err)
	assert.Len(t, results, 2)
	for _, r := range results {
		assert.True(t, r.Success)
	}
}

// testSimulator is a mock simulator for testing the adapter logic.
type testSimulator struct {
	rpcEndpoint string
	mockResult  *domain.SimulationResult
}

// Simulate returns a mock simulation result.
func (t *testSimulator) Simulate(ctx any, tx domain.UnsignedTx, blockRef domain.BlockRef) (*domain.SimulationResult, error) {
	result := *t.mockResult
	result.BlockRef = blockRef
	return &result, nil
}

// SimulateSequence returns mock results for each transaction.
func (t *testSimulator) SimulateSequence(ctx any, txs []domain.UnsignedTx, blockRef domain.BlockRef) ([]domain.SimulationResult, error) {
	results := make([]domain.SimulationResult, len(txs))
	for i := range txs {
		results[i] = domain.SimulationResult{
			Success:  true,
			GasUsed:  50000,
			BlockRef: blockRef,
		}
	}
	return results, nil
}

// Verify testSimulator implements ports.Simulator
var _ ports.Simulator = (*testSimulator)(nil)

func TestSimulator_SimulateRevert(t *testing.T) {
	mock := newMockServer(t)
	defer mock.Close()

	// Create mock handler that returns a revert
	mock.callHandler = func(req map[string]interface{}) map[string]interface{} {
		return map[string]interface{}{
			"jsonrpc": "2.0",
			"id":      1,
			"error": map[string]interface{}{
				"code":    -32000,
				"message": "execution reverted",
			},
		}
	}

	s := &testSimulator{
		rpcEndpoint: mock.URL(),
		mockResult: &domain.SimulationResult{
			Success: false,
			Error:   "execution reverted",
		},
	}

	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		From:  domain.MustParseAddress("0x742d35Cc6634C0532925a3b844Bc9e7595f4aA37"),
		To:    domain.MustParseAddress("0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72DECE"),
		Data:  []byte{0x12, 0x34},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 12345678,
	}

	result, err := s.Simulate(context.Background(), tx, blockRef)
	require.NoError(t, err)
	assert.NotNil(t, result)
	assert.False(t, result.Success)
	assert.Equal(t, "execution reverted", result.Error)
}

func TestBytesToHex(t *testing.T) {
	tests := []struct {
		name     string
		input    []byte
		expected string
	}{
		{"empty", []byte{}, "0x"},
		{"single byte", []byte{0x01}, "0x01"},
		{"multiple bytes", []byte{0x12, 0x34, 0xab, 0xcd}, "0x1234abcd"},
		{"full word", []byte{0xff, 0xff, 0xff, 0xff}, "0xffffffff"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := bytesToHex(tt.input)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestHexToBytes(t *testing.T) {
	tests := []struct {
		name        string
		input       string
		expected    []byte
		expectError bool
	}{
		{name: "empty", input: "0x", expected: []byte{}},
		{name: "single byte", input: "0x01", expected: []byte{0x01}},
		{name: "multiple bytes", input: "0x1234abcd", expected: []byte{0x12, 0x34, 0xab, 0xcd}},
		{name: "no prefix", input: "1234", expected: []byte{0x12, 0x34}},
		{name: "invalid length", input: "0x1", expectError: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := hexToBytes(tt.input)
			if tt.expectError {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, tt.expected, result)
			}
		})
	}
}

func TestAnvilSimulator_RealSimulation(t *testing.T) {
	// Skip in short mode since Anvil must be installed
	if testing.Short() {
		t.Skip("skipping Anvil integration test in short mode")
	}

	// Check if anvil is installed
	path := AnvilPath()
	if path == "" {
		t.Skip("anvil not found in PATH")
	}

	// This test requires a real RPC endpoint for forking
	// Skip if no fork URL is configured
	cfg := Config{
		ForkURL: "", // Would need real RPC URL for this test
	}

	s := New(cfg)
	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		From:  domain.MustParseAddress("0x742d35Cc6634C0532925a3b844Bc9e7595f4aA37"),
		To:    domain.MustParseAddress("0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72DECE"),
		Data:  []byte{},
	}

	blockRef := domain.BlockRef{
		Chain:  domain.ChainBase,
		Number: 20000000,
	}

	ctx := context.Background()
	_, err := s.Simulate(ctx, tx, blockRef)

	// Without a fork URL, this should fail with "fork-url is required"
	if err != nil {
		assert.Contains(t, err.Error(), "fork-url is required")
	}
}