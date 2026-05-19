package pnl

import (
	"math/big"
	"strconv"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/il"
)

// RealizeIL computes impermanent loss (IL) for a position at a point in time.
//
// This function uses the pkg/il package for V2/V3 IL calculation.
// IL is always non-positive (monotone property: IL <= 0).
//
// Parameters:
//   - pos: the position state (includes tick range for V3)
//   - price0: current price of token0 in USD
//   - price1: current price of token1 in USD
//
// Returns IL as a decimal (negative = loss, 0 = no change).
func RealizeIL(pos domain.Position, price0, price1 domain.Decimal) (domain.Decimal, error) {
	// Check if V3 position (has tick range) or V2 (no tick range)
	if pos.TickLower != 0 || pos.TickUpper != 0 {
		// V3 position - use tick range for IL calculation
		return RealizeILV3(pos, price0, price1)
	}

	// V2 position - use simple price ratio IL
	return RealizeILV2(pos, price0, price1)
}

// domainToPkgDecimal converts domain.Decimal to pkg/decimal.Decimal for calculation.
func domainToPkgDecimal(d domain.Decimal) decimal.Decimal {
	s := d.String()
	p, err := decimal.FromString(s)
	if err != nil {
		return decimal.Zero
	}
	return p
}

// RealizeILV2 computes V2 impermanent loss using simple price ratio formula.
//
// IL = 2*sqrt(P1/P0) / (1 + P1/P0) - 1
//
// Always returns non-positive value (0 or negative).
func RealizeILV2(pos domain.Position, price0, price1 domain.Decimal) (domain.Decimal, error) {
	if price0.IsZero() {
		return domain.MustDecimal("0"), nil
	}

	// Convert to pkg/decimal for calculation (which has Sqrt method)
	p0 := domainToPkgDecimal(price0)
	p1 := domainToPkgDecimal(price1)

	ratio, _ := p0.Div(p1)
	sqrtRatio, err := ratio.Sqrt()
	if err != nil {
		return domain.MustDecimal("0"), err
	}

	two := decimal.FromInt(2)
	one := decimal.FromInt(1)
	numerator := sqrtRatio.Mul(two)
	denominator := one.Add(ratio)
	ilFactor, _ := numerator.Div(denominator)
	il := ilFactor.Sub(one)

	return domain.MustDecimal(il.String()), nil
}

// RealizeILV3 computes V3 impermanent loss based on price position relative to tick range.
//
// Three cases:
// 1. Price in range: IL = 2*sqrt(r) / (1 + r) - 1 (same as V2)
// 2. Price below range: IL = sqrt(r) - 1
// 3. Price above range: IL = 1/sqrt(r) - 1
func RealizeILV3(pos domain.Position, price0, price1 domain.Decimal) (domain.Decimal, error) {
	if price0.IsZero() {
		return domain.MustDecimal("0"), nil
	}

	// Convert to pkg/decimal for calculation (which has Sqrt method)
	p0 := domainToPkgDecimal(price0)
	p1 := domainToPkgDecimal(price1)

	ratio, _ := p0.Div(p1)
	sqrtRatio, err := ratio.Sqrt()
	if err != nil {
		return domain.MustDecimal("0"), err
	}

	one := decimal.FromInt(1)
	tickLower := pos.TickLower
	tickUpper := pos.TickUpper
	tickRange := int64(tickUpper - tickLower)

	approxPriceRange := decimal.FromInt(1).DivInt(10000) // 0.0001
	tickRangeDecimal := decimal.FromInt(tickRange / 2)
	lowerBound := one.Sub(approxPriceRange.Mul(tickRangeDecimal))
	upperBound := one.Add(approxPriceRange.Mul(tickRangeDecimal))

	if ratio.GreaterThanOrEqual(lowerBound) && ratio.LessThanOrEqual(upperBound) {
		two := decimal.FromInt(2)
		num := sqrtRatio.Mul(two)
		denom := one.Add(ratio)
		ilFactor, _ := num.Div(denom)
		il := ilFactor.Sub(one)
		return domain.MustDecimal(il.String()), nil
	}

	if ratio.LessThan(lowerBound) {
		il := sqrtRatio.Sub(one)
		return domain.MustDecimal(il.String()), nil
	}

	invSqrt, _ := one.Div(sqrtRatio)
	il := invSqrt.Sub(one)
	return domain.MustDecimal(il.String()), nil
}

// RealizeILFromILPackage computes IL using the pkg/il package directly.
// This provides accurate V3 IL calculation with proper tick handling.
func RealizeILFromILPackage(
	sqrtPrice0X96, sqrtPriceCurrentX96 *big.Int,
	tickLower, tickUpper int64,
) (domain.Decimal, error) {
	ilDecimal, err := il.ILV3(sqrtPrice0X96, sqrtPriceCurrentX96, tickLower, tickUpper)
	if err != nil {
		return domain.MustDecimal("0"), err
	}
	return domain.MustDecimal(ilDecimal.String()), nil
}

// pkgDecimalToDomain converts pkg/decimal.Decimal to domain.Decimal.
func pkgDecimalToDomain(d decimal.Decimal) domain.Decimal {
	return domain.MustDecimal(d.String())
}

// int64ToString converts an int64 to string.
func int64ToString(n int64) string {
	if n == 0 {
		return "0"
	}
	return strconv.FormatInt(n, 10)
}