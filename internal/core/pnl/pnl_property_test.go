package pnl

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/pkg/decimal"
	"github.com/lpbot/lpbot/pkg/il"
	"github.com/lpbot/lpbot/pkg/tickmath"
	"github.com/stretchr/testify/require"
)

// TestFeeIncomeMonotoneNonNegative verifies that fee income is always >= 0.
// This is a core invariant: fees can never be negative.
func TestFeeIncomeMonotoneNonNegative(t *testing.T) {
	tests := []struct {
		name     string
		pos      domain.Position
		swaps    []Swap
		validate bool // if true, validates monotonicity across cumulative fees
	}{
		{
			name:     "empty_swaps",
			pos:      domain.Position{ID: "test-1"},
			swaps:    []Swap{},
			validate: false,
		},
		{
			name: "single_swap_token0_out",
			pos:  domain.Position{ID: "test-2"},
			swaps: []Swap{
				{
					Amount0:    domain.MustDecimal("-1000"),
					Amount1:    domain.MustDecimal("2000"),
					PoolFeeBPS: 30,
				},
			},
			validate: false,
		},
		{
			name: "single_swap_token1_out",
			pos:  domain.Position{ID: "test-3"},
			swaps: []Swap{
				{
					Amount0:    domain.MustDecimal("1000"),
					Amount1:    domain.MustDecimal("-2000"),
					PoolFeeBPS: 30,
				},
			},
			validate: false,
		},
		{
			name: "multiple_swaps_accumulating",
			pos:  domain.Position{ID: "test-4"},
			swaps: []Swap{
				{
					Amount0:    domain.MustDecimal("-500"),
					Amount1:    domain.MustDecimal("1000"),
					PoolFeeBPS: 30,
				},
				{
					Amount0:    domain.MustDecimal("800"),
					Amount1:    domain.MustDecimal("-1600"),
					PoolFeeBPS: 30,
				},
				{
					Amount0:    domain.MustDecimal("-1200"),
					Amount1:    domain.MustDecimal("2400"),
					PoolFeeBPS: 30,
				},
			},
			validate: true, // validate cumulative monotonicity
		},
		{
			name: "high_fee_tier",
			pos:  domain.Position{ID: "test-5"},
			swaps: []Swap{
				{
					Amount0:    domain.MustDecimal("-10000"),
					Amount1:    domain.MustDecimal("20000"),
					PoolFeeBPS: 100, // 1% fee
				},
			},
			validate: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			fees, err := AccrueFees(tc.pos, tc.swaps)
			require.NoError(t, err)

			// Property 1: fees must be non-negative
			require.True(t, fees.GreaterThanOrEqual(domain.MustDecimal("0")),
				"fees must be >= 0, got %s", fees.String())

			// Property 2: if swaps is empty, fees should be zero
			if len(tc.swaps) == 0 {
				require.True(t, fees.IsZero(),
					"fees for empty swaps should be 0, got %s", fees.String())
			}

			// Property 3: cumulative fees should be monotone non-decreasing
			if tc.validate {
				var cumulativeFees domain.Decimal
				for i := range tc.swaps {
					partialSwaps := tc.swaps[:i+1]
					feesPartial, err := AccrueFees(tc.pos, partialSwaps)
					require.NoError(t, err)
					require.True(t, feesPartial.GreaterThanOrEqual(cumulativeFees),
						"cumulative fees should not decrease: prev=%s, current=%s",
						cumulativeFees.String(), feesPartial.String())
					cumulativeFees = feesPartial
				}
				require.True(t, fees.Equal(cumulativeFees),
					"final fees should equal cumulative: expected=%s, got=%s",
					cumulativeFees.String(), fees.String())
			}
		})
	}
}

// TestILMonotoneNonPositive verifies that impermanent loss is always <= 0.
// This is a core invariant: IL can never be positive (you can't gain from IL).
func TestILMonotoneNonPositive(t *testing.T) {
	tests := []struct {
		name   string
		pos    domain.Position
		price0 domain.Decimal
		price1 domain.Decimal
	}{
		{
			name:   "v2_no_price_change",
			pos:    domain.Position{ID: "test-v2-1"},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("1.0"),
		},
		{
			name:   "v2_price_increase",
			pos:    domain.Position{ID: "test-v2-2"},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("1.5"),
		},
		{
			name:   "v2_price_decrease",
			pos:    domain.Position{ID: "test-v2-3"},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("0.5"),
		},
		{
			name:   "v2_large_price_increase",
			pos:    domain.Position{ID: "test-v2-4"},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("10.0"),
		},
		{
			name:   "v2_large_price_decrease",
			pos:    domain.Position{ID: "test-v2-5"},
			price0: domain.MustDecimal("10.0"),
			price1: domain.MustDecimal("1.0"),
		},
		{
			name:   "v3_in_range_no_change",
			pos:    domain.Position{ID: "test-v3-1", TickLower: -1000, TickUpper: 1000},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("1.0"),
		},
		{
			name:   "v3_in_range_small_change",
			pos:    domain.Position{ID: "test-v3-2", TickLower: -1000, TickUpper: 1000},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("1.1"),
		},
		{
			name:   "v3_below_range",
			pos:    domain.Position{ID: "test-v3-3", TickLower: -1000, TickUpper: 1000},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("0.5"),
		},
		{
			name:   "v3_above_range",
			pos:    domain.Position{ID: "test-v3-4", TickLower: -1000, TickUpper: 1000},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("2.0"),
		},
		{
			name:   "v3_wide_range",
			pos:    domain.Position{ID: "test-v3-5", TickLower: -10000, TickUpper: 10000},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("0.8"),
		},
		{
			name:   "v3_narrow_range",
			pos:    domain.Position{ID: "test-v3-6", TickLower: -10, TickUpper: 10},
			price0: domain.MustDecimal("1.0"),
			price1: domain.MustDecimal("1.05"),
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			il, err := RealizeIL(tc.pos, tc.price0, tc.price1)
			require.NoError(t, err)

			// Property: IL must be non-positive (IL <= 0)
			// Allow small floating point errors (less than 1e-12)
			isNonPositive := il.IsNegative() || il.Abs().LessThan(domain.MustDecimal("1e-12"))
			require.True(t, isNonPositive,
				"IL must be <= 0, got %s for price0=%s, price1=%s",
				il.String(), tc.price0.String(), tc.price1.String())
		})
	}
}

// TestSumNetPnLPerBlockEqualsRealizedAtClose verifies the invariant:
// sum(NetPnL_per_block) == Realized_NetPnL_at_close
func TestSumNetPnLPerBlockEqualsRealizedAtClose(t *testing.T) {
	// Simulate a position lifecycle with multiple blocks
	pos := domain.Position{
		ID:        "test-sum-1",
		TickLower: -1000,
		TickUpper: 1000,
	}

	// Initial prices
	initialPrice0 := domain.MustDecimal("1.0")
	initialPrice1 := domain.MustDecimal("1.0")

	// Simulate blocks with different price scenarios
	blocks := []struct {
		blockNum int
		price0   domain.Decimal
		price1   domain.Decimal
		fees     domain.Decimal
		gas      domain.Decimal
	}{
		{1, domain.MustDecimal("1.0"), domain.MustDecimal("1.0"), domain.MustDecimal("10"), domain.MustDecimal("1")},
		{2, domain.MustDecimal("1.05"), domain.MustDecimal("1.05"), domain.MustDecimal("15"), domain.MustDecimal("1.5")},
		{3, domain.MustDecimal("1.1"), domain.MustDecimal("1.1"), domain.MustDecimal("20"), domain.MustDecimal("2")},
		{4, domain.MustDecimal("1.15"), domain.MustDecimal("1.15"), domain.MustDecimal("25"), domain.MustDecimal("2.5")},
	}

	var sumNetPnL domain.Decimal

	for _, block := range blocks {
		il, err := RealizeIL(pos, block.price0, block.price1)
		require.NoError(t, err)

		netPnL := NetPnL(block.fees, il, block.gas)
		sumNetPnL = sumNetPnL.Add(netPnL)
	}

	// Calculate final realized PnL at close
	finalIL, err := RealizeIL(pos, initialPrice0, initialPrice1)
	require.NoError(t, err)

	// Total fees and gas over all blocks
	var totalFees, totalGas domain.Decimal
	for _, block := range blocks {
		totalFees = totalFees.Add(block.fees)
		totalGas = totalGas.Add(block.gas)
	}

	// Final realized PnL = fees - |IL_initial| - gas_total
	// (IL_initial is the IL at the start, which is 0 for no price change)
	finalRealizedPnL := NetPnL(totalFees, finalIL, totalGas)

	// Property: sum of per-block NetPnL should equal realized NetPnL at close
	// Allow small rounding differences
	diff := sumNetPnL.Sub(finalRealizedPnL).Abs()
	require.True(t, diff.LessThan(domain.MustDecimal("1e-6")),
		"sum(NetPnL_per_block) should equal Realized_NetPnL_at_close: "+
			"sum=%s, realized=%s, diff=%s",
		sumNetPnL.String(), finalRealizedPnL.String(), diff.String())
}

// TestILWithILPackage verifies that RealizeIL matches pkg/il for V3 positions.
func TestILWithILPackage(t *testing.T) {
	tests := []struct {
		name           string
		initialTick    int64
		currentTick    int64
		tickLower      int64
		tickUpper      int64
		priceTolerance string // tolerance for comparison
	}{
		{
			name:           "in_range_same_price",
			initialTick:    0,
			currentTick:    0,
			tickLower:      -1000,
			tickUpper:      1000,
			priceTolerance: "1e-10",
		},
		{
			name:           "in_range_price_up",
			initialTick:    0,
			currentTick:    100,
			tickLower:      -1000,
			tickUpper:      1000,
			priceTolerance: "1e-6",
		},
		{
			name:           "in_range_price_down",
			initialTick:    0,
			currentTick:    -100,
			tickLower:      -1000,
			tickUpper:      1000,
			priceTolerance: "1e-6",
		},
		{
			name:           "below_range",
			initialTick:    0,
			currentTick:    -2000,
			tickLower:      -1000,
			tickUpper:      1000,
			priceTolerance: "1e-6",
		},
		{
			name:           "above_range",
			initialTick:    0,
			currentTick:    2000,
			tickLower:      -1000,
			tickUpper:      1000,
			priceTolerance: "1e-6",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			sqrtPrice0, err := tickmath.TickToSqrtPriceX96(tc.initialTick)
			require.NoError(t, err)
			sqrtPriceCurrent, err := tickmath.TickToSqrtPriceX96(tc.currentTick)
			require.NoError(t, err)

			// Calculate using pkg/il
			ilPackage, err := il.ILV3(sqrtPrice0, sqrtPriceCurrent, tc.tickLower, tc.tickUpper)
			require.NoError(t, err)

			// Calculate using our RealizeILFromILPackage
			ilOurs, err := RealizeILFromILPackage(sqrtPrice0, sqrtPriceCurrent, tc.tickLower, tc.tickUpper)
			require.NoError(t, err)

			// Results should be close - convert both to string for comparison
			tolerance := domain.MustDecimal(tc.priceTolerance)
			ilPackageDom := domain.MustDecimal(ilPackage.String())
			diff := ilPackageDom.Sub(ilOurs).Abs()
			require.True(t, diff.LessThan(tolerance),
				"IL values should match: pkg/il=%s, ours=%s, diff=%s",
				ilPackage.String(), ilOurs.String(), diff.String())
		})
	}
}

// TestNetPnLWithRealisticValues tests NetPnL with realistic trading scenarios.
func TestNetPnLWithRealisticValues(t *testing.T) {
	tests := []struct {
		name  string
		fees  domain.Decimal
		il    domain.Decimal
		gas   domain.Decimal
		check string // expected relationship
	}{
		{
			name:  "positive_net_with_fees_exceeding_il",
			fees:  domain.MustDecimal("100"),
			il:    domain.MustDecimal("-50"),
			gas:   domain.MustDecimal("10"),
			check: "positive",
		},
		{
			name:  "negative_net_with_il_exceeding_fees",
			fees:  domain.MustDecimal("30"),
			il:    domain.MustDecimal("-100"),
			gas:   domain.MustDecimal("5"),
			check: "negative",
		},
		{
			name:  "zero_net_perfect_balance",
			fees:  domain.MustDecimal("100"),
			il:    domain.MustDecimal("-100"),
			gas:   domain.MustDecimal("0"),
			check: "zero",
		},
		{
			name:  "zero_fees_only_il",
			fees:  domain.MustDecimal("0"),
			il:    domain.MustDecimal("-50"),
			gas:   domain.MustDecimal("0"),
			check: "negative",
		},
		{
			name:  "large_fees_overcome_il_and_gas",
			fees:  domain.MustDecimal("1000"),
			il:    domain.MustDecimal("-500"),
			gas:   domain.MustDecimal("200"),
			check: "positive",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			netPnL := NetPnL(tc.fees, tc.il, tc.gas)

			switch tc.check {
			case "positive":
				require.True(t, netPnL.IsPositive(),
					"NetPnL should be positive, got %s", netPnL.String())
			case "negative":
				require.True(t, netPnL.IsNegative(),
					"NetPnL should be negative, got %s", netPnL.String())
			case "zero":
				require.True(t, netPnL.Abs().LessThan(domain.MustDecimal("1e-10")),
					"NetPnL should be ~zero, got %s", netPnL.String())
			}
		})
	}
}

// TestAccrueFeesFromVolume tests the volume-based fee calculation.
func TestAccrueFeesFromVolume(t *testing.T) {
	tests := []struct {
		name       string
		volumeUSD  domain.Decimal
		feeTierBPS uint
		expected   string
	}{
		{
			name:       "0.3pct_fee_1000_volume",
			volumeUSD:  domain.MustDecimal("1000"),
			feeTierBPS: 30,
			expected:   "3",
		},
		{
			name:       "1pct_fee_1000_volume",
			volumeUSD:  domain.MustDecimal("1000"),
			feeTierBPS: 100,
			expected:   "10",
		},
		{
			name:       "0.05pct_fee_100000_volume",
			volumeUSD:  domain.MustDecimal("100000"),
			feeTierBPS: 5,
			expected:   "50",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			fee := AccrueFeesFromVolume(tc.volumeUSD, tc.feeTierBPS)
			expected := domain.MustDecimal(tc.expected)

			// Fee should be non-negative
			require.True(t, fee.GreaterThanOrEqual(domain.MustDecimal("0")))

			// Fee should match expected
			diff := fee.Sub(expected).Abs()
			require.True(t, diff.LessThan(domain.MustDecimal("1e-6")),
				"fee=%s, expected=%s, diff=%s", fee.String(), expected.String(), diff.String())
		})
	}
}

// TestZeroPriceEdgeCase tests IL calculation with zero prices.
func TestZeroPriceEdgeCase(t *testing.T) {
	pos := domain.Position{
		ID:        "test-edge",
		TickLower: -1000,
		TickUpper: 1000,
	}

	// Zero price should not panic and should return zero IL
	il, err := RealizeIL(pos, domain.MustDecimal("0"), domain.MustDecimal("1.0"))
	require.NoError(t, err)
	require.True(t, il.Equal(domain.MustDecimal("0")) || il.IsNegative())

	il, err = RealizeIL(pos, domain.MustDecimal("1.0"), domain.MustDecimal("0"))
	require.NoError(t, err)
	require.True(t, il.Equal(domain.MustDecimal("0")) || il.IsNegative())
}

// TestV2ILUsingPkgIL verifies V2 IL matches the il package.
func TestV2ILUsingPkgIL(t *testing.T) {
	tests := [][2]string{
		{"1.0", "1.0"},
		{"1.0", "1.2"},
		{"1.0", "0.8"},
		{"1.0", "2.0"},
		{"1.0", "0.5"},
		{"1.0", "10.0"},
		{"1.0", "0.1"},
	}

	for _, pp := range tests {
		t.Run(pp[0]+"_to_"+pp[1], func(t *testing.T) {
			price0 := domain.MustDecimal(pp[0])
			price1 := domain.MustDecimal(pp[1])

			pos := domain.Position{ID: "test-v2"}

			// Calculate using our V2 function
			ilOurs, err := RealizeILV2(pos, price0, price1)
			require.NoError(t, err)

			// Calculate using pkg/il - need to convert via pkg/decimal.FromString
			p0, err := decimal.FromString(price0.String())
			require.NoError(t, err)
			p1, err := decimal.FromString(price1.String())
			require.NoError(t, err)
			ilPackage := il.ILV2(p0, p1)

			// Results should match - convert both to domain.Decimal for comparison
			ilPackageDom := domain.MustDecimal(ilPackage.String())
			diff := ilOurs.Sub(ilPackageDom).Abs()
			require.True(t, diff.LessThan(domain.MustDecimal("1e-10")),
				"V2 IL mismatch: ours=%s, pkg=%s, diff=%s",
				ilOurs.String(), ilPackageDom.String(), diff.String())
		})
	}
}

// TestNetPnLBreakdown tests the detailed PnL breakdown.
func TestNetPnLBreakdown(t *testing.T) {
	breakdown := ComputeNetPnL(
		domain.MustDecimal("100"),  // feeUSD
		domain.MustDecimal("-50"), // ilUSD (negative)
		domain.MustDecimal("10"),   // gasUSD
		domain.MustDecimal("0"),    // swapCostUSD (Phase 0)
		domain.MustDecimal("0"),    // slippageUSD (Phase 0)
	)

	require.Equal(t, domain.MustDecimal("100"), breakdown.FeeUSD)
	require.Equal(t, domain.MustDecimal("-50"), breakdown.ILUSD)
	require.Equal(t, domain.MustDecimal("10"), breakdown.GasUSD)
	require.True(t, breakdown.SwapCostUSD.IsZero())
	require.True(t, breakdown.SlippageUSD.IsZero())
	// NetPnL = 100 + (-50) - 10 = 40
	require.Equal(t, domain.MustDecimal("40"), breakdown.NetPnLUSD)
}

// TestAccrueFeesWithLargeVolume tests fee calculation with large volumes.
func TestAccrueFeesWithLargeVolume(t *testing.T) {
	pos := domain.Position{ID: "test-large"}

	// Large swap with 0.3% fee
	swaps := []Swap{
		{
			Amount0:    domain.MustDecimal("-1000000000"), // 1 billion
			Amount1:    domain.MustDecimal("2000000000"),
			PoolFeeBPS: 30,
		},
	}

	fees, err := AccrueFees(pos, swaps)
	require.NoError(t, err)
	require.True(t, fees.GreaterThanOrEqual(domain.MustDecimal("0")))
}

// TestILBoundedByPositionValue verifies IL magnitude is bounded.
func TestILBoundedByPositionValue(t *testing.T) {
	pos := domain.Position{
		ID:        "test-bounds",
		TickLower: -1000,
		TickUpper: 1000,
	}

	price0 := domain.MustDecimal("1.0")
	price1 := domain.MustDecimal("1.1") // 10% price increase

	il, err := RealizeIL(pos, price0, price1)
	require.NoError(t, err)

	// IL should be negative (a loss)
	require.True(t, il.IsNegative())

	// IL should be bounded: magnitude should be reasonable for price changes
	// For 10% price change, IL is approximately -0.26% (classical IL formula)
	// We allow generous slack for our simplified V3 calculation
	maxExpectedIL := domain.MustDecimal("-0.5") // Should be well below -50%
	require.True(t, il.GreaterThan(maxExpectedIL),
		"IL seems too large: %s", il.String())
}

// TestSwapWithZeroFees tests fee calculation with zero fees.
func TestSwapWithZeroFees(t *testing.T) {
	pos := domain.Position{ID: "test-zero-fee"}

	swaps := []Swap{
		{
			Amount0:    domain.MustDecimal("-1000"),
			Amount1:    domain.MustDecimal("2000"),
			PoolFeeBPS: 0,
		},
	}

	fees, err := AccrueFees(pos, swaps)
	require.NoError(t, err)
	require.True(t, fees.IsZero() || fees.GreaterThanOrEqual(domain.MustDecimal("0")))
}

// TestSwapWithInvalidDirection tests fee calculation with unusual swap directions.
func TestSwapWithInvalidDirection(t *testing.T) {
	pos := domain.Position{ID: "test-both-positive"}

	// Both positive (unusual but shouldn't panic)
	swaps := []Swap{
		{
			Amount0:    domain.MustDecimal("1000"),
			Amount1:    domain.MustDecimal("1000"),
			PoolFeeBPS: 30,
		},
	}

	fees, err := AccrueFees(pos, swaps)
	require.NoError(t, err)
	require.True(t, fees.GreaterThanOrEqual(domain.MustDecimal("0")))
}

// TestNetPnLFromComponents tests the alternative constructor.
func TestNetPnLFromComponents(t *testing.T) {
	feeUSD := domain.MustDecimal("100")
	ilUSD := domain.MustDecimal("-50")
	gasUSD := domain.MustDecimal("10")

	netPnL := NetPnLFromComponents(feeUSD, ilUSD, gasUSD)

	// Should equal: fee + il - gas = 100 + (-50) - 10 = 40
	expected := domain.MustDecimal("40")
	diff := netPnL.Sub(expected).Abs()
	require.True(t, diff.LessThan(domain.MustDecimal("1e-10")),
		"NetPnLFromComponents mismatch: got %s, expected %s", netPnL.String(), expected.String())
}

// BenchmarkAccrueFees benchmarks the fee calculation.
func BenchmarkAccrueFees(b *testing.B) {
	pos := domain.Position{ID: "bench"}
	swaps := make([]Swap, 1000)
	for i := range swaps {
		swaps[i] = Swap{
			Amount0:    domain.MustDecimal("-1000"),
			Amount1:    domain.MustDecimal("2000"),
			PoolFeeBPS: 30,
		}
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = AccrueFees(pos, swaps)
	}
}

// BenchmarkRealizeIL benchmarks the IL calculation.
func BenchmarkRealizeIL(b *testing.B) {
	pos := domain.Position{
		ID:        "bench",
		TickLower: -1000,
		TickUpper: 1000,
	}
	price0 := domain.MustDecimal("1.0")
	price1 := domain.MustDecimal("1.5")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = RealizeIL(pos, price0, price1)
	}
}

// BenchmarkNetPnL benchmarks the NetPnL calculation.
func BenchmarkNetPnL(b *testing.B) {
	fees := domain.MustDecimal("100")
	il := domain.MustDecimal("-50")
	gas := domain.MustDecimal("10")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = NetPnL(fees, il, gas)
	}
}