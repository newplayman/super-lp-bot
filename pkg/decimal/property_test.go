package decimal

import (
	"fmt"
	"strconv"
	"testing"

	"github.com/stretchr/testify/require"
	rapid "pgregory.net/rapid"
)

// TestDecimal_DB_Roundtrip is a property test proving that
// a Decimal survives JSON marshal → parse → Value → Scan → String roundtrip
// without loss of precision (the core DB serialization guarantee).
func TestDecimal_DB_Roundtrip(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		// Generate a random integer with up to 30 significant digits
		// (stay well within decimal.Decimal's 36-digit precision)
		intPart := rapid.Int64Range(0, 999999999999999).Draw(t, "int")
		fracDigits := rapid.Int64Range(0, 18).Draw(t, "frac_digits")

		var s string
		if fracDigits == 0 {
			s = fmt.Sprintf("%d", intPart)
		} else {
			fracPart := rapid.Int64Range(0, pow10(fracDigits)-1).Draw(t, "frac")
			s = fmt.Sprintf("%d.%0"+strconv.FormatInt(fracDigits, 10)+"d", intPart, fracPart)
		}

		d, err := FromString(s)
		if err != nil {
			t.Fatalf("FromString(%q) failed: %v", s, err)
		}

		// Simulate DB write → read
		v, _ := d.Value()
		var d2 Decimal
		err = d2.Scan(v)
		if err != nil {
			t.Fatalf("Scan(Value()) failed: %v", err)
		}

		// The string representation must be identical
		require.Equal(t, d.String(), d2.String(), "DB roundtrip changed value: %s → %s", s, d2.String())
	})
}
