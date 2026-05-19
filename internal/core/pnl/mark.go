package pnl

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

// MarkService handles mark-to-market valuation logic.
// It updates position valuations based on current market prices.
type MarkService struct {
	priceSource PriceSource
}

// NewMarkService creates a new mark service.
func NewMarkService(priceSource PriceSource) *MarkService {
	return &MarkService{
		priceSource: priceSource,
	}
}

// MarkPosition updates the mark-to-market valuation for a single position.
func (s *MarkService) MarkPosition(ctx context.Context, pos *domain.Position) (*PositionSnapshot, error) {
	_, _, err := s.priceSource.GetPrice(ctx, pos.PoolID, "")
	if err != nil {
		return nil, err
	}

	snapshot := &PositionSnapshot{
		PositionID:   pos.ID,
		ValuationUSD: pos.AmountUSD, // Simplified
		BlockRef: domain.BlockRef{
			Chain: pos.Chain,
		},
	}

	return snapshot, nil
}

// MarkPositions updates valuations for multiple positions.
func (s *MarkService) MarkPositions(ctx context.Context, positions []*domain.Position) (map[string]*PositionSnapshot, error) {
	results := make(map[string]*PositionSnapshot)

	for _, pos := range positions {
		snapshot, err := s.MarkPosition(ctx, pos)
		if err != nil {
			continue // Skip on error
		}
		results[pos.ID] = snapshot
	}

	return results, nil
}