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

// mockWallet is a mock implementation of ports.Wallet for testing.
type mockWallet struct {
	address        func() domain.Address
	approveExact  func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error)
	revoke        func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error)
}

func (m *mockWallet) Address() domain.Address {
	if m.address != nil {
		return m.address()
	}
	return domain.Address{}
}

func (m *mockWallet) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
	if m.approveExact != nil {
		return m.approveExact(ctx, token, spender, amount)
	}
	return domain.UnsignedTx{}, errors.New("not implemented")
}

func (m *mockWallet) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	if m.revoke != nil {
		return m.revoke(ctx, token, spender)
	}
	return domain.UnsignedTx{}, errors.New("not implemented")
}

// Ensure mockWallet implements ports.Wallet for compilation.
var _ ports.Wallet = (*mockWallet)(nil)

// mockWallet also needs to implement the other methods of ports.Wallet
func (m *mockWallet) Open(ctx context.Context) error                       { return nil }
func (m *mockWallet) Close() error                                        { return nil }
func (m *mockWallet) Chain() domain.ChainID                              { return domain.ChainBase }
func (m *mockWallet) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	return domain.SignedTx{}, errors.New("not implemented")
}

// mockChain is a mock implementation of ports.Chain for testing.
type mockChain struct {
	multicall func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error)
}

func (m *mockChain) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	if m.multicall != nil {
		return m.multicall(ctx, calls)
	}
	return nil, errors.New("not implemented")
}

// Ensure mockChain implements ports.Chain for compilation.
var _ ports.Chain = (*mockChain)(nil)

// mockChain also needs to implement the other methods of ports.Chain
func (m *mockChain) Info() ports.ChainInfo                                { return ports.ChainInfo{} }
func (m *mockChain) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, errors.New("not implemented")
}
func (m *mockChain) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	return nil, errors.New("not implemented")
}
func (m *mockChain) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, errors.New("not implemented")
}
func (m *mockChain) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, errors.New("not implemented")
}

// TestApproveTracker_Acquire tests acquiring a new approval.
func TestApproveTracker_Acquire(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			// Verify exact amount is being approved
			assert.Equal(t, big.NewInt(1000), amount)
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	approval, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)
	require.NotNil(t, approval)

	assert.Equal(t, token, approval.Token)
	assert.Equal(t, spender, approval.Spender)
	assert.Equal(t, "position-123", approval.Position)
}

// TestApproveTracker_Acquire_ExistingApproval tests that existing sufficient approval is reused.
func TestApproveTracker_Acquire_ExistingApproval(t *testing.T) {
	callCount := 0
	revokeCount := 0
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			callCount++
			return domain.UnsignedTx{}, nil
		},
		revoke: func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
			revokeCount++
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	// First acquisition - creates approval
	_, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)
	assert.Equal(t, 1, callCount, "first call should create approval")

	// Second acquisition with same or less amount - should reuse existing
	_, err = tracker.Acquire(context.Background(), token, spender, big.NewInt(500), "position-123")
	require.NoError(t, err)
	assert.Equal(t, 1, callCount, "second call should reuse existing approval (no new tx)")

	// Third acquisition with same amount - should reuse existing
	_, err = tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)
	assert.Equal(t, 1, callCount, "third call should reuse existing approval (no new tx)")

	// Fourth acquisition with larger amount - should create new approval
	_, err = tracker.Acquire(context.Background(), token, spender, big.NewInt(2000), "position-456")
	require.NoError(t, err)
	assert.Equal(t, 2, callCount, "fourth call should create new approval for increased amount")

	// Verify position link was updated
	approval := tracker.GetApproval(token, spender)
	require.NotNil(t, approval)
	assert.Equal(t, "position-456", approval.Position, "position should be updated to latest")
}

// TestApproveTracker_Acquire_InvalidAmount tests that zero/negative amounts are rejected.
func TestApproveTracker_Acquire_InvalidAmount(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
	}
	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	tests := []struct {
		name  string
		need  *big.Int
	}{
		{"zero amount", big.NewInt(0)},
		{"negative amount", big.NewInt(-100)},
		{"nil amount", nil},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := tracker.Acquire(context.Background(), token, spender, tc.need, "")
			assert.Error(t, err, "should reject invalid amount")
		})
	}
}

// TestApproveTracker_Release tests releasing (revoking) an approval.
func TestApproveTracker_Release(t *testing.T) {
	revokeCalled := false
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
		revoke: func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
			revokeCalled = true
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	// First acquire an approval
	_, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)

	// Verify approval exists
	approval := tracker.GetApproval(token, spender)
	require.NotNil(t, approval)

	// Release the approval
	err = tracker.Release(context.Background(), token, spender)
	require.NoError(t, err)
	assert.True(t, revokeCalled, "revoke should be called")

	// Verify approval is removed from tracker
	approval = tracker.GetApproval(token, spender)
	assert.Nil(t, approval, "approval should be removed after release")
}

// TestApproveTracker_Release_NonExistent tests releasing a non-existent approval.
func TestApproveTracker_Release_NonExistent(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		revoke: func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	// Release without prior acquire - should still work (revoke anyway)
	err := tracker.Release(context.Background(), token, spender)
	require.NoError(t, err)
}

// TestApproveTracker_AuditAll tests auditing all tracked approvals.
func TestApproveTracker_AuditAll(t *testing.T) {
	allowanceValue := big.NewInt(1000)
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{
		multicall: func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
			// Return matching allowance
			data := make([]byte, 32)
			allowanceValue.FillBytes(data)
			return []ports.CallResult{
				{Success: true, Data: data},
			}, nil
		},
	}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	// Acquire an approval with amount 1000
	_, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)

	// Audit should find no issues (on-chain matches tracked)
	findings, err := tracker.AuditAll(context.Background())
	require.NoError(t, err)
	assert.Empty(t, findings, "no findings when on-chain matches tracked")
}

// TestApproveTracker_AuditAll_FindsDiscrepancy tests that audit finds discrepancies.
func TestApproveTracker_AuditAll_FindsDiscrepancy(t *testing.T) {
	// Return a different allowance on-chain than tracked
	onChainAllowance := big.NewInt(500)
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{
		multicall: func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
			data := make([]byte, 32)
			onChainAllowance.FillBytes(data)
			return []ports.CallResult{
				{Success: true, Data: data},
			}, nil
		},
	}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	// Acquire an approval with amount 1000 (tracked)
	_, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(1000), "position-123")
	require.NoError(t, err)

	// Audit should find discrepancy (on-chain is 500, tracked is 1000)
	findings, err := tracker.AuditAll(context.Background())
	require.NoError(t, err)
	assert.Len(t, findings, 1, "should find one discrepancy")
	assert.Equal(t, onChainAllowance, findings[0].OnChain)
}

// TestApproveTracker_CheckAllowance tests querying on-chain allowance.
func TestApproveTracker_CheckAllowance(t *testing.T) {
	expectedAllowance := big.NewInt(123456789)
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
	}

	chain := &mockChain{
		multicall: func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
			// Verify calldata structure
			require.Len(t, calls, 1)
			assert.Len(t, calls[0].Data, 68, "calldata should be 4 bytes selector + 64 bytes args")

			// Return expected allowance
			data := make([]byte, 32)
			expectedAllowance.FillBytes(data)
			return []ports.CallResult{
				{Success: true, Data: data},
			}, nil
		},
	}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	allowance, err := tracker.CheckAllowance(context.Background(), token, spender)
	require.NoError(t, err)
	assert.Equal(t, expectedAllowance, allowance)
}

// TestApproveTracker_CheckAllowance_Error tests error handling on chain query failure.
func TestApproveTracker_CheckAllowance_Error(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
	}

	expectedErr := errors.New("connection refused")
	chain := &mockChain{
		multicall: func(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
			return nil, expectedErr
		},
	}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")

	_, err := tracker.CheckAllowance(context.Background(), token, spender)
	assert.Error(t, err)
}

// TestApproveTracker_GetApprovals tests retrieving all tracked approvals.
func TestApproveTracker_GetApprovals(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
	spender1 := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")
	spender2 := domain.MustParseAddress("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")

	// Initially empty
	approvals := tracker.GetApprovals()
	assert.Empty(t, approvals)

	// Acquire approvals
	_, err := tracker.Acquire(context.Background(), token, spender1, big.NewInt(1000), "position-1")
	require.NoError(t, err)
	_, err = tracker.Acquire(context.Background(), token, spender2, big.NewInt(2000), "position-2")
	require.NoError(t, err)

	// Verify both approvals are tracked
	approvals = tracker.GetApprovals()
	assert.Len(t, approvals, 2)
}

// TestApproveTracker_ConcurrentAccess tests thread safety.
func TestApproveTracker_ConcurrentAccess(t *testing.T) {
	wallet := &mockWallet{
		address: func() domain.Address {
			return domain.MustParseAddress("0x1234567890123456789012345678901234567890")
		},
		approveExact: func(ctx context.Context, token, spender domain.Address, amount *big.Int) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
		revoke: func(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
			return domain.UnsignedTx{}, nil
		},
	}

	chain := &mockChain{}
	tracker := NewApproveTracker(wallet, chain, nil)

	token := domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")

	errors := make(chan error, 100)
	for i := 0; i < 100; i++ {
		go func(idx int) {
			spender := domain.MustParseAddress("0xC36442b4a4522E871399CD717aBDD847Ab11FE88")
			_, err := tracker.Acquire(context.Background(), token, spender, big.NewInt(int64(idx+1)), "")
			errors <- err
		}(i)
	}

	// Collect results
	for i := 0; i < 100; i++ {
		select {
		case err := <-errors:
			require.NoError(t, err, "concurrent access should not cause errors")
		}
	}
}