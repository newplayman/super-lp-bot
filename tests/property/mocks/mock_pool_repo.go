// Package mocks provides mock implementations of port interfaces for testing.
package mocks

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// MockPoolRepo implements ports.PoolRepo for testing.
type MockPoolRepo struct {
	Pools          map[string]domain.Pool
	ScoreHistory   map[string][]ports.PoolScoreSnapshot
	UpsertPoolHook func(ctx context.Context, pool ports.PoolWithScore) error
	GetPoolHook    func(ctx context.Context, key string) (domain.Pool, error)
	ListPoolsHook  func(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error)
}

func NewMockPoolRepo() *MockPoolRepo {
	return &MockPoolRepo{
		Pools:        make(map[string]domain.Pool),
		ScoreHistory: make(map[string][]ports.PoolScoreSnapshot),
	}
}

func (m *MockPoolRepo) UpsertPool(ctx context.Context, pool ports.PoolWithScore) error {
	if m.UpsertPoolHook != nil {
		return m.UpsertPoolHook(ctx, pool)
	}
	key := pool.Pool.Key()
	m.Pools[key] = pool.Pool
	m.ScoreHistory[key] = append(m.ScoreHistory[key], ports.PoolScoreSnapshot{
		PoolKey:  key,
		Tier:     pool.Pool.Tier_,
		Score:    pool.Score,
		Timestamp: 0,
	})
	return nil
}

func (m *MockPoolRepo) GetPool(ctx context.Context, key string) (domain.Pool, error) {
	if m.GetPoolHook != nil {
		return m.GetPoolHook(ctx, key)
	}
	pool, ok := m.Pools[key]
	if !ok {
		return domain.Pool{}, ports.ErrPoolNotFound
	}
	return pool, nil
}

func (m *MockPoolRepo) ListPools(ctx context.Context, filter ports.PoolFilter) ([]domain.Pool, error) {
	if m.ListPoolsHook != nil {
		return m.ListPoolsHook(ctx, filter)
	}
	var result []domain.Pool
	for _, pool := range m.Pools {
		if filter.Chain != "" && pool.Chain != filter.Chain {
			continue
		}
		if filter.Tier != "" && pool.Tier_ != filter.Tier {
			continue
		}
		result = append(result, pool)
	}
	return result, nil
}

func (m *MockPoolRepo) GetScoreHistory(ctx context.Context, poolKey string, limit int) ([]ports.PoolScoreSnapshot, error) {
	history, ok := m.ScoreHistory[poolKey]
	if !ok {
		return nil, nil
	}
	if limit > 0 && len(history) > limit {
		return history[len(history)-limit:], nil
	}
	return history, nil
}

func (m *MockPoolRepo) UpsertAuditVerdict(ctx context.Context, poolKey string, verdict domain.AuditVerdict, riskScore float64) error {
	pool, ok := m.Pools[poolKey]
	if !ok {
		return ports.ErrPoolNotFound
	}
	pool.UpdatedAt = 0 // Placeholder for audit timestamp
	m.Pools[poolKey] = pool
	return nil
}