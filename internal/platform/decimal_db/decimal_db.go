package decimal_db

import (
	"fmt"

	"github.com/lpbot/lpbot/pkg/decimal"
)

// MarshalText serializes a Decimal to TEXT for database storage.
// It implements encoding.TextMarshaler.
func MarshalText(d decimal.Decimal) ([]byte, error) {
	return []byte(d.String()), nil
}

// UnmarshalText deserializes TEXT from database storage into a Decimal.
// It implements encoding.TextUnmarshaler.
func UnmarshalText(data []byte, d *decimal.Decimal) error {
	if d == nil {
		return fmt.Errorf("decimal unmarshal: destination is nil")
	}
	dec, err := decimal.FromString(string(data))
	if err != nil {
		return fmt.Errorf("decimal unmarshal: %w", err)
	}
	*d = dec
	return nil
}
