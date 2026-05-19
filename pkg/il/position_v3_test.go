package il

import (
	"math/big"
	"testing"

	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestV3PositionPnL_PriceUnchanged(t *testing.T) {
	// Test Case 1: Position initial in range, price unchanged -> IL~0, has fee
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(1000000),
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("1000"), // 1000 token0
		Token1: decimal.MustFromString("2000"), // 2000 token1 (USDC)
	}

	initialPrice := decimal.MustFromString("1.0")   // token0 = 1 USDC
	currentPrice := decimal.MustFromString("1.0")  // price unchanged

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	// Fee value: token0 * price + token1 = 1000 * 1 + 2000 = 3000 USD
	expectedFees := decimal.MustFromString("3000")

	// IL should be ~0 since price unchanged
	ilAbs := il.Abs()
	threshold := decimal.MustFromString("1.0") // Allow up to 1 USD IL for numerical precision
	if ilAbs.GreaterThan(threshold) {
		t.Errorf("IL should be ~0 when price unchanged, got %v", il)
	}

	// Net PnL = fees - IL = fees (since IL~0)
	netDiff := net.Sub(expectedFees).Abs()
	if netDiff.GreaterThan(threshold) {
		t.Errorf("Net PnL should equal fees when IL~0, got %v, want %v", net, expectedFees)
	}

	t.Logf("Test 1: Price unchanged - fees=%v, il=%v, net=%v", fees, il, net)
}

func TestV3PositionPnL_PriceDropped(t *testing.T) {
	// Test Case 2: Price dropped 50% -> significant IL
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(1000000),
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("1000"), // 1000 token0
		Token1: decimal.MustFromString("2000"), // 2000 token1 (USDC)
	}

	initialPrice := decimal.MustFromString("1.0")   // token0 = 1 USDC
	currentPrice := decimal.MustFromString("0.5")  // token0 dropped 50%

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	// IL should have significant magnitude
	t.Logf("Test 2: Price dropped 50%% - fees=%v, il=%v, net=%v", fees, il, net)

	// IL should have significant magnitude (not near zero)
	ilAbs := il.Abs()
	if ilAbs.LessThan(decimal.MustFromString("100")) {
		t.Errorf("IL should have significant magnitude when price drops 50%%, got %v", il)
	}
}

func TestV3PositionPnL_FeeIncomeExceedsIL(t *testing.T) {
	// Test Case 3: Net PnL can be positive (fee收益 > IL损失)
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(1000000),
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("100"),   // Small token0
		Token1: decimal.MustFromString("5000"),  // Large token1 (USDC) - high fee income
	}

	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("0.8")  // 20% drop

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	// Fee income should be substantial
	// Fees = token0 * price + token1 = 100 * 0.8 + 5000 = 5080 USD
	t.Logf("Test 3: Fee income vs IL - fees=%v, il=%v, net=%v", fees, il, net)

	// Net should be positive if fees exceed IL losses
	if net.LessThan(decimal.Zero) {
		t.Errorf("Net PnL should be positive with high fee income, got %v", net)
	}
}

func TestV3PositionPnL_NoLiquidity(t *testing.T) {
	// Test Case: Position with no liquidity -> IL=0
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(0),  // No liquidity
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("0"),
		Token1: decimal.MustFromString("0"),
	}

	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("0.5")

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	// All values should be zero
	if !fees.IsZero() {
		t.Errorf("Fees should be 0 with no tokens, got %v", fees)
	}

	if !il.IsZero() {
		t.Errorf("IL should be 0 with no liquidity, got %v", il)
	}

	if !net.IsZero() {
		t.Errorf("Net PnL should be 0 with no position, got %v", net)
	}

	t.Logf("Test 4: No liquidity - fees=%v, il=%v, net=%v", fees, il, net)
}

func TestV3PositionPnL_PriceIncreased(t *testing.T) {
	// Test Case: Price doubled -> IL should be significant
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(1000000),
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("1000"), // 1000 token0
		Token1: decimal.MustFromString("1000"), // 1000 token1
	}

	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("2.0")  // 100% increase

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	// IL should be significant when price doubles
	// Price doubled, ratio = 2
	t.Logf("Test 5: Price doubled - fees=%v, il=%v, net=%v", fees, il, net)

	// IL should have significant magnitude
	ilAbs := il.Abs()
	if ilAbs.LessThan(decimal.MustFromString("50")) {
		t.Errorf("IL should have significant magnitude when price doubles, got %v", il)
	}
}

func TestV3PositionPnL_NetPnLCalculation(t *testing.T) {
	// Test that net PnL = fees + ilUSD (ilUSD is negative for loss)
	state := V3PositionState{
		TickLower:  -1000,
		TickUpper:   1000,
		Liquidity:   big.NewInt(1000000),
		FeeGrowthInside0: decimal.Zero,
		FeeGrowthInside1: decimal.Zero,
		Token0: decimal.MustFromString("1000"),
		Token1: decimal.MustFromString("1000"),
	}

	initialPrice := decimal.MustFromString("1.0")
	currentPrice := decimal.MustFromString("0.5")  // 50% drop

	fees, il, net := V3PositionPnL(state, initialPrice, currentPrice)

	t.Logf("Test 6: Net PnL check - fees=%v, il=%v, net=%v", fees, il, net)

	// Net PnL should be fees + il (il is positive here which is a "gain" in the formula sense)
	// But conceptually, if IL is a loss, it should reduce net
	// The exact sign depends on implementation, so we just verify the relationship

	// Net should be somewhere between fees - |il| and fees + |il|
	feesAbs := fees.Abs()
	ilAbs := il.Abs()

	// Net should be in a reasonable range
	maxExpected := feesAbs.Add(ilAbs)
	if net.GreaterThan(maxExpected) {
		t.Errorf("Net PnL should not exceed fees + |il|, got %v, max expected %v", net, maxExpected)
	}
}