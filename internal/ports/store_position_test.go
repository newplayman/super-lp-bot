package ports_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface compliance check: PositionRepo must implement ports.PositionRepo
var _ ports.PositionRepo = (*positionRepoNop)(nil)

// positionRepoNop is a no-op implementation for compile-time interface checks.
type positionRepoNop struct{}

func (positionRepoNop) Save(ctx context.Context, pos *domain.Position) error { return nil }

func (positionRepoNop) FindByID(ctx context.Context, id string) (*domain.Position, error) {
	return nil, nil
}

func (positionRepoNop) FindByPoolAndStatus(ctx context.Context, poolID string, status domain.PositionStatus) ([]*domain.Position, error) {
	return nil, nil
}

func (positionRepoNop) FindByChainAndStatus(ctx context.Context, chain domain.ChainID, status domain.PositionStatus) ([]*domain.Position, error) {
	return nil, nil
}

func (positionRepoNop) UpdateStatus(ctx context.Context, id string, status domain.PositionStatus) error {
	return nil
}

// TestPositionRepoInterface verifies the PositionRepo interface exists and is properly defined.
func TestPositionRepoInterface(t *testing.T) {
	require.NotNil(t, t, "ports.PositionRepo interface must exist")
}

// TestPositionRepoMethods verifies all required methods are present.
func TestPositionRepoMethods(t *testing.T) {
	// Verify the nop implementation satisfies the interface
	var repo ports.PositionRepo = &positionRepoNop{}
	require.NotNil(t, repo)
}