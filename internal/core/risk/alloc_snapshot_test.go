package risk

import (
	"context"
	"sync"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

// mockPositionRepo is a mock implementation of PositionRepo for testing.
type mockPositionRepo struct {
	positions []*domain.Position
	err       error
	snapMu    sync.Mutex
}

func (m *mockPositionRepo) Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error) {
	m.snapMu.Lock()
	defer m.snapMu.Unlock()
	if m.err != nil {
		return nil, m.err
	}
	var result []*domain.Position
	for _, p := range m.positions {
		if p.PoolID == poolID {
			result = append(result, p)
		}
	}
	return result, nil
}

func (m *mockPositionRepo) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	if m.err != nil {
		return nil, m.err
	}
	for _, p := range m.positions {
		if p.ID == id {
			return p, nil
		}
	}
	return nil, nil
}

func (m *mockPositionRepo) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	return m.Snapshot(ctx, poolID)
}

func (m *mockPositionRepo) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	m.snapMu.Lock()
	defer m.snapMu.Unlock()
	if m.err != nil {
		return nil, m.err
	}
	var result []*domain.Position
	for _, p := range m.positions {
		if p.Chain == chain && p.Status == status {
			result = append(result, p)
		}
	}
	return result, nil
}

func (m *mockPositionRepo) Save(ctx context.Context, pos *domain.Position) error {
	return m.err
}

func (m *mockPositionRepo) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	return m.err
}

// TestAlloc_FreshPool_BelowLimit_OK tests that a fresh pool below limit is allowed.
func TestAlloc_FreshPool_BelowLimit_OK(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{}, // no existing positions
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	c := AllocationCandidate{
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Tier:      domain.TierC,
		AmountUSD: decimal.NewFromInt(30), // $30 under $50 limit
	}

	allowed, reason := m.CheckAllocationWithSnapshot(context.Background(), c)

	if !allowed {
		t.Errorf("fresh pool with $30 should be allowed, got reason %v", reason)
	}
	if reason != AllocReasonOK {
		t.Errorf("expected AllocReasonOK, got %v", reason)
	}
}

// TestAlloc_FreshPool_ExactLimit_OK tests that exact limit ($50) is allowed.
func TestAlloc_FreshPool_ExactLimit_OK(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{}, // no existing positions
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	c := AllocationCandidate{
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Tier:      domain.TierC,
		AmountUSD: decimal.NewFromInt(50), // exactly $50 limit
	}

	allowed, reason := m.CheckAllocationWithSnapshot(context.Background(), c)

	if !allowed {
		t.Errorf("fresh pool with exactly $50 should be allowed, got reason %v", reason)
	}
	if reason != AllocReasonOK {
		t.Errorf("expected AllocReasonOK, got %v", reason)
	}
}

// TestAlloc_FreshPool_OverLimit_Block tests that over limit ($51 > $50) is blocked.
func TestAlloc_FreshPool_OverLimit_Block(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{}, // no existing positions
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	c := AllocationCandidate{
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Tier:      domain.TierC,
		AmountUSD: decimal.NewFromInt(51), // $51 over $50 limit
	}

	allowed, reason := m.CheckAllocationWithSnapshot(context.Background(), c)

	if allowed {
		t.Error("fresh pool with $51 should be blocked")
	}
	if reason != AllocReasonOverPoolLimit {
		t.Errorf("expected AllocReasonOverPoolLimit, got %v", reason)
	}
}

// TestAlloc_ExistingPool_AddBreachesLimit_Block tests that adding to an existing pool breaches limit.
// Existing $30 + new $25 = $55 > $50 limit.
func TestAlloc_ExistingPool_AddBreachesLimit_Block(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{
			{
				ID:        "pos-1",
				PoolID:    "pool-1",
				Chain:     domain.ChainBase,
				Status:    domain.StatusOpen,
				Tier:      domain.TierC,
				AmountUSD: decimal.NewFromInt(30), // existing $30 in pool-1
			},
		},
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	// Adding $25 to a pool that already has $30 = $55 total > $50 limit
	c := AllocationCandidate{
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Tier:      domain.TierC,
		AmountUSD: decimal.NewFromInt(25),
	}

	allowed, reason := m.CheckAllocationWithSnapshot(context.Background(), c)

	if allowed {
		t.Error("existing $30 + new $25 = $55 > $50 should be blocked")
	}
	if reason != AllocReasonOverPoolLimit {
		t.Errorf("expected AllocReasonOverPoolLimit, got %v", reason)
	}
}

// TestAlloc_TotalExposure_OverThirtyPct_Block tests that total exposure > 30% is blocked.
func TestAlloc_TotalExposure_OverThirtyPct_Block(t *testing.T) {
	cfg := AllocationConfig{
		TotalCapitalUSD: decimal.NewFromInt(1000), // total capital $1000
		TierALimit:      decimal.NewFromInt(1000),
		TierBLimit:      decimal.NewFromInt(200),
		TierCLimit:      decimal.NewFromInt(50),
		MaxExposure:     decimal.NewFromFloat(0.30), // 30% = $300
	}
	// Existing allocations = $280
	// Adding $25 would exceed 30% ($305 > $300)
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{
			{
				ID:        "pos-1",
				PoolID:    "pool-1",
				Chain:     domain.ChainBase,
				Status:    domain.StatusOpen,
				Tier:      domain.TierB,
				AmountUSD: decimal.NewFromInt(140),
			},
			{
				ID:        "pos-2",
				PoolID:    "pool-2",
				Chain:     domain.ChainBase,
				Status:    domain.StatusOpen,
				Tier:      domain.TierB,
				AmountUSD: decimal.NewFromInt(140),
			},
		},
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	c := AllocationCandidate{
		PoolID:    "pool-3",
		Chain:     domain.ChainBase,
		Tier:      domain.TierB,
		AmountUSD: decimal.NewFromInt(25), // Would make total = $305 > $300 (30%)
	}

	allowed, reason := m.CheckTotalExposureWithSnapshot(context.Background(), c)

	if allowed {
		t.Error("total exposure over 30% should be blocked")
	}
	if reason != AllocReasonOverTotalExposure {
		t.Errorf("expected AllocReasonOverTotalExposure, got %v", reason)
	}
}

// TestAlloc_RepoError_FailClosed tests that repo errors return false (fail-closed).
func TestAlloc_RepoError_FailClosed(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		err: context.DeadlineExceeded,
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	c := AllocationCandidate{
		PoolID:    "pool-1",
		Chain:     domain.ChainBase,
		Tier:      domain.TierC,
		AmountUSD: decimal.NewFromInt(10),
	}

	allowed, reason := m.CheckAllocationWithSnapshot(context.Background(), c)

	if allowed {
		t.Error("repo error should result in fail-closed (not allowed)")
	}
	if reason != AllocReasonRepoError {
		t.Errorf("expected AllocReasonRepoError, got %v", reason)
	}
}

// TestAlloc_ConcurrentCalls_NoRace tests concurrent calls don't have race conditions.
func TestAlloc_ConcurrentCalls_NoRace(t *testing.T) {
	cfg := AllocationConfig{
		TierCLimit:  decimal.NewFromInt(50),
		MaxExposure: decimal.NewFromFloat(0.30),
	}
	mockRepo := &mockPositionRepo{
		positions: []*domain.Position{},
	}
	m := NewAllocationManagerWithRepo(cfg, mockRepo)

	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c := AllocationCandidate{
				PoolID:    "pool-1",
				Chain:     domain.ChainBase,
				Tier:      domain.TierC,
				AmountUSD: decimal.NewFromInt(10),
			}
			// Just verify it doesn't panic or race
			_, _ = m.CheckAllocationWithSnapshot(context.Background(), c)
			_, _ = m.CheckTotalExposureWithSnapshot(context.Background(), c)
		}(i)
	}
	wg.Wait()
}