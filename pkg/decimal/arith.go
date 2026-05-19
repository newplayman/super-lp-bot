package decimal

import (
	"fmt"

	sd "github.com/shopspring/decimal"
)

func (d Decimal) Add(other Decimal) Decimal {
	return Decimal{v: d.v.Add(other.v)}
}

func (d Decimal) Sub(other Decimal) Decimal {
	return Decimal{v: d.v.Sub(other.v)}
}

func (d Decimal) Mul(other Decimal) Decimal {
	return Decimal{v: d.v.Mul(other.v)}
}

func (d Decimal) Div(other Decimal) (Decimal, error) {
	if other.IsZero() {
		return Decimal{}, fmt.Errorf("division by zero")
	}
	return Decimal{v: d.v.Div(other.v)}, nil
}

func (d Decimal) DivInt(divisor int64) Decimal {
	return Decimal{v: d.v.Div(sd.NewFromInt(divisor))}
}

func (d Decimal) Pow(exp int) Decimal {
	return Decimal{v: d.v.Pow(sd.NewFromInt(int64(exp)))}
}

func (d Decimal) Neg() Decimal {
	return Decimal{v: d.v.Neg()}
}

func (d Decimal) Abs() Decimal {
	return Decimal{v: d.v.Abs()}
}