// Package scanner provides pool discovery and scoring functionality.
// See spec §3.1.
package scanner

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Scanner scans candidate pools and publishes scored events.
type Scanner interface {
	// Run starts the scanner loop. It blocks until ctx is cancelled.
	Run(ctx context.Context) error

	// Score evaluates a pool and returns its score.
	Score(ctx context.Context, p domain.Pool) (domain.Score, error)

	// AssignTier derives a Tier from a score.
	AssignTier(s domain.Score) domain.Tier
}

// PoolScorer calculates scores for pools.
type PoolScorer interface {
	Score(ctx context.Context, pool domain.Pool) (domain.Score, error)
}

// Config holds scanner configuration.
type Config struct {
	// Datasource is used to discover pools.
	Datasource ports.Datasource
	// Chain to scan.
	Chain domain.ChainID
	// MinTVLUSD minimum TVL in USD to consider a pool.
	MinTVLUSD domain.Decimal
	// ScanInterval between scans.
	ScanInterval time.Duration
	// Logger for debug output.
	Logger *slog.Logger
}

// defaultScanner implements Scanner using a Datasource.
type defaultScanner struct {
	config Config
}

// New creates a new Scanner with the given configuration.
func New(cfg Config) Scanner {
	if cfg.ScanInterval == 0 {
		cfg.ScanInterval = 5 * time.Minute
	}
	if cfg.MinTVLUSD.IsZero() {
		cfg.MinTVLUSD = domain.MustDecimal("10000") // $10k minimum TVL
	}
	return &defaultScanner{config: cfg}
}

// Run starts the scanner loop to continuously discover and score pools.
func (s *defaultScanner) Run(ctx context.Context) error {
	if s.config.Datasource == nil {
		return fmt.Errorf("datasource is required")
	}

	ticker := time.NewTicker(s.config.ScanInterval)
	defer ticker.Stop()

	// Initial scan
	if err := s.scanOnce(ctx); err != nil {
		s.log("initial scan failed: %v", err)
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if err := s.scanOnce(ctx); err != nil {
				s.log("scan failed: %v", err)
			}
		}
	}
}

// scanOnce performs a single scan of the configured chain.
func (s *defaultScanner) scanOnce(ctx context.Context) error {
	pools, err := s.config.Datasource.DiscoverPools(ctx, s.config.Chain, "", s.config.MinTVLUSD, 100)
	if err != nil {
		return fmt.Errorf("discover pools: %w", err)
	}

	s.log("discovered %d pools", len(pools))

	// Score each pool
	for _, discovery := range pools {
		pool := domain.Pool{
			ID:        discovery.ID,
			Chain:     discovery.Chain,
			Protocol:  discovery.Protocol,
			Token0:    discovery.Token0,
			Token1:    discovery.Token1,
			TVLUSD:    discovery.TVLUSD,
			Vol24h:    discovery.Vol24h,
			UpdatedAt: discovery.UpdatedAt.Unix(),
		}

		score, err := s.Score(ctx, pool)
		if err != nil {
			s.log("score pool %s failed: %v", pool.ID, err)
			continue
		}

		tier := s.AssignTier(score)
		pool.Tier_ = tier

		s.log("pool %s: score=%.2f tier=%s tvl=%s vol=%s",
			pool.ID, score.Total, tier, pool.TVLUSD, pool.Vol24h)
	}

	return nil
}

// Score evaluates a pool and returns its score (0-100).
func (s *defaultScanner) Score(ctx context.Context, p domain.Pool) (domain.Score, error) {
	score := domain.Score{
		// TVL score: higher is better, cap at $10M
		TvlScore: normalizeScore(p.TVLUSD.String(), 0, 10_000_000),

		// Volume score: higher is better, cap at $1M/day
		VolScore: normalizeScore(p.Vol24h.String(), 0, 1_000_000),

		// Fee APR score: derive from TVL and volume ratio
		// Higher volume relative to TVL = better fee APR
		FeeAPRScore: calculateFeeAPRScore(p.TVLUSD, p.Vol24h),

		// Volatility score: lower is more stable
		// Pools with very high TVL tend to be more stable
		VolatilityScore: calculateVolatilityScore(p.TVLUSD, p.Vol24h),

		// Security score: based on TVL (higher TVL = more established = safer)
		SecurityScore: calculateSecurityScore(p.TVLUSD),
	}

	score.Total = score.ComputeTotal()
	return score, nil
}

// AssignTier derives a Tier from the total score.
func (s *defaultScanner) AssignTier(score domain.Score) domain.Tier {
	return score.AssignTier()
}

func (s *defaultScanner) log(format string, args ...any) {
	if s.config.Logger != nil {
		s.config.Logger.Debug(fmt.Sprintf("scanner: "+format, args...))
	}
}

// normalizeScore normalizes a value to a 0-100 score.
// value: string representation of decimal value
// min, max: the range to normalize within
func normalizeScore(value string, min, max float64) float64 {
	v, err := parseFloat(value)
	if err != nil {
		return 0
	}

	if v <= min {
		return 0
	}
	if v >= max {
		return 100
	}

	return (v - min) / (max - min) * 100
}

func parseFloat(s string) (float64, error) {
	var f float64
	_, err := fmt.Sscanf(s, "%f", &f)
	return f, err
}

// calculateFeeAPRScore estimates fee APR from TVL and volume.
// Fee APR ≈ (daily volume × fee rate) / TVL × 365
// Assuming 0.3% fee for V3 pools
func calculateFeeAPRScore(tvl, vol domain.Decimal) float64 {
	if tvl.IsZero() {
		return 0
	}

	feeRate := 0.003 // 0.3% fee
	dailyFeeIncome := vol.Mul(domain.NewDecimalFromFloat(feeRate))
	estimatedAPR := dailyFeeIncome.Div(tvl).Mul(domain.MustDecimal("365"))

	// Convert to 0-100 score (100 = 100%+ APR)
	aprFloat, _ := estimatedAPR.Float64()
	score := aprFloat * 10 // 10% APR = 100 score
	if score > 100 {
		score = 100
	}
	return score
}

// calculateVolatilityScore based on TVL to volume ratio.
// Higher TVL relative to volume = more stable
func calculateVolatilityScore(tvl, vol domain.Decimal) float64 {
	if vol.IsZero() {
		return 50 // neutral if no volume data
	}

	ratio := tvl.Div(vol)
	ratioFloat, _ := ratio.Float64()

	// Higher ratio = more stable = higher score
	// 10:1 ratio = very stable (score 100)
	// 1:1 ratio = very volatile (score 10)
	score := ratioFloat * 10
	if score > 100 {
		score = 100
	}
	if score < 0 {
		score = 0
	}
	return score
}

// calculateSecurityScore based on TVL.
// Higher TVL = more established = safer
func calculateSecurityScore(tvl domain.Decimal) float64 {
	// Minimum TVL for any score
	minTVL := 10_000.0 // $10k
	maxTVL := 50_000_000.0 // $50M for max score

	return normalizeScore(tvl.String(), minTVL, maxTVL)
}