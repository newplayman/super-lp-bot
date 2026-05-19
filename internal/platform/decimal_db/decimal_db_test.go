package decimal_db_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/platform/decimal_db"
	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/stretchr/testify/require"
)

func TestMarshalText(t *testing.T) {
	tests := []struct {
		name     string
		input    decimal.Decimal
		expected string
	}{
		{
			name:     "zero",
			input:    decimal.Zero,
			expected: "0",
		},
		{
			name:     "positive integer",
			input:    decimal.MustFromString("123"),
			expected: "123",
		},
		{
			name:     "positive decimal",
			input:    decimal.MustFromString("123.456"),
			expected: "123.456",
		},
		{
			name:     "negative decimal",
			input:    decimal.MustFromString("-987.654"),
			expected: "-987.654",
		},
		{
			name:     "large number",
			input:    decimal.MustFromString("1000000000000.000001"),
			expected: "1000000000000.000001",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := decimal_db.MarshalText(tt.input)
			require.NoError(t, err)
			require.Equal(t, tt.expected, string(got))
		})
	}
}

func TestUnmarshalText(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected decimal.Decimal
	}{
		{
			name:     "zero",
			input:    "0",
			expected: decimal.Zero,
		},
		{
			name:     "positive integer",
			input:    "123",
			expected: decimal.MustFromString("123"),
		},
		{
			name:     "positive decimal",
			input:    "123.456",
			expected: decimal.MustFromString("123.456"),
		},
		{
			name:     "negative decimal",
			input:    "-987.654",
			expected: decimal.MustFromString("-987.654"),
		},
		{
			name:     "large number",
			input:    "1000000000000.000001",
			expected: decimal.MustFromString("1000000000000.000001"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var d decimal.Decimal
			err := decimal_db.UnmarshalText([]byte(tt.input), &d)
			require.NoError(t, err)
			require.True(t, tt.expected.Equal(d), "expected %s, got %s", tt.expected.String(), d.String())
		})
	}
}

func TestUnmarshalTextError(t *testing.T) {
	var d decimal.Decimal
	err := decimal_db.UnmarshalText([]byte("not-a-number"), &d)
	require.Error(t, err)
}

func TestRoundTrip(t *testing.T) {
	original := decimal.MustFromString("12345.6789")
	data, err := decimal_db.MarshalText(original)
	require.NoError(t, err)

	var restored decimal.Decimal
	err = decimal_db.UnmarshalText(data, &restored)
	require.NoError(t, err)
	require.True(t, original.Equal(restored), "round-trip failed: %s != %s", original.String(), restored.String())
}
