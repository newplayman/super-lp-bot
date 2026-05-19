package tickmath

import (
	"errors"
	"math/big"
	"strings"

	"github.com/lpbot/lpbot/pkg/decimal"
)

var ErrInvalidDecimals = errors.New("invalid decimals")

// PriceToTick converts a price ratio to tick.
// price = amount1 / amount0 = 1.0001^tick * 10^(decimals0 - decimals1)
// Returns floor(tick).
func PriceToTick(price decimal.Decimal, decimals0, decimals1 uint8) (int, error) {
	if decimals0 > 30 || decimals1 > 30 {
		return 0, ErrInvalidDecimals
	}

	// Adjust for decimal difference: effective price = price * 10^(decimals1-decimals0)
	decimalsDiff := int(decimals1) - int(decimals0)
	adjusted := price
	if decimalsDiff > 0 {
		for i := 0; i < decimalsDiff; i++ {
			adjusted = adjusted.Mul(decimal.MustFromString("10"))
		}
	} else if decimalsDiff < 0 {
		for i := 0; i < -decimalsDiff; i++ {
			adjusted, _ = adjusted.Div(decimal.MustFromString("10"))
		}
	}

	// Convert to sqrtPriceX96 and use SqrtPriceX96ToTick
	sqrtFromPrice, err := SqrtPriceX96ToTick(sqrtFromDecimal(adjusted))
	if err != nil {
		return 0, err
	}
	return sqrtFromPrice, nil
}

// sqrtFromDecimal converts a decimal price to sqrtPriceX96.
// price = (sqrtPriceX96 / 2^96)^2
// => sqrtPriceX96 = sqrt(price) * 2^96
func sqrtFromDecimal(price decimal.Decimal) *big.Int {
	// Get price as big.Int (without decimal point)
	priceBI := decimalToBI(price)

	// Q96 = 2^96
	q96 := new(big.Int).Lsh(big.NewInt(1), 96)

	// First, get the number of decimal places in the price string
	s := price.String()
	decimalPlaces := 0
	hasDecimal := false
	for i := 0; i < len(s); i++ {
		if s[i] == '.' {
			hasDecimal = true
			decimalPlaces = len(s) - i - 1
			break
		}
	}

	// sqrt(price) * 2^96 = sqrt(priceBI) * 2^96 / 10^decimalPlaces
	sqrtPrice := sqrtInt(priceBI)
	result := new(big.Int).Mul(sqrtPrice, q96)
	if hasDecimal {
		divisor := pow10Big(int64(decimalPlaces))
		result.Div(result, divisor)
	}

	return result
}

func pow10Big(n int64) *big.Int {
	if n <= 0 {
		return big.NewInt(1)
	}
	result := big.NewInt(1)
	for i := int64(0); i < n; i++ {
		result.Mul(result, big.NewInt(10))
	}
	return result
}

// sqrtInt computes integer square root using Newton-Raphson
func sqrtInt(n *big.Int) *big.Int {
	if n.Sign() <= 0 {
		return big.NewInt(0)
	}

	// Initial guess
	x := new(big.Int).Rsh(n, 1)
	if x.Sign() == 0 {
		x = big.NewInt(1)
	}

	// Newton-Raphson iteration
	for {
		y := new(big.Int).Add(x, new(big.Int).Div(n, x))
		y.Rsh(y, 1)
		if y.Cmp(x) >= 0 {
			// Check if x^2 <= n < (x+1)^2
			xSq := new(big.Int).Mul(x, x)
			if xSq.Cmp(n) <= 0 {
				return x
			}
			// x was too high, backtrack
			x.Sub(x, big.NewInt(1))
			xSq = new(big.Int).Mul(x, x)
			if xSq.Cmp(n) <= 0 {
				return x
			}
			return big.NewInt(0)
		}
		x.Set(y)
	}
}

func decimalToBI(d decimal.Decimal) *big.Int {
	// Convert decimal.Decimal to *big.Int by parsing string representation
	s := d.String()
	// Remove decimal point
	var clean strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] != '.' {
			clean.WriteByte(s[i])
		}
	}
	v, _ := new(big.Int).SetString(clean.String(), 10)
	return v
}