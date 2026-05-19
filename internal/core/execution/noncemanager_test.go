package execution

import (
	"context"
	"errors"
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockEVMChain is a mock implementation of ports.EVMChain for testing.
type mockEVMChain struct {
	pendingNonceAt func(ctx context.Context, addr domain.Address) (uint64, error)
	nonceAt        func(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error)
	info           func() ports.ChainInfo
}

func (m *mockEVMChain) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	if m.pendingNonceAt != nil {
		return m.pendingNonceAt(ctx, addr)
	}
	return 0, errors.New("not implemented")
}

func (m *mockEVMChain) NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error) {
	if m.nonceAt != nil {
		return m.nonceAt(ctx, addr, ref)
	}
	return 0, errors.New("not implemented")
}

func (m *mockEVMChain) Info() ports.ChainInfo {
	if m.info != nil {
		return m.info()
	}
	return ports.ChainInfo{}
}

func (m *mockEVMChain) SuggestGasFees(ctx context.Context) (*big.Int, *big.Int, error) {
	return nil, nil, errors.New("not implemented")
}

// Ensure mockEVMChain implements ports.EVMChain for compilation.
var _ ports.EVMChain = (*mockEVMChain)(nil)

// mockChain implements the remaining Chain interface methods.
func (m *mockEVMChain) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, errors.New("not implemented")
}

func (m *mockEVMChain) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	return nil, errors.New("not implemented")
}

func (m *mockEVMChain) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, errors.New("not implemented")
}

func (m *mockEVMChain) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, errors.New("not implemented")
}

func (m *mockEVMChain) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, errors.New("not implemented")
}

// TestNonceManager_GetNextNonce_Initialization tests that GetNextNonce
// initializes the nonce from the chain on first call.
func TestNonceManager_GetNextNonce_Initialization(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(42), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// First call should initialize and return the chain nonce
	nonce, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)
	assert.Equal(t, uint64(42), nonce)

	// Second call should increment
	nonce, err = nm.GetNextNonce(context.Background())
	require.NoError(t, err)
	assert.Equal(t, uint64(43), nonce)
}

// TestNonceManager_GetNextNonce_Increment tests that GetNextNonce
// provides monotonic nonce increment.
func TestNonceManager_GetNextNonce_Increment(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(10), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Get first nonce
	nonce1, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)

	// Get second nonce
	nonce2, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)

	// Get third nonce
	nonce3, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)

	// Verify monotonic increment
	assert.Equal(t, uint64(10), nonce1)
	assert.Equal(t, uint64(11), nonce2)
	assert.Equal(t, uint64(12), nonce3)

	// Verify CurrentNonce returns the next expected nonce
	assert.Equal(t, uint64(13), nm.CurrentNonce())
}

// TestNonceManager_AcknowledgeNonce tests that AcknowledgeNonce
// tracks acknowledged nonces correctly.
func TestNonceManager_AcknowledgeNonce(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(5), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Initialize nonce
	nonce1, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)
	assert.Equal(t, uint64(5), nonce1)

	// Acknowledge the nonce
	nm.AcknowledgeNonce(context.Background(), nonce1, "0xtxhash1")

	// Verify pending contains the acknowledged nonce
	pending, err := nm.GetPendingNonces(context.Background())
	require.NoError(t, err)
	assert.Contains(t, pending, nonce1)

	// Get next nonce
	nonce2, err := nm.GetNextNonce(context.Background())
	require.NoError(t, err)
	assert.Equal(t, uint64(6), nonce2)

	// Acknowledge second nonce
	nm.AcknowledgeNonce(context.Background(), nonce2, "0xtxhash2")

	// Verify pending contains both
	pending, err = nm.GetPendingNonces(context.Background())
	require.NoError(t, err)
	assert.Contains(t, pending, nonce1)
	assert.Contains(t, pending, nonce2)
}

// TestNonceManager_GetPendingNonces tests that GetPendingNonces
// returns all pending nonces in sorted order.
func TestNonceManager_GetPendingNonces(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(0), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Initially, no nonces are pending (not initialized in terms of pending tracking)
	pending, err := nm.GetPendingNonces(context.Background())
	require.NoError(t, err)
	assert.Empty(t, pending)

	// Get several nonces
	nonce1, _ := nm.GetNextNonce(context.Background()) // 0
	nonce2, _ := nm.GetNextNonce(context.Background()) // 1
	nonce3, _ := nm.GetNextNonce(context.Background()) // 2

	// Acknowledge some
	nm.AcknowledgeNonce(context.Background(), nonce1, "0xhash1")
	nm.AcknowledgeNonce(context.Background(), nonce3, "0xhash3")

	// Get pending (nonce2 is still reserved but not acknowledged)
	pending, err = nm.GetPendingNonces(context.Background())
	require.NoError(t, err)

	// Should contain all acknowledged + reserved
	assert.Len(t, pending, 3)
	assert.Equal(t, uint64(0), pending[0])
	assert.Equal(t, uint64(1), pending[1])
	assert.Equal(t, uint64(2), pending[2])

	// Suppress unused variable warning
	_ = nonce2
}

// TestNonceManager_IsNonceAvailable tests that IsNonceAvailable
// correctly checks nonce availability.
func TestNonceManager_IsNonceAvailable(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(5), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Before initialization, any nonce is "available" (no conflict known)
	available, err := nm.IsNonceAvailable(context.Background(), uint64(100))
	require.NoError(t, err)
	assert.True(t, available)

	// Initialize nonce
	_, err = nm.GetNextNonce(context.Background()) // returns 5, nonce becomes 6
	require.NoError(t, err)

	// Nonces >= 6 should be available (future nonces)
	available, err = nm.IsNonceAvailable(context.Background(), uint64(6))
	require.NoError(t, err)
	assert.True(t, available)

	available, err = nm.IsNonceAvailable(context.Background(), uint64(7))
	require.NoError(t, err)
	assert.True(t, available)

	// Nonces < 6 should not be available (already used)
	available, err = nm.IsNonceAvailable(context.Background(), uint64(5))
	require.NoError(t, err)
	assert.False(t, available)

	available, err = nm.IsNonceAvailable(context.Background(), uint64(3))
	require.NoError(t, err)
	assert.False(t, available)
}

// TestNonceManager_InitializeNonce tests explicit nonce initialization.
func TestNonceManager_InitializeNonce(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(100), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Before initialization
	assert.False(t, nm.IsInitialized())

	// Explicitly initialize
	err := nm.InitializeNonce(context.Background())
	require.NoError(t, err)

	// After initialization
	assert.True(t, nm.IsInitialized())
	assert.Equal(t, uint64(100), nm.CurrentNonce())
}

// TestNonceManager_ClearPending tests clearing pending nonces.
func TestNonceManager_ClearPending(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(0), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Get and acknowledge nonces
	nonce1, _ := nm.GetNextNonce(context.Background())
	nonce2, _ := nm.GetNextNonce(context.Background())
	nm.AcknowledgeNonce(context.Background(), nonce1, "0xhash1")
	nm.AcknowledgeNonce(context.Background(), nonce2, "0xhash2")

	// Clear one nonce
	nm.ClearPending(nonce1)

	// Verify it's cleared
	pending, _ := nm.GetPendingNonces(context.Background())
	assert.NotContains(t, pending, nonce1)
	assert.Contains(t, pending, nonce2)
}

// TestNonceManager_ConcurrentAccess tests thread safety.
func TestNonceManager_ConcurrentAccess(t *testing.T) {
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return uint64(0), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// Concurrent GetNextNonce calls
	results := make(chan uint64, 100)
	errors := make(chan error, 100)

	for i := 0; i < 100; i++ {
		go func() {
			nonce, err := nm.GetNextNonce(context.Background())
			if err != nil {
				errors <- err
				return
			}
			results <- nonce
		}()
	}

	// Collect results
	var nonces []uint64
	for i := 0; i < 100; i++ {
		select {
		case nonce := <-results:
			nonces = append(nonces, nonce)
		case err := <-errors:
			t.Fatalf("unexpected error: %v", err)
		}
	}

	// Verify all nonces are unique and sequential
	assert.Len(t, nonces, 100)
	for i := uint64(0); i < 100; i++ {
		assert.Contains(t, nonces, i)
	}
}

// TestNonceManager_ChainError tests error handling when chain call fails.
func TestNonceManager_ChainError(t *testing.T) {
	expectedErr := errors.New("connection refused")
	chain := &mockEVMChain{
		pendingNonceAt: func(ctx context.Context, addr domain.Address) (uint64, error) {
			return 0, expectedErr
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	nm := NewNonceManager(chain, walletAddr)

	// GetNextNonce should return the error
	_, err := nm.GetNextNonce(context.Background())
	assert.Error(t, err)
	assert.Equal(t, expectedErr, err)
}