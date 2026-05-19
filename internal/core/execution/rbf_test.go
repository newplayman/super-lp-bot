package execution_test

import (
	"context"
	"errors"
	"math/big"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/core/execution"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// mockEVMChain is a mock implementation of ports.EVMChain.
type mockEVMChain struct {
	chainInfo      ports.ChainInfo
	nonceFunc      func(ctx context.Context) (uint64, error)
	suggestGasFunc func(ctx context.Context) (*big.Int, *big.Int, error)
}

func (m *mockEVMChain) Info() ports.ChainInfo { return m.chainInfo }
func (m *mockEVMChain) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, nil
}
func (m *mockEVMChain) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) { return nil, nil }
func (m *mockEVMChain) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, nil
}
func (m *mockEVMChain) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, nil
}
func (m *mockEVMChain) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	return nil, nil
}
func (m *mockEVMChain) NonceAt(ctx context.Context, addr domain.Address, ref domain.BlockRef) (uint64, error) {
	return 0, nil
}
func (m *mockEVMChain) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	if m.nonceFunc != nil {
		return m.nonceFunc(ctx)
	}
	return 0, nil
}
func (m *mockEVMChain) SuggestGasFees(ctx context.Context) (*big.Int, *big.Int, error) {
	if m.suggestGasFunc != nil {
		return m.suggestGasFunc(ctx)
	}
	return big.NewInt(1000000000), big.NewInt(1000000000), nil // 1 gwei base, 1 gwei tip
}

// mockWallet for RBF tests
type mockWalletRBF struct {
	address domain.Address
	chain   domain.ChainID
}

func (m *mockWalletRBF) Open(ctx context.Context) error                            { return nil }
func (m *mockWalletRBF) Close() error                                              { return nil }
func (m *mockWalletRBF) Address() domain.Address                                   { return m.address }
func (m *mockWalletRBF) Chain() domain.ChainID                                     { return m.chain }
func (m *mockWalletRBF) Sign(ctx context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	return domain.SignedTx{UnsignedTx: tx, Hash: "mock-hash-" + string(tx.Chain)}, nil
}
func (m *mockWalletRBF) ApproveExact(ctx context.Context, token, spender domain.Address, amount *big.Int) (
	domain.UnsignedTx, error,
) {
	return domain.UnsignedTx{}, nil
}
func (m *mockWalletRBF) Revoke(ctx context.Context, token, spender domain.Address) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}

// mockNonceManager for RBF tests
type mockNonceManagerRBF struct {
	getNextNonceFunc func(ctx context.Context) (uint64, error)
	acknowledgeFunc   func(ctx context.Context, nonce uint64, txHash string)
}

func (m *mockNonceManagerRBF) GetNextNonce(ctx context.Context) (uint64, error) {
	if m.getNextNonceFunc != nil {
		return m.getNextNonceFunc(ctx)
	}
	return 0, nil
}
func (m *mockNonceManagerRBF) AcknowledgeNonce(ctx context.Context, nonce uint64, txHash string) {
	if m.acknowledgeFunc != nil {
		m.acknowledgeFunc(ctx, nonce, txHash)
	}
}
func (m *mockNonceManagerRBF) GetPendingNonces(ctx context.Context) ([]uint64, error) {
	return nil, nil
}
func (m *mockNonceManagerRBF) IsNonceAvailable(ctx context.Context, nonce uint64) (bool, error) {
	return true, nil
}
func (m *mockNonceManagerRBF) InitializeNonce(ctx context.Context) error { return nil }
func (m *mockNonceManagerRBF) ClearPending(nonce uint64)                  {}
func (m *mockNonceManagerRBF) CurrentNonce() uint64                       { return 0 }
func (m *mockNonceManagerRBF) IsInitialized() bool                        { return true }

// TestRBFManager_IsStuck tests the stuck transaction detection.
func TestRBFManager_IsStuck(t *testing.T) {
	ctx := context.Background()

	// Create mock chain
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	// Create real nonce manager for testing
	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	// Create RBF manager with short stuck timeout for testing
	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   1 * time.Second,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Initially, no transactions should be stuck
	isStuck, err := rbf.IsStuck(ctx, "0xtxhash1")
	if err != nil {
		t.Fatalf("IsStuck should not return error: %v", err)
	}
	if isStuck {
		t.Error("Transaction should not be stuck (not tracked)")
	}
}

// TestRBFManager_CanRBF_MaxAttempts tests the max attempts limit.
func TestRBFManager_CanRBF_MaxAttempts(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   1 * time.Hour,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	txHash := "0xtxhash-max-attempts"

	// First attempt should be allowed
	canRBF, err := rbf.CanRBF(ctx, txHash)
	if err != nil {
		t.Fatalf("CanRBF should not return error: %v", err)
	}
	if !canRBF {
		t.Error("First attempt should be allowed")
	}

	// Record 3 attempts (max) - RecordAttempt takes just txHash now
	rbf.RecordAttempt(txHash)
	rbf.RecordAttempt(txHash)
	rbf.RecordAttempt(txHash)

	// Now canRBF should return false
	canRBF, err = rbf.CanRBF(ctx, txHash)
	if err != nil {
		t.Fatalf("CanRBF should not return error: %v", err)
	}
	if canRBF {
		t.Error("RBF should not be allowed after max attempts (3)")
	}
}

// TestRBFManager_AttemptRBF_Success tests successful RBF attempt.
func TestRBFManager_AttemptRBF_Success(t *testing.T) {
	ctx := context.Background()
	currentNonce := uint64(42)

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
		suggestGasFunc: func(ctx context.Context) (*big.Int, *big.Int, error) {
			// Return 1 gwei base fee, 2 gwei tip
			return big.NewInt(1000000000), big.NewInt(2000000000), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	// Initialize nonce
	_ = nonceMgr.InitializeNonce(ctx)

	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   1 * time.Hour,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	originalTx := domain.UnsignedTx{
		Chain:  domain.ChainBase,
		From:   walletAddr,
		To:     domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:   []byte{0x01, 0x02, 0x03},
		Value:  domain.MustDecimal("0"),
		Nonce:  currentNonce,
	}

	// Attempt RBF - should create new transaction with higher gas
	replacementTx, err := rbf.AttemptRBFWithOriginal(ctx, "0xoriginal-tx-hash", originalTx)
	if err != nil {
		t.Fatalf("AttemptRBF should not return error: %v", err)
	}

	if replacementTx == nil {
		t.Fatal("Replacement transaction should not be nil")
	}

	// Verify the replacement uses same nonce
	if replacementTx.Nonce != currentNonce {
		t.Errorf("Replacement tx nonce should be %d, got %d", currentNonce, replacementTx.Nonce)
	}
}

// TestRBFManager_AttemptRBF_MaxAttemptsExceeded tests that RBF fails after max attempts.
func TestRBFManager_AttemptRBF_MaxAttemptsExceeded(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   1 * time.Hour,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	txHash := "0xtxhash-exceeded"

	// Record 3 attempts
	rbf.RecordAttempt(txHash)
	rbf.RecordAttempt(txHash)
	rbf.RecordAttempt(txHash)

	// CanRBF should return false (max attempts exceeded)
	canRBF, err := rbf.CanRBF(ctx, txHash)
	if err != nil {
		t.Fatalf("CanRBF should not return error: %v", err)
	}
	if canRBF {
		t.Error("RBF should not be allowed after max attempts exceeded")
	}

	// GetRBFAttempts should return 3
	attempts := rbf.GetRBFAttempts(txHash)
	if attempts != 3 {
		t.Errorf("RBF attempts should be 3, got %d", attempts)
	}
}

// TestRBFManager_GasIncrease tests that gas price is increased correctly.
func TestRBFManager_GasIncrease(t *testing.T) {
	ctx := context.Background()

	// Set up chain with specific gas fees
	originalBaseFee := int64(1000000000)  // 1 gwei
	originalTip := int64(1000000000)      // 1 gwei

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
		suggestGasFunc: func(ctx context.Context) (*big.Int, *big.Int, error) {
			return big.NewInt(originalBaseFee), big.NewInt(originalTip), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0, // 25% increase
		StuckTimeout:   1 * time.Hour,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	originalTx := domain.UnsignedTx{
		Chain:  domain.ChainBase,
		From:   walletAddr,
		Nonce:  42,
	}

	// Attempt RBF
	replacementTx, err := rbf.AttemptRBFWithOriginal(ctx, "0xgas-increase-tx", originalTx)
	if err != nil {
		t.Fatalf("AttemptRBF should not return error: %v", err)
	}

	// With 25% increase, the gas should be higher
	// Original: 1 gwei base + 1 gwei tip = 2 gwei total
	// With 25% increase: 1.25 gwei base + 1.25 gwei tip = 2.5 gwei total
	expectedTip := int64(1250000000)   // 1.25 gwei
	_ = expectedTip

	// Check that the new gas values are higher
	if replacementTx.Priority == nil {
		t.Error("Replacement tx should have Priority set")
	} else if replacementTx.Priority.Cmp(big.NewInt(expectedTip)) != 0 {
		t.Errorf("Priority tip should be %d, got %s", expectedTip, replacementTx.Priority.String())
	}

	if replacementTx.BaseFee == nil {
		t.Error("Replacement tx should have BaseFee set")
	}
}

// TestRBFManager_DefaultConfig tests default configuration.
func TestRBFManager_DefaultConfig(t *testing.T) {
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	// Create with default config
	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	if rbf == nil {
		t.Fatal("RBF manager should not be nil")
	}

	// Verify defaults
	if config.MaxAttempts != 3 {
		t.Errorf("Default MaxAttempts should be 3, got %d", config.MaxAttempts)
	}
	if config.GasIncreasePct != 25.0 {
		t.Errorf("Default GasIncreasePct should be 25.0, got %f", config.GasIncreasePct)
	}
	if config.StuckTimeout != 5*time.Minute {
		t.Errorf("Default StuckTimeout should be 5 minutes, got %v", config.StuckTimeout)
	}
}

// TestRBFManager_GetRBFAttempts tests getting attempt count for unknown tx.
func TestRBFManager_GetRBFAttempts(t *testing.T) {
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Unknown transaction should return 0 attempts
	attempts := rbf.GetRBFAttempts("0xunknown-tx")
	if attempts != 0 {
		t.Errorf("Unknown transaction should have 0 attempts, got %d", attempts)
	}
}

// TestRBFManager_CanRBF_UnknownTx tests CanRBF for unknown transaction.
func TestRBFManager_CanRBF_UnknownTx(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Unknown transaction should be able to RBF (not tracked = can try)
	canRBF, err := rbf.CanRBF(ctx, "0xunknown-tx")
	if err != nil {
		t.Fatalf("CanRBF should not return error: %v", err)
	}
	if !canRBF {
		t.Error("Unknown transaction should be able to RBF")
	}
}

// TestRBFManager_IsStuck_BelowTimeout tests stuck detection below timeout.
func TestRBFManager_IsStuck_BelowTimeout(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	// Use 1 hour timeout
	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   1 * time.Hour,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Transaction tracked but last attempt was just now
	rbf.RecordAttempt("0xrecent-tx")

	// Should not be stuck (timeout is 1 hour)
	isStuck, err := rbf.IsStuck(ctx, "0xrecent-tx")
	if err != nil {
		t.Fatalf("IsStuck should not return error: %v", err)
	}
	if isStuck {
		t.Error("Recent transaction should not be stuck")
	}
}

// TestRBFManager_IsStuck_AboveTimeout tests stuck detection above timeout.
func TestRBFManager_IsStuck_AboveTimeout(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	// Use short timeout (10ms for testing)
	config := execution.RBFConfig{
		MaxAttempts:    3,
		GasIncreasePct: 25.0,
		StuckTimeout:   10 * time.Millisecond,
	}
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Record an attempt and wait
	rbf.RecordAttempt("0xold-tx")

	// Wait for timeout to pass
	time.Sleep(20 * time.Millisecond)

	// Now should be stuck
	isStuck, err := rbf.IsStuck(ctx, "0xold-tx")
	if err != nil {
		t.Fatalf("IsStuck should not return error: %v", err)
	}
	if !isStuck {
		t.Error("Old transaction should be stuck after timeout")
	}
}

// TestRBFManager_ConcurrentAccess tests thread safety.
func TestRBFManager_ConcurrentAccess(t *testing.T) {
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Test concurrent access to GetRBFAttempts
	done := make(chan bool)
	for i := 0; i < 10; i++ {
		go func(id int) {
			for j := 0; j < 100; j++ {
				txHash := "0xconcurrent-tx-" + string(rune('0'+id%10))
				rbf.GetRBFAttempts(txHash)
				if j%2 == 0 {
					rbf.RecordAttempt(txHash)
				}
			}
			done <- true
		}(i)
	}

	// Wait for all goroutines
	for i := 0; i < 10; i++ {
		<-done
	}
}

// TestRBFManager_ClearAttempts tests clearing attempts.
func TestRBFManager_ClearAttempts(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	txHash := "0xtxhash-clear"

	// Record some attempts
	rbf.RecordAttempt(txHash)
	rbf.RecordAttempt(txHash)

	// Verify attempts
	attempts := rbf.GetRBFAttempts(txHash)
	if attempts != 2 {
		t.Errorf("Expected 2 attempts, got %d", attempts)
	}

	// Clear attempts
	rbf.ClearAttempts(txHash)

	// Verify cleared
	attempts = rbf.GetRBFAttempts(txHash)
	if attempts != 0 {
		t.Errorf("Expected 0 attempts after clear, got %d", attempts)
	}

	// CanRBF should be allowed now
	canRBF, err := rbf.CanRBF(ctx, txHash)
	if err != nil {
		t.Fatalf("CanRBF should not return error: %v", err)
	}
	if !canRBF {
		t.Error("CanRBF should be allowed after clearing attempts")
	}
}

// TestRBFManager_NonceReuse tests that RBF reuses the same nonce.
func TestRBFManager_NonceReuse(t *testing.T) {
	ctx := context.Background()

	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
		suggestGasFunc: func(ctx context.Context) (*big.Int, *big.Int, error) {
			return big.NewInt(1000000000), big.NewInt(1000000000), nil
		},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	originalNonce := uint64(100)
	originalTx := domain.UnsignedTx{
		Chain:  domain.ChainBase,
		From:   walletAddr,
		Nonce:  originalNonce,
	}

	// Multiple RBF attempts should use same nonce
	// Note: AttemptRBFWithOriginal already increments attempts internally,
	// so we only call it 3 times (which is the max)
	for i := 0; i < 3; i++ {
		replacementTx, err := rbf.AttemptRBFWithOriginal(ctx, "0xtxhash-nonce-test", originalTx)
		if err != nil {
			t.Fatalf("AttemptRBF attempt %d failed: %v", i+1, err)
		}

		if replacementTx.Nonce != originalNonce {
			t.Errorf("RBF attempt %d should reuse nonce %d, got %d", i+1, originalNonce, replacementTx.Nonce)
		}
	}

	// After 3 attempts, we should be at max
	attempts := rbf.GetRBFAttempts("0xtxhash-nonce-test")
	if attempts != 3 {
		t.Errorf("Should have 3 attempts, got %d", attempts)
	}

	// 4th attempt should fail
	_, err := rbf.AttemptRBFWithOriginal(ctx, "0xtxhash-nonce-test", originalTx)
	if err == nil {
		t.Error("4th attempt should fail due to max attempts exceeded")
	}
}

// TestRBFManager_GetState tests getting the state of a transaction.
func TestRBFManager_GetState(t *testing.T) {
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	txHash := "0xtxhash-state"

	// Initially, state should not exist
	attempts, lastAttempt, exists := rbf.GetState(txHash)
	if exists {
		t.Error("State should not exist for unknown transaction")
	}
	if attempts != 0 {
		t.Errorf("Attempts should be 0, got %d", attempts)
	}

	// Record an attempt
	rbf.RecordAttempt(txHash)

	// Now state should exist
	attempts, lastAttempt, exists = rbf.GetState(txHash)
	if !exists {
		t.Error("State should exist after recording attempt")
	}
	if attempts != 1 {
		t.Errorf("Attempts should be 1, got %d", attempts)
	}
	if lastAttempt.IsZero() {
		t.Error("LastAttempt should not be zero")
	}
}

// TestRBFManager_AttemptRBF_Error tests error handling in AttemptRBF.
func TestRBFManager_AttemptRBF_Error(t *testing.T) {
	ctx := context.Background()

	// Chain that returns error on SuggestGasFees
	chain := &mockEVMChain{
		chainInfo: ports.ChainInfo{ID: domain.ChainBase},
		suggestGasFunc: func(ctx context.Context) (*big.Int, *big.Int, error) {
			return nil, nil, errors.New("gas fees unavailable")
		},
	}

	walletAddr := domain.MustParseAddress("0x0000000000000000000000000000000000000001")
	nonceMgr := execution.NewNonceManager(chain, walletAddr)

	config := execution.DefaultRBFConfig()
	rbf := execution.NewRBFManager(config, chain, nonceMgr)

	// Attempt RBF should fail
	_, err := rbf.AttemptRBF(ctx, "0xtxhash-error")
	if err == nil {
		t.Error("AttemptRBF should return error when gas fees fail")
	}
}

// TestRBFManager_ToUnsignedTx tests conversion of ReplacementTx to UnsignedTx.
func TestRBFManager_ToUnsignedTx(t *testing.T) {
	rt := &execution.ReplacementTx{
		Chain:    domain.ChainBase,
		Nonce:    42,
		BaseFee:  big.NewInt(1000000000),
		Priority: big.NewInt(2000000000),
	}

	tx := rt.ToUnsignedTx()

	if tx.Chain != domain.ChainBase {
		t.Errorf("Chain should be base, got %s", tx.Chain)
	}
	if tx.Nonce != 42 {
		t.Errorf("Nonce should be 42, got %d", tx.Nonce)
	}
}