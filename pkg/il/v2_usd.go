package il

import "github.com/lpbot/lpbot/pkg/decimal"

// ILToUSD converts IL percentage to USD loss.
// ilPct: IL as decimal (e.g., -0.134 for -13.4%)
// lpValueUSD: LP position value in USDC at price0
func ILToUSD(ilPct, lpValueUSD decimal.Decimal) decimal.Decimal {
	return lpValueUSD.Mul(ilPct) // negative result = loss
}

// NetValueUSD returns the LP position value in USD at termination,
// accounting for impermanent loss.
// lpValueUSD + ILToUSD(ILV2(price0, price1), lpValueUSD)
func NetValueUSD(price0, price1, lpValueUSD decimal.Decimal) decimal.Decimal {
	il := ILV2(price0, price1)
	return lpValueUSD.Add(ILToUSD(il, lpValueUSD))
}