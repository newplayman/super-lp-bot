package scanner

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

type defaultScanner struct{}

func New() Scanner { return &defaultScanner{} }

func (s *defaultScanner) Run(ctx context.Context) error {
	panic("not implemented: T-301 (Phase 1)")
}

func (s *defaultScanner) Score(ctx context.Context, p domain.Pool) (domain.Score, error) {
	panic("not implemented: T-302 (Phase 1)")
}

func (s *defaultScanner) AssignTier(s2 domain.Score) domain.Tier {
	panic("not implemented: T-303 (Phase 1)")
}