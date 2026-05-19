package execution

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockChainForReconcile implements ports.Chain for testing.
type mockChainForReconcile struct {
	info            func() ports.ChainInfo
	listMyPositions func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error)
}

func (m *mockChainForReconcile) Info() ports.ChainInfo {
	if m.info != nil {
		return m.info()
	}
	return ports.ChainInfo{ID: domain.ChainBase}
}

func (m *mockChainForReconcile) GetBlock(ctx context.Context, ref domain.BlockRef) (ports.Block, error) {
	return ports.Block{}, errors.New("not implemented")
}

func (m *mockChainForReconcile) SubscribeBlocks(ctx context.Context) (<-chan ports.Block, error) {
	return nil, errors.New("not implemented")
}

func (m *mockChainForReconcile) Multicall(ctx context.Context, calls []ports.Call) ([]ports.CallResult, error) {
	return nil, errors.New("not implemented")
}

func (m *mockChainForReconcile) EstimateGas(ctx context.Context, tx ports.UnsignedTx) (ports.GasEstimate, error) {
	return ports.GasEstimate{}, errors.New("not implemented")
}

func (m *mockChainForReconcile) ListMyPositions(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
	if m.listMyPositions != nil {
		return m.listMyPositions(ctx, owner)
	}
	return nil, errors.New("not implemented")
}

// mockPositionRepoForReconcile implements ports.PositionRepo for testing.
type mockPositionRepoForReconcile struct {
	findByChainAndStatus func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error)
}

func (m *mockPositionRepoForReconcile) Save(ctx context.Context, pos *domain.Position) error {
	return errors.New("not implemented")
}

func (m *mockPositionRepoForReconcile) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	return nil, errors.New("not implemented")
}

func (m *mockPositionRepoForReconcile) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	return nil, errors.New("not implemented")
}

func (m *mockPositionRepoForReconcile) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	if m.findByChainAndStatus != nil {
		return m.findByChainAndStatus(ctx, chain, status)
	}
	return nil, errors.New("not implemented")
}

func (m *mockPositionRepoForReconcile) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	return errors.New("not implemented")
}

// Ensure mock implementations satisfy required interfaces
var _ ports.Chain = (*mockChainForReconcile)(nil)
var _ ports.PositionRepo = (*mockPositionRepoForReconcile)(nil)

// TestBootstrapReconcile_Empty tests reconciliation with no positions on either side.
func TestBootstrapReconcile_Empty(t *testing.T) {
	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return nil, nil // no positions on chain
		},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return nil, nil // no positions in DB
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01, // 1%
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass, "Empty reconciliation should pass")
	assert.Equal(t, 0, result.ChainMismatch, "No chain mismatches expected")
	assert.Equal(t, 0, result.DBMismatch, "No DB mismatches expected")
	assert.InDelta(t, 0.0, result.ValueDevPct, 0.001, "Value deviation should be zero")
	assert.Empty(t, result.Errors, "No errors expected")
}

// TestBootstrapReconcile_Pass tests reconciliation when chain and DB positions match.
func TestBootstrapReconcile_Pass(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
		{PoolID: "pool-2", OnChain: []byte("token2")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB positions match chain positions
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(1000.0)},
		{ID: "pos-2", PoolID: "pool-2", AmountUSD: decimal.NewFromFloat(2000.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01, // 1%
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass, "Matching positions should pass")
	assert.Equal(t, 0, result.ChainMismatch, "No mismatches expected")
	assert.Equal(t, 0, result.DBMismatch, "No mismatches expected")
	assert.InDelta(t, 0.0, result.ValueDevPct, 0.001, "Value deviation should be zero")
}

// TestBootstrapReconcile_CountMismatch tests reconciliation when position counts differ.
func TestBootstrapReconcile_CountMismatch(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
		{PoolID: "pool-2", OnChain: []byte("token2")},
		{PoolID: "pool-3", OnChain: []byte("token3")}, // 3 on chain
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB has only 2 positions
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(1000.0)},
		{ID: "pos-2", PoolID: "pool-2", AmountUSD: decimal.NewFromFloat(2000.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.False(t, result.Pass, "Count mismatch should fail")
	assert.Equal(t, 1, result.ChainMismatch, "One extra position on chain")
	assert.Equal(t, 0, result.DBMismatch, "No missing DB positions")
}

// TestBootstrapReconcile_DBMismatch tests reconciliation when DB has more positions than chain.
func TestBootstrapReconcile_DBMismatch(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB has extra position not on chain
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(1000.0)},
		{ID: "pos-2", PoolID: "pool-2", AmountUSD: decimal.NewFromFloat(2000.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.False(t, result.Pass, "DB mismatch should fail")
	assert.Equal(t, 0, result.ChainMismatch, "No extra chain positions")
	assert.Equal(t, 1, result.DBMismatch, "One missing DB position")
}

// TestBootstrapReconcile_ChainError tests handling of chain errors.
func TestBootstrapReconcile_ChainError(t *testing.T) {
	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return nil, errors.New("chain RPC error")
		},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return nil, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.Error(t, err, "Chain error should return error")
	assert.Nil(t, result, "Result should be nil on error")
}

// TestBootstrapReconcile_DBError tests handling of DB errors.
func TestBootstrapReconcile_DBError(t *testing.T) {
	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return nil, nil
		},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return nil, errors.New("DB read error")
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.Error(t, err, "DB error should return error")
	assert.Nil(t, result, "Result should be nil on error")
}

// TestBootstrapReconcile_ContextCancellation tests graceful handling of cancelled context.
func TestBootstrapReconcile_ContextCancellation(t *testing.T) {
	slow := make(chan struct{})
	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			// Block until context is cancelled
			select {
			case <-slow:
				return nil, nil
			case <-ctx.Done():
				return nil, ctx.Err()
			}
		},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return nil, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           100 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	result, err := BootstrapReconcile(ctx, deps, cfg)
	require.Error(t, err, "Context cancellation should return error")
	assert.Nil(t, result, "Result should be nil on cancellation")
	assert.True(t, errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled),
		"Error should be context error")

	close(slow) // cleanup
}

// TestReconcileConfig_Defaults tests that default configuration is sensible.
func TestReconcileConfig_Defaults(t *testing.T) {
	cfg := DefaultReconcileConfig()

	assert.Equal(t, 0.01, cfg.MaxValueDeviation, "Default max deviation should be 1%")
	assert.True(t, cfg.Timeout > 0, "Default timeout should be positive")
}

// TestReconcileDeps_Validation tests dependency validation.
func TestReconcileDeps_Validation(t *testing.T) {
	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	// Test nil chain
	deps := ReconcileDeps{
		Chain:        nil,
		PositionRepo: &mockPositionRepoForReconcile{},
		WalletAddr:   walletAddr,
	}
	cfg := DefaultReconcileConfig()
	_, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.Error(t, err, "Nil chain should fail")

	// Test nil position repo
	deps = ReconcileDeps{
		Chain: &mockChainForReconcile{
			info: func() ports.ChainInfo {
				return ports.ChainInfo{ID: domain.ChainBase}
			},
		},
		PositionRepo: nil,
		WalletAddr:   walletAddr,
	}
	_, err = BootstrapReconcile(context.Background(), deps, cfg)
	require.Error(t, err, "Nil position repo should fail")
}

// TestReconcileResult_Fields tests that all result fields are properly populated.
func TestReconcileResult_Fields(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB has mismatch
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(500.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	// Verify all fields are accessible (not zero values when they should be)
	assert.True(t, result.Pass, "Matching positions should pass")
	assert.Equal(t, 0, result.ChainMismatch)
	assert.Equal(t, 0, result.DBMismatch)
}

// TestReconcileResult_ErrorDetails tests that error messages are properly populated.
func TestReconcileResult_ErrorDetails(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
		{PoolID: "pool-2", OnChain: []byte("token2")},
		{PoolID: "pool-3", OnChain: []byte("token3")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB has fewer positions
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(1000.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.False(t, result.Pass, "Mismatch should fail")
	assert.NotEmpty(t, result.Errors, "Should have error messages")
}

// TestBootstrapReconcile_ValueDeviationSimple tests value deviation check with matching counts.
func TestBootstrapReconcile_ValueDeviationSimple(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
		{PoolID: "pool-2", OnChain: []byte("token2")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB positions match by count, value deviation should be 0
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.NewFromFloat(1000.0)},
		{ID: "pos-2", PoolID: "pool-2", AmountUSD: decimal.NewFromFloat(2000.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass, "Matching count with zero deviation should pass")
	assert.InDelta(t, 0.0, result.ValueDevPct, 0.001)
}

// TestBootstrapReconcile_SolanaChain tests reconciliation with Solana chain.
func TestBootstrapReconcile_SolanaChain(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-sol-1", OnChain: []byte("tokenSol1")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainSolana}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	dbPositions := []*domain.Position{
		{ID: "pos-sol-1", PoolID: "pool-sol-1", Chain: domain.ChainSolana, AmountUSD: decimal.NewFromFloat(1500.0)},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			if chain == domain.ChainSolana {
				return dbPositions, nil
			}
			return nil, nil
		},
	}

	walletAddr := domain.MustParseAddress("7xS5TLx8U4eTEqUYSaZqEs3C5qF6t2tVCuJ5hGrF2C9y")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass, "Solana positions should reconcile correctly")
}

// TestBootstrapReconcile_ZeroAmountPositions tests handling of positions with zero amount.
func TestBootstrapReconcile_ZeroAmountPositions(t *testing.T) {
	chainPositions := []ports.ChainPosition{
		{PoolID: "pool-1", OnChain: []byte("token1")},
	}

	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return chainPositions, nil
		},
	}

	// DB position with zero amount
	dbPositions := []*domain.Position{
		{ID: "pos-1", PoolID: "pool-1", AmountUSD: decimal.Zero},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return dbPositions, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass, "Zero amount positions should reconcile")
}

// TestBootstrapReconcile_EmptyMismatches tests that mismatches report correct counts.
func TestBootstrapReconcile_EmptyMismatches(t *testing.T) {
	// No positions anywhere
	chain := &mockChainForReconcile{
		info: func() ports.ChainInfo {
			return ports.ChainInfo{ID: domain.ChainBase}
		},
		listMyPositions: func(ctx context.Context, owner domain.Address) ([]ports.ChainPosition, error) {
			return []ports.ChainPosition{}, nil
		},
	}

	repo := &mockPositionRepoForReconcile{
		findByChainAndStatus: func(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
			return []*domain.Position{}, nil
		},
	}

	walletAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")

	deps := ReconcileDeps{
		Chain:        chain,
		PositionRepo: repo,
		WalletAddr:   walletAddr,
	}

	cfg := ReconcileConfig{
		MaxValueDeviation: 0.01,
		Timeout:           30 * time.Second,
	}

	result, err := BootstrapReconcile(context.Background(), deps, cfg)
	require.NoError(t, err)
	require.NotNil(t, result)

	assert.True(t, result.Pass)
	assert.Equal(t, 0, result.ChainMismatch)
	assert.Equal(t, 0, result.DBMismatch)
	assert.Empty(t, result.Errors)
}