package decimal

import (
	"fmt"
	"math/big"
	sd "github.com/shopspring/decimal"
)

const Precision = 36

var Zero = Decimal{sd.Zero}
var One = Decimal{sd.NewFromInt(1)}

type Decimal struct{ v sd.Decimal }

func FromString(s string) (Decimal, error) {
	d, err := sd.NewFromString(s)
	if err != nil {
		return Decimal{}, fmt.Errorf("decimal parse: %w", err)
	}
	return Decimal{v: d}, nil
}

func MustFromString(s string) Decimal {
	d, err := FromString(s)
	if err != nil {
		panic(err)
	}
	return d
}

func FromInt(i int64) Decimal { return Decimal{v: sd.NewFromInt(i)} }

func FromBigInt(i *big.Int) Decimal { return Decimal{v: sd.NewFromBigInt(i, 0)} }

// pow10 returns 10^n for n >= 0
func pow10(n int64) int64 {
	r := int64(1)
	for i := int64(0); i < n; i++ {
		r *= 10
	}
	return r
}

func (d Decimal) String() string { return d.v.String() }

func (d Decimal) IsZero() bool      { return d.v.IsZero() }
func (d Decimal) IsNeg() bool        { return d.v.IsNegative() }
func (d Decimal) IsPositive() bool  { return d.v.IsPositive() }

// IntPart returns the integer component of the decimal as int64.
func (d Decimal) IntPart() int64 { return d.v.IntPart() }

// MulFrac multiplies by a fraction (numerator/denominator)
func (d Decimal) MulFrac(num, denom int64) Decimal {
	if denom == 0 {
		return Zero
	}
	return Decimal{v: d.v.Mul(sd.NewFromInt(num)).Div(sd.NewFromInt(denom))}
}
