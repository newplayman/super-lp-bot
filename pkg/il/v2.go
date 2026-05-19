package il

import "github.com/lpbot/lpbot/pkg/decimal"

// ILV2 computes impermanent loss for a V2-style LP position.
// price0, price1 are token prices in USDC.
func ILV2(price0, price1 decimal.Decimal) decimal.Decimal {
	ratio, _ := price1.Div(price0) // P₁/P₀
	two := decimal.FromInt(2)
	sqrtRatio, _ := ratio.Sqrt()
	numerator := two.Mul(sqrtRatio)
	one := decimal.FromInt(1)
	denominator := one.Add(ratio)
	ilFactor, _ := numerator.Div(denominator)
	il := ilFactor.Sub(one)
	return il // negative = loss
}