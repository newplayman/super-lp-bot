package il

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestILV2(t *testing.T) {
	tests := []struct {
		name     string
		price0   decimal.Decimal
		price1   decimal.Decimal
		expected decimal.Decimal
	}{
		{
			name:     "price0 equals price1 -> IL=0",
			price0:   decimal.FromInt(1000),
			price1:   decimal.FromInt(1000),
			expected: decimal.Zero,
		},
		{
			name:     "price0=1000, price1=500 -> IL ≈ -5.72%",
			price0:   decimal.FromInt(1000),
			price1:   decimal.FromInt(500),
			expected: decimal.MustFromString("-0.0572"),
		},
		{
			name:     "price0=1000, price1=2000 -> IL ≈ -5.72%",
			price0:   decimal.FromInt(1000),
			price1:   decimal.FromInt(2000),
			expected: decimal.MustFromString("-0.0572"),
		},
		{
			name:     "price0=1000, price1=2500 -> IL ≈ -9.65%",
			price0:   decimal.FromInt(1000),
			price1:   decimal.FromInt(2500),
			expected: decimal.MustFromString("-0.0965"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			il := ILV2(tt.price0, tt.price1)
			// Use approximate comparison for floating point
			diff := il.Sub(tt.expected).Abs()
			// Allow 0.001 tolerance (0.1%)
			if diff.GreaterThan(decimal.MustFromString("0.001")) {
				t.Errorf("ILV2(%v, %v) = %v, want %v", tt.price0, tt.price1, il, tt.expected)
			}
		})
	}
}