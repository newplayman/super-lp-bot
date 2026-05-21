package scanner_test

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockDatasource implements ports.Datasource for testing.
type mockDatasource struct {
	pools []ports.PoolDiscovery
	err   error
}

func (m *mockDatasource) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.pools, nil
}

func (m *mockDatasource) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, nil
}

func (m *mockDatasource) HealthCheck(ctx context.Context) error {
	return nil
}

func TestScanner_New(t *testing.T) {
	cfg := scanner.Config{
		MinTVLUSD:    domain.MustDecimal("10000"),
		ScanInterval: time.Minute,
	}
	s := scanner.New(cfg)
	require.NotNil(t, s)
}

func TestScanner_Score(t *testing.T) {
	cfg := scanner.Config{
		MinTVLUSD: domain.MustDecimal("10000"),
	}
	s := scanner.New(cfg)

	pool := domain.Pool{
		ID:     "0x123",
		Chain:  domain.ChainBase,
		TVLUSD: domain.MustDecimal("100000"), // $100k TVL
		Vol24h: domain.MustDecimal("50000"),  // $50k volume
	}

	score, err := s.Score(context.Background(), pool)
	require.NoError(t, err)
	require.NotNil(t, score)

	// Score should be > 0
	assert.Greater(t, score.Total, 0.0)

	// Component scores should be in 0-100 range
	assert.GreaterOrEqual(t, score.TvlScore, 0.0)
	assert.LessOrEqual(t, score.TvlScore, 100.0)
	assert.GreaterOrEqual(t, score.VolScore, 0.0)
	assert.LessOrEqual(t, score.VolScore, 100.0)
	assert.GreaterOrEqual(t, score.FeeAPRScore, 0.0)
	assert.LessOrEqual(t, score.FeeAPRScore, 100.0)
	assert.GreaterOrEqual(t, score.VolatilityScore, 0.0)
	assert.LessOrEqual(t, score.VolatilityScore, 100.0)
	assert.GreaterOrEqual(t, score.SecurityScore, 0.0)
	assert.LessOrEqual(t, score.SecurityScore, 100.0)
}

func TestScanner_Score_DifferentPools(t *testing.T) {
	cfg := scanner.Config{}
	s := scanner.New(cfg)

	tests := []struct {
		name    string
		tvlUSD  string
		vol24h  string
		wantMin float64
		wantMax float64
	}{
		{"Low TVL pool", "1000", "500", 0, 30},
		{"Medium TVL pool", "100000", "50000", 0, 100},
		{"High TVL pool", "10000000", "1000000", 0, 100},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pool := domain.Pool{
				ID:     "test-pool",
				Chain:  domain.ChainBase,
				TVLUSD: domain.MustDecimal(tt.tvlUSD),
				Vol24h: domain.MustDecimal(tt.vol24h),
			}

			score, err := s.Score(context.Background(), pool)
			require.NoError(t, err)
			assert.Greater(t, score.Total, tt.wantMin)
			assert.LessOrEqual(t, score.Total, tt.wantMax)
		})
	}
}

func TestScanner_AssignTier(t *testing.T) {
	cfg := scanner.Config{}
	s := scanner.New(cfg)

	tests := []struct {
		totalScore float64
		wantTier   domain.Tier
	}{
		{80, domain.TierA},
		{75, domain.TierA},
		{74, domain.TierB},
		{50, domain.TierB},
		{49, domain.TierC},
		{0, domain.TierC},
	}

	for _, tt := range tests {
		t.Run(tt.wantTier.String(), func(t *testing.T) {
			score := domain.Score{Total: tt.totalScore}
			tier := s.AssignTier(score)
			assert.Equal(t, tt.wantTier, tier)
		})
	}
}

func TestScanner_Run(t *testing.T) {
	pools := []ports.PoolDiscovery{
		{
			ID:       "pool-1",
			Chain:    domain.ChainBase,
			Protocol: "aerodrome",
			TVLUSD:   domain.MustDecimal("100000"),
			Vol24h:   domain.MustDecimal("50000"),
		},
		{
			ID:       "pool-2",
			Chain:    domain.ChainBase,
			Protocol: "aerodrome",
			TVLUSD:   domain.MustDecimal("50000"),
			Vol24h:   domain.MustDecimal("20000"),
		},
	}

	cfg := scanner.Config{
		Datasource:   &mockDatasource{pools: pools},
		Chain:        domain.ChainBase,
		MinTVLUSD:    domain.ZeroDecimal(),
		ScanInterval: time.Hour, // Long interval for test
	}

	s := scanner.New(cfg)

	// Run with context that cancels after short delay
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	// Should not panic, should return context cancellation
	err := s.Run(ctx)
	assert.ErrorIs(t, err, context.DeadlineExceeded)
}

func TestScanner_Run_NoDatasource(t *testing.T) {
	cfg := scanner.Config{
		Datasource:   nil,
		ScanInterval: time.Hour,
	}

	s := scanner.New(cfg)

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	err := s.Run(ctx)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "datasource is required")
}

func TestScanner_Run_DatasourceError(t *testing.T) {
	cfg := scanner.Config{
		Datasource:   &mockDatasource{err: assert.AnError},
		Chain:        domain.ChainBase,
		ScanInterval: time.Hour,
	}

	s := scanner.New(cfg)

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	err := s.Run(ctx)
	assert.Error(t, err)
}

func TestScanner_Interface(t *testing.T) {
	// Compile-time interface check
	var _ scanner.Scanner = (*scannerImpl)(nil)
}

// scannerImpl implements scanner.Scanner for interface check.
type scannerImpl struct{}

func (s *scannerImpl) Run(ctx context.Context) error { return nil }
func (s *scannerImpl) ScanOnce(ctx context.Context) ([]scanner.ScoredPool, error) {
	return nil, nil
}
func (s *scannerImpl) Score(ctx context.Context, p domain.Pool) (domain.Score, error) {
	return domain.Score{}, nil
}
func (s *scannerImpl) AssignTier(score domain.Score) domain.Tier {
	return domain.TierC
}
