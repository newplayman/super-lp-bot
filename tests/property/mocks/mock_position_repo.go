package mocks

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// MockPositionRepo implements ports.PositionRepo for testing.
type MockPositionRepo struct {
	Positions      map[string]*domain.Position
	SaveHook       func(ctx context.Context, pos *domain.Position) error
	FindByIDHook   func(ctx context.Context, id string) (*domain.Position, error)
	UpdateStatusHook func(ctx context.Context, id string, status domain.PositionStatus) error
}

func NewMockPositionRepo() *MockPositionRepo {
	return &MockPositionRepo{
		Positions: make(map[string]*domain.Position),
	}
}

func (m *MockPositionRepo) Save(ctx context.Context, pos *domain.Position) error {
	if m.SaveHook != nil {
		return m.SaveHook(ctx, pos)
	}
	m.Positions[pos.ID] = pos
	return nil
}

func (m *MockPositionRepo) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	if m.FindByIDHook != nil {
		return m.FindByIDHook(ctx, id)
	}
	pos, ok := m.Positions[id]
	if !ok {
		return nil, nil
	}
	return pos, nil
}

func (m *MockPositionRepo) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	var result []*domain.Position
	for _, pos := range m.Positions {
		if pos.PoolID == poolID && pos.Status == status {
			result = append(result, pos)
		}
	}
	return result, nil
}

func (m *MockPositionRepo) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	var result []*domain.Position
	for _, pos := range m.Positions {
		if pos.Chain == chain && pos.Status == status {
			result = append(result, pos)
		}
	}
	return result, nil
}

func (m *MockPositionRepo) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	if m.UpdateStatusHook != nil {
		return m.UpdateStatusHook(ctx, id, status)
	}
	pos, ok := m.Positions[id]
	if !ok {
		return nil // Treat as no-op for mock
	}
	if !pos.Status.CanTransitionTo(status) {
		return nil // Treat as no-op for mock
	}
	pos.Status = status
	return nil
}

func (m *MockPositionRepo) Snapshot(ctx context.Context, poolID string) ([]*domain.Position, error) {
	var result []*domain.Position
	for _, pos := range m.Positions {
		if pos.PoolID == poolID {
			result = append(result, pos)
		}
	}
	return result, nil
}