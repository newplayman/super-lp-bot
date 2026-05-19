package tickmath_test

import (
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

func TestPriceToTick_USDC_USDT(t *testing.T) {
	// USDC/USDT pair, both 6 decimals, price ≈ 1.0 → tick ≈ 0
	// Actually: price = 1.0, decimals0=6, decimals1=6
	// effective_price = 1.0 * 10^0 = 1.0 → tick ≈ 0
	price := decimal.MustFromString("1.0")
	tick, err := tickmath.PriceToTick(price, 6, 6)
	require.NoError(t, err)
	require.True(t, tick >= -10 && tick <= 10, "USDC/USDT ~1 should be near tick 0, got %d", tick)
}

func TestPriceToTick_WBTC_WETH(t *testing.T) {
	// WBTC (8 decimals) / WETH (18 decimals)
	// price = WBTC/WETH ≈ 10 (1 WETH ≈ 10 WBTC)
	// effective_price = price * 10^(18-8) = 10 * 10^10 = 10^11
	price := decimal.MustFromString("10")
	tick, err := tickmath.PriceToTick(price, 8, 18)
	require.NoError(t, err)
	require.True(t, tick > 0, "WBTC/WETH > 1, tick should be positive, got %d", tick)
}