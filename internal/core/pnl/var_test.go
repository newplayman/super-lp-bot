package pnl

import (
	"testing"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestVaR_CalculateVaR_Success(t *testing.T) {
	tests := []struct {
		name            string
		returns         []decimal.Decimal
		confidenceLevel float64
		expectedVaR     string // expected VaR as string for decimal comparison
	}{
		{
			name: "basic VaR calculation with 95% confidence",
			returns: []decimal.Decimal{
				decimal.NewFromFloat(-0.10), // worst loss
				decimal.NewFromFloat(-0.08),
				decimal.NewFromFloat(-0.05),
				decimal.NewFromFloat(-0.03),
				decimal.NewFromFloat(-0.01),
				decimal.NewFromFloat(0.02),
				decimal.NewFromFloat(0.05),
				decimal.NewFromFloat(0.08),
				decimal.NewFromFloat(0.10),
				decimal.NewFromFloat(0.15),
			},
			confidenceLevel: 0.95,
			expectedVaR:     "0.10", // 5th percentile of 10 returns = 0.10
		},
		{
			name: "VaR with exact percentile match",
			returns: []decimal.Decimal{
				decimal.NewFromFloat(-0.05),
				decimal.NewFromFloat(-0.04),
				decimal.NewFromFloat(-0.03),
				decimal.NewFromFloat(-0.02),
				decimal.NewFromFloat(-0.01),
				decimal.NewFromFloat(0.01),
				decimal.NewFromFloat(0.02),
				decimal.NewFromFloat(0.03),
				decimal.NewFromFloat(0.04),
				decimal.NewFromFloat(0.05),
			},
			confidenceLevel: 0.95,
			expectedVaR:     "0.05", // 5th percentile = 5%
		},
		{
			name: "VaR with all positive returns",
			returns: []decimal.Decimal{
				decimal.NewFromFloat(0.01),
				decimal.NewFromFloat(0.02),
				decimal.NewFromFloat(0.03),
				decimal.NewFromFloat(0.04),
				decimal.NewFromFloat(0.05),
			},
			confidenceLevel: 0.95,
			expectedVaR:     "0.01", // lowest return = 1%
		},
		{
			name: "VaR with mostly positive but some negative",
			returns: []decimal.Decimal{
				decimal.NewFromFloat(-0.02),
				decimal.NewFromFloat(0.01),
				decimal.NewFromFloat(0.02),
				decimal.NewFromFloat(0.03),
				decimal.NewFromFloat(0.04),
				decimal.NewFromFloat(0.05),
				decimal.NewFromFloat(0.06),
				decimal.NewFromFloat(0.07),
				decimal.NewFromFloat(0.08),
				decimal.NewFromFloat(0.09),
				decimal.NewFromFloat(0.10),
			},
			confidenceLevel: 0.95,
			expectedVaR:     "0.02", // 5th percentile = 2%
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			config := VaRConfig{
				ConfidenceLevel: tt.confidenceLevel,
				LookbackDays:    90,
				WarnThreshold:   decimal.NewFromFloat(0.08),
				KillThreshold:   decimal.NewFromFloat(0.12),
			}

			result, err := CalculateVaR(tt.returns, config)
			require.NoError(t, err)

			expectedVaR := decimal.RequireFromString(tt.expectedVaR)
			assert.True(t, result.VaR.Equal(expectedVaR),
				"VaR = %s, expected = %s", result.VaR.String(), expectedVaR.String())
			assert.Equal(t, tt.confidenceLevel, result.Confidence)
			assert.Equal(t, 90, result.Lookback)
			assert.False(t, result.UpdatedAt.IsZero())
		})
	}
}

func TestVaR_CalculateVaR_EmptyReturns(t *testing.T) {
	config := VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08),
		KillThreshold:   decimal.NewFromFloat(0.12),
	}

	returns := []decimal.Decimal{}

	result, err := CalculateVaR(returns, config)

	assert.ErrorIs(t, err, ErrEmptyReturns)
	assert.True(t, result.VaR.IsZero())
}

func TestVaR_GetVaRLevel_Kill(t *testing.T) {
	config := VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08), // 8%
		KillThreshold:   decimal.NewFromFloat(0.12), // 12%
	}

	// Test cases that should trigger kill
	killCases := []struct {
		name  string
		varVa string
	}{
		{name: "VaR at 13%", varVa: "0.13"},
		{name: "VaR at 20%", varVa: "0.20"},
		{name: "VaR at 50%", varVa: "0.50"},
	}

	for _, tt := range killCases {
		t.Run(tt.name, func(t *testing.T) {
			varValue := decimal.RequireFromString(tt.varVa)
			level := GetVaRLevel(varValue, config)
			assert.Equal(t, ports.KillLevelKill, level, "VaR of %s should trigger kill", tt.varVa)
		})
	}
}

func TestVaR_GetVaRLevel_Warn(t *testing.T) {
	config := VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08), // 8%
		KillThreshold:   decimal.NewFromFloat(0.12), // 12%
	}

	tests := []struct {
		name  string
		varVa string
	}{
		{name: "VaR at 9%", varVa: "0.09"},
		{name: "VaR at 10%", varVa: "0.10"},
		{name: "VaR at 11.99%", varVa: "0.1199"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			varValue := decimal.RequireFromString(tt.varVa)
			level := GetVaRLevel(varValue, config)
			assert.Equal(t, ports.KillLevelWarn, level, "VaR of %s should trigger warn", tt.varVa)
		})
	}
}

func TestVaR_GetVaRLevel_OK(t *testing.T) {
	config := VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08), // 8%
		KillThreshold:   decimal.NewFromFloat(0.12), // 12%
	}

	tests := []struct {
		name  string
		varVa string
	}{
		{name: "VaR at 0%", varVa: "0"},
		{name: "VaR at 1%", varVa: "0.01"},
		{name: "VaR at 5%", varVa: "0.05"},
		{name: "VaR at 7.99%", varVa: "0.0799"},
		{name: "VaR at exactly warn threshold (not greater than)", varVa: "0.08"},
		// Note: VaR at exactly 12% is greater than warn threshold (8%), so it's warn, not kill
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			varValue := decimal.RequireFromString(tt.varVa)
			level := GetVaRLevel(varValue, config)
			assert.Equal(t, ports.KillLevelOK, level, "VaR of %s should be OK", tt.varVa)
		})
	}
}

func TestVaR_DefaultVaRConfig(t *testing.T) {
	config := DefaultVaRConfig()

	assert.Equal(t, 0.95, config.ConfidenceLevel)
	assert.Equal(t, 90, config.LookbackDays)
	assert.True(t, config.WarnThreshold.Equal(decimal.NewFromFloat(0.08)))
	assert.True(t, config.KillThreshold.Equal(decimal.NewFromFloat(0.12)))
}

func TestVaR_CalculateVaR_LargeSample(t *testing.T) {
	// Generate 365 daily returns for a full year of data
	returns := make([]decimal.Decimal, 365)
	// Simulate mostly positive returns with occasional drawdowns
	for i := range returns {
		switch {
		case i%100 == 0:
			returns[i] = decimal.NewFromFloat(-0.05) // major drawdown every ~100 days
		case i%20 == 0:
			returns[i] = decimal.NewFromFloat(-0.02) // smaller drawdown every ~20 days
		case i%5 == 0:
			returns[i] = decimal.NewFromFloat(-0.01) // small loss every 5 days
		default:
			returns[i] = decimal.NewFromFloat(0.001) // small daily gains
		}
	}

	config := VaRConfig{
		ConfidenceLevel: 0.95,
		LookbackDays:    365,
		WarnThreshold:   decimal.NewFromFloat(0.08),
		KillThreshold:   decimal.NewFromFloat(0.12),
	}

	result, err := CalculateVaR(returns, config)
	require.NoError(t, err)

	// 95% VaR with 365 returns: index = ceil(0.05 * 365) - 1 = 19 - 1 = 18
	// We have 3 returns at -0.05 (i=0,100,200), 17 at -0.02 (i=20,40,...,340)
	// Index 18 is within the -0.02 group (indices 3-19 are -0.02)
	assert.True(t, result.VaR.Equal(decimal.NewFromFloat(0.02)),
		"Expected VaR of 2%%, got %s", result.VaR.String())
}

func TestVaR_EdgeCases(t *testing.T) {
	config := VaRConfig{
		ConfidenceLevel: 0.99,
		LookbackDays:    90,
		WarnThreshold:   decimal.NewFromFloat(0.08),
		KillThreshold:   decimal.NewFromFloat(0.12),
	}

	t.Run("single return", func(t *testing.T) {
		returns := []decimal.Decimal{decimal.NewFromFloat(-0.05)}
		result, err := CalculateVaR(returns, config)
		require.NoError(t, err)
		assert.True(t, result.VaR.Equal(decimal.NewFromFloat(0.05)))
	})

	t.Run("two returns", func(t *testing.T) {
		returns := []decimal.Decimal{
			decimal.NewFromFloat(-0.03),
			decimal.NewFromFloat(0.05),
		}
		result, err := CalculateVaR(returns, config)
		require.NoError(t, err)
		// 99% VaR with 2 returns: index = 0.01 * 2 = 0.02 -> index 0
		assert.True(t, result.VaR.Equal(decimal.NewFromFloat(0.03)))
	})
}