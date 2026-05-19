package il

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestILToUSD(t *testing.T) {
	tests := []struct {
		name       string
		ilPct      decimal.Decimal
		lpValueUSD decimal.Decimal
		expected   decimal.Decimal
	}{
		{
			name:       "IL -13.4% on $1000 -> loss ~$134",
			ilPct:      decimal.MustFromString("-0.134"),
			lpValueUSD: decimal.FromInt(1000),
			expected:   decimal.MustFromString("-134"),
		},
		{
			name:       "IL -0.1% on $10000 -> loss ~$10",
			ilPct:      decimal.MustFromString("-0.001"),
			lpValueUSD: decimal.FromInt(10000),
			expected:   decimal.MustFromString("-10"),
		},
		{
			name:       "zero IL -> zero loss",
			ilPct:      decimal.Zero,
			lpValueUSD: decimal.FromInt(1000),
			expected:   decimal.Zero,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ILToUSD(tt.ilPct, tt.lpValueUSD)
			diff := result.Sub(tt.expected).Abs()
			if diff.GreaterThan(decimal.MustFromString("0.01")) {
				t.Errorf("ILToUSD(%v, %v) = %v, want %v", tt.ilPct, tt.lpValueUSD, result, tt.expected)
			}
		})
	}
}

func TestNetValueUSD(t *testing.T) {
	tests := []struct {
		name       string
		price0     decimal.Decimal
		price1     decimal.Decimal
		lpValueUSD decimal.Decimal
		expected   decimal.Decimal
	}{
		{
			name:       "price0=1000, price1=500, lpValueUSD=1000 -> USD loss ~-57.2",
			price0:     decimal.FromInt(1000),
			price1:     decimal.FromInt(500),
			lpValueUSD: decimal.FromInt(1000),
			expected:   decimal.MustFromString("942.8"), // 1000 - 57.2 = 942.8
		},
		{
			name:       "price0=1001, price1=1000, lpValueUSD=10000 -> near zero IL",
			price0:     decimal.FromInt(1001),
			price1:     decimal.FromInt(1000),
			lpValueUSD: decimal.FromInt(10000),
			expected:   decimal.MustFromString("9999.9988"), // ~10000, very small IL
		},
		{
			name:       "price0=1000, price1=1000, lpValueUSD=1000 -> no loss",
			price0:     decimal.FromInt(1000),
			price1:     decimal.FromInt(1000),
			lpValueUSD: decimal.FromInt(1000),
			expected:   decimal.FromInt(1000),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := NetValueUSD(tt.price0, tt.price1, tt.lpValueUSD)
			diff := result.Sub(tt.expected).Abs()
			if diff.GreaterThan(decimal.MustFromString("0.01")) {
				t.Errorf("NetValueUSD(%v, %v, %v) = %v, want %v", tt.price0, tt.price1, tt.lpValueUSD, result, tt.expected)
			}
		})
	}
}