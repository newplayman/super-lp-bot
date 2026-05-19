package decimal

import (
	"database/sql/driver"
	"fmt"

	sd "github.com/shopspring/decimal"
)

// Scan implements sql.Scanner.
func (d *Decimal) Scan(src interface{}) error {
	switch v := src.(type) {
	case []byte:
		dec, err := sd.NewFromString(string(v))
		if err != nil {
			return fmt.Errorf("decimal scan: %w", err)
		}
		d.v = dec
	case string:
		dec, err := sd.NewFromString(v)
		if err != nil {
			return fmt.Errorf("decimal scan: %w", err)
		}
		d.v = dec
	default:
		return fmt.Errorf("decimal scan: unsupported type %T", src)
	}
	return nil
}

// Value implements driver.Valuer.
func (d Decimal) Value() (driver.Value, error) {
	return d.String(), nil
}