package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestTier_Parse(t *testing.T) {
	tA, _ := domain.ParseTier("A")
	require.Equal(t, domain.TierA, tA)
	tB, _ := domain.ParseTier("b")
	require.Equal(t, domain.TierB, tB)
	tC, _ := domain.ParseTier("C")
	require.Equal(t, domain.TierC, tC)
	_, err := domain.ParseTier("D")
	require.Error(t, err)
}

func TestTier_TierThresholds(t *testing.T) {
	tA := domain.TierThresholdsFor(domain.TierA)
	require.Equal(t, "0.03", tA.ILStopPct.String())
	require.Equal(t, "1000", tA.MaxPerPoolUSD.String())

	tB := domain.TierThresholdsFor(domain.TierB)
	require.Equal(t, "0.05", tB.ILStopPct.String())

	tC := domain.TierThresholdsFor(domain.TierC)
	require.Equal(t, "0.08", tC.ILStopPct.String())
}

func TestTier_ThresholdsOrdered(t *testing.T) {
	// IL thresholds should be A < B < C (more risk tolerance)
	tA := domain.TierThresholdsFor(domain.TierA)
	tB := domain.TierThresholdsFor(domain.TierB)
	tC := domain.TierThresholdsFor(domain.TierC)

	require.True(t, tA.ILStopPct.LessThan(tB.ILStopPct), "A IL < B IL")
	require.True(t, tB.ILStopPct.LessThan(tC.ILStopPct), "B IL < C IL")
}

func TestTier_MaxExposure(t *testing.T) {
	// Tier A can expose more than Tier C
	tA := domain.TierThresholdsFor(domain.TierA)
	tC := domain.TierThresholdsFor(domain.TierC)
	require.True(t, tA.MaxPerPoolUSD.GreaterThan(tC.MaxPerPoolUSD))
}