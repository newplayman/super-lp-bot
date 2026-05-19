package domain_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestScore_AssignTier(t *testing.T) {
	tests := []struct {
		total  float64
		expect domain.Tier
	}{
		{80, domain.TierA},
		{75, domain.TierA},
		{74.9, domain.TierB},
		{50, domain.TierB},
		{49.9, domain.TierC},
		{0, domain.TierC},
	}
	for _, tc := range tests {
		s := domain.Score{Total: tc.total}
		require.Equal(t, tc.expect, s.AssignTier(), "total=%.1f", tc.total)
	}
}

func TestScore_ComputeTotal(t *testing.T) {
	s := domain.Score{
		FeeAPRScore:     100,
		TvlScore:        100,
		VolScore:        100,
		VolatilityScore: 100,
		SecurityScore:   100,
	}
	s.Total = s.ComputeTotal()
	require.Equal(t, 100.0, s.Total)
}

func TestScore_Empty(t *testing.T) {
	s := domain.Score{}
	require.Equal(t, 0.0, s.Total)
}