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

// Sqrt returns the square root of the decimal.
func (d Decimal) Sqrt() (Decimal, error) {
	if d.IsNeg() {
		return Decimal{}, fmt.Errorf("square root of negative number")
	}
	if d.IsZero() {
		return Zero, nil
	}
	// Newton's method: x_{n+1} = (x_n + d/x_n) / 2
	guess := Decimal{v: d.v.Div(sd.NewFromFloat(2.0))}
	one := Decimal{v: sd.NewFromInt(1)}
	for i := 0; i < 50; i++ {
		div, _ := d.Div(guess)
		next := guess.Add(div).DivInt(2)
		diff := next.Sub(guess).Abs()
		if diff.LessThan(one.DivInt(1000000)) {
			return next, nil
		}
		guess = next
	}
	return guess, nil
}