package il

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestSimFeeGrowth(t *testing.T) {
	tests := []struct {
		name          string
		volumeUSD     decimal.Decimal
		totalLiquidity decimal.Decimal
		feeTierBPS    decimal.Decimal
		expected      decimal.Decimal
	}{
		{
			name:          "fee=30bps, volume=1M, liquidity=5M -> 0.0006",
			volumeUSD:     decimal.FromInt(1000000),
			totalLiquidity: decimal.FromInt(5000000),
			feeTierBPS:    decimal.FromInt(30),
			expected:      decimal.MustFromString("0.0006"),
		},
		{
			name:          "fee=100bps (1%), volume=1M, liquidity=1M -> 0.01",
			volumeUSD:     decimal.FromInt(1000000),
			totalLiquidity: decimal.FromInt(1000000),
			feeTierBPS:    decimal.FromInt(100),
			expected:      decimal.MustFromString("0.01"),
		},
		{
			name:          "zero volume -> zero fee",
			volumeUSD:     decimal.Zero,
			totalLiquidity: decimal.FromInt(1000000),
			feeTierBPS:    decimal.FromInt(30),
			expected:      decimal.Zero,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := SimFeeGrowth(tt.volumeUSD, tt.totalLiquidity, tt.feeTierBPS)
			diff := result.Sub(tt.expected).Abs()
			if diff.GreaterThan(decimal.MustFromString("0.0001")) {
				t.Errorf("SimFeeGrowth() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestFeeAPR24h(t *testing.T) {
	tests := []struct {
		name         string
		feeVolume24h decimal.Decimal
		tvlUSD       decimal.Decimal
		expected     decimal.Decimal
	}{
		{
			name:         "fee=100, tvl=10000 -> 3.65 APR",
			feeVolume24h: decimal.FromInt(100),
			tvlUSD:       decimal.FromInt(10000),
			expected:     decimal.MustFromString("3.65"),
		},
		{
			name:         "zero fee -> zero APR",
			feeVolume24h: decimal.Zero,
			tvlUSD:       decimal.FromInt(10000),
			expected:     decimal.Zero,
		},
		{
			name:         "zero tvl -> zero APR (div by zero protection)",
			feeVolume24h: decimal.FromInt(100),
			tvlUSD:       decimal.Zero,
			expected:     decimal.Zero,
		},
		{
			name:         "fee=50, tvl=5000 -> 3.65 APR",
			feeVolume24h: decimal.FromInt(50),
			tvlUSD:       decimal.FromInt(5000),
			expected:     decimal.MustFromString("3.65"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := FeeAPR24h(tt.feeVolume24h, tt.tvlUSD)
			diff := result.Sub(tt.expected).Abs()
			if diff.GreaterThan(decimal.MustFromString("0.01")) {
				t.Errorf("FeeAPR24h() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestUncollectedFees(t *testing.T) {
	tests := []struct {
		name           string
		feeGrowthInside decimal.Decimal
		feeGrowthLast   decimal.Decimal
		liquidity       decimal.Decimal
		expected        decimal.Decimal
	}{
		{
			name:           "growth increased by 0.001, liquidity=1000 -> 1 fee",
			feeGrowthInside: decimal.MustFromString("0.001"),
			feeGrowthLast:   decimal.Zero,
			liquidity:       decimal.FromInt(1000),
			expected:        decimal.FromInt(1),
		},
		{
			name:           "no growth change -> zero uncollected",
			feeGrowthInside: decimal.FromInt(1),
			feeGrowthLast:   decimal.FromInt(1),
			liquidity:       decimal.FromInt(1000),
			expected:        decimal.Zero,
		},
		{
			name:           "negative growth (theoretical) -> negative fees",
			feeGrowthInside: decimal.Zero,
			feeGrowthLast:   decimal.MustFromString("0.001"),
			liquidity:       decimal.FromInt(1000),
			expected:        decimal.MustFromString("-1"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := UncollectedFees(tt.feeGrowthInside, tt.feeGrowthLast, tt.liquidity)
			diff := result.Sub(tt.expected).Abs()
			if diff.GreaterThan(decimal.MustFromString("0.0001")) {
				t.Errorf("UncollectedFees() = %v, want %v", result, tt.expected)
			}
		})
	}
}