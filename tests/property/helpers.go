// Package property provides property-based testing helpers using rapid.
package property

import (
	"math/big"
	"testing"

	"github.com/shopspring/decimal"
	"pgregory.net/rapid"

	"github.com/lpbot/lpbot/internal/domain"
)

// GenChainID generates random ChainID values.
func GenChainID() *rapid.Generator[domain.ChainID] {
	return rapid.SampledFrom([]domain.ChainID{domain.ChainBase, domain.ChainSolana})
}

// GenPositiveDecimal generates positive decimal values in the range
// 1e0 to 1e(maxDigits-1).
func GenPositiveDecimal(maxDigits int) *rapid.Generator[domain.Decimal] {
	return rapid.Custom(func(t *rapid.T) domain.Decimal {
		n := rapid.Int64Range(1, pow10(int64(maxDigits))-1).Draw(t, "value")
		return domain.Decimal(decimal.NewFromInt(n))
	})
}

// GenTier generates random Tier values.
func GenTier() *rapid.Generator[domain.Tier] {
	return rapid.SampledFrom([]domain.Tier{domain.TierA, domain.TierB, domain.TierC})
}

// GenBlockRef generates random BlockRef values.
func GenBlockRef() *rapid.Generator[domain.BlockRef] {
	return rapid.Custom(func(t *rapid.T) domain.BlockRef {
		return domain.BlockRef{
			Chain:    rapid.SampledFrom([]domain.ChainID{domain.ChainBase, domain.ChainSolana}).Draw(t, "Chain"),
			Number:   rapid.Uint64Range(1, 1e9).Draw(t, "Number"),
			Hash:     rapid.StringMatching(`^0x[a-fA-F0-9]{64}$`).Draw(t, "Hash"),
			TimeUnix: rapid.Int64Range(1609459200, 1735689600).Draw(t, "TimeUnix"),
		}
	})
}

// GenPosition generates random Position values.
func GenPosition() *rapid.Generator[domain.Position] {
	return rapid.Custom(func(t *rapid.T) domain.Position {
		tickLower := rapid.Int64Range(-887272, 887271).Draw(t, "TickLower")
		tickUpper := rapid.Int64Range(tickLower+1, 887272).Draw(t, "TickUpper")

		return domain.Position{
			ID:        rapid.StringMatching(`^[a-zA-Z0-9-]+$`).Draw(t, "ID"),
			PoolID:    rapid.StringMatching(`^[a-zA-Z0-9]+$`).Draw(t, "PoolID"),
			Chain:     rapid.SampledFrom([]domain.ChainID{domain.ChainBase, domain.ChainSolana}).Draw(t, "Chain"),
			Status:    GenPositionStatus().Draw(t, "Status"),
			Tier:      rapid.SampledFrom([]domain.Tier{domain.TierA, domain.TierB, domain.TierC}).Draw(t, "Tier"),
			AmountUSD: GenPositiveDecimal(8).Draw(t, "AmountUSD"),
			TickLower: tickLower,
			TickUpper: tickUpper,
			OpenedAt:  rapid.Int64Range(1609459200, 1735689600).Draw(t, "OpenedAt"),
			ClosedAt:  0,
		}
	})
}

// GenPositionStatus generates random PositionStatus values.
func GenPositionStatus() *rapid.Generator[domain.PositionStatus] {
	return rapid.SampledFrom([]domain.PositionStatus{
		domain.StatusIntended,
		domain.StatusApproved,
		domain.StatusRejected,
		domain.StatusOpening,
		domain.StatusOpen,
		domain.StatusExiting,
		domain.StatusClosed,
		domain.StatusExitFailed,
		domain.StatusManual,
	})
}

// GenPool generates random Pool values.
func GenPool() *rapid.Generator[domain.Pool] {
	return rapid.Custom(func(t *rapid.T) domain.Pool {
		return domain.Pool{
			ID:     rapid.StringMatching(`^0x[a-fA-F0-9]{40}$`).Draw(t, "ID"),
			Chain:  rapid.SampledFrom([]domain.ChainID{domain.ChainBase, domain.ChainSolana}).Draw(t, "Chain"),
			Token0: GenAddress().Draw(t, "Token0"),
			Token1: GenAddress().Draw(t, "Token1"),
			FeeBPS: uint(rapid.Uint64Range(1, 10000).Draw(t, "FeeBPS")),
			Tier_:  rapid.SampledFrom([]domain.Tier{domain.TierA, domain.TierB, domain.TierC}).Draw(t, "Tier"),
		}
	})
}

// GenAddress generates valid Ethereum address using domain.Address.
func GenAddress() *rapid.Generator[domain.Address] {
	return rapid.Custom(func(t *rapid.T) domain.Address {
		s := rapid.StringMatching(`^0x[a-fA-F0-9]{40}$`).Draw(t, "addr")
		return domain.MustParseAddress(s)
	})
}

// GenDecimal generates arbitrary decimal values with up to maxDigits.
func GenDecimal(maxDigits int) *rapid.Generator[domain.Decimal] {
	return rapid.Custom(func(t *rapid.T) domain.Decimal {
		n := rapid.Int64Range(-pow10(int64(maxDigits)), pow10(int64(maxDigits))).Draw(t, "value")
		return domain.Decimal(decimal.NewFromInt(n))
	})
}

// GenBigInt generates big.Int values with up to maxDigits.
func GenBigInt(maxDigits int) *rapid.Generator[big.Int] {
	return rapid.Custom(func(t *rapid.T) big.Int {
		n := rapid.Int64Range(0, pow10(int64(maxDigits))-1).Draw(t, "value")
		return *big.NewInt(n)
	})
}

// pow10 returns 10^n for n >= 0.
func pow10(n int64) int64 {
	r := int64(1)
	for i := int64(0); i < n; i++ {
		r *= 10
	}
	return r
}

// GenTick generates tick values within Uniswap V3 valid range.
func GenTick() *rapid.Generator[int64] {
	return rapid.Int64Range(-887272, 887272)
}

// GenTickRange generates a valid tick range (lower < upper).
func GenTickRange() *rapid.Generator[TickRange] {
	return rapid.Custom(func(t *rapid.T) TickRange {
		lower := rapid.Int64Range(-887272, 887271).Draw(t, "Lower")
		upper := rapid.Int64Range(lower+1, 887272).Draw(t, "Upper")
		return TickRange{
			Lower: lower,
			Upper: upper,
		}
	})
}

// TickRange represents a tick range for V3 positions.
type TickRange struct {
	Lower int64
	Upper int64
}

// PropertyTest runs a property-based test with the given generator.
func PropertyTest(t testing.TB, name string, gen *rapid.Generator[domain.Decimal], prop func(domain.Decimal) bool) {
	rapid.Check(t, func(t *rapid.T) {
		val := gen.Draw(t, name)
		if !prop(val) {
			t.Errorf("property failed for %v", val)
		}
	})
}