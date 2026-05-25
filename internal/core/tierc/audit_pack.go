package tierc

import (
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
)

type Verdict string

const (
	VerdictReject        Verdict = "reject"
	VerdictWatch         Verdict = "watch"
	VerdictCanaryAllowed Verdict = "canary_allowed"
)

type FlagSeverity string

const (
	SeverityInfo     FlagSeverity = "info"
	SeverityWarn     FlagSeverity = "warn"
	SeverityCritical FlagSeverity = "critical"
)

type MarketQuality struct {
	BuyVolume24hUSD      domain.Decimal
	SellVolume24hUSD     domain.Decimal
	BuyCount24h          int64
	SellCount24h         int64
	Buyers24h            int64
	Sellers24h           int64
	VolumeCV5m           domain.Decimal
	MedianAbsPriceMove5m domain.Decimal
	Top10HolderPct       domain.Decimal
	KnownHoneypot        bool
	BuyTaxPct            domain.Decimal
	SellTaxPct           domain.Decimal
}

type PackInput struct {
	Pool            domain.Pool
	Score           domain.Score
	EstimatedFeeAPR domain.Decimal
	VolumeToTVL     domain.Decimal
	MarketQuality   MarketQuality
}

type Flag struct {
	Code     string
	Severity FlagSeverity
	Message  string
	Evidence map[string]string
}

type Pack struct {
	PoolID          string
	Verdict         Verdict
	RiskScore       int
	Flags           []Flag
	EstimatedFeeAPR domain.Decimal
	VolumeToTVL     domain.Decimal
}

func BuildPack(input PackInput) Pack {
	var flags []Flag
	var riskScore int

	if sample, ok := knownNegativeSample(input.Pool); ok {
		flags = append(flags, Flag{
			Code:     "known_negative_check",
			Severity: SeverityCritical,
			Message:  "Known negative sample: pool/token matches prior rejected trap and should stay blocked until explicitly cleared",
			Evidence: map[string]string{
				"sample_id": sample.ID,
				"pool_id":   input.Pool.ID,
				"token0":    input.Pool.Token0.String(),
				"token1":    input.Pool.Token1.String(),
				"reason":    sample.Reason,
			},
		})
		riskScore += 40
	}

	// bot_volume_symmetry: if buy/sell volume symmetry >= 0.98 and buy/sell count symmetry >= 0.98, add warn
	if input.MarketQuality.BuyVolume24hUSD.GreaterThan(domain.ZeroDecimal()) && input.MarketQuality.SellVolume24hUSD.GreaterThan(domain.ZeroDecimal()) {
		volSym := min(
			input.MarketQuality.BuyVolume24hUSD.Div(input.MarketQuality.SellVolume24hUSD),
			input.MarketQuality.SellVolume24hUSD.Div(input.MarketQuality.BuyVolume24hUSD),
		)
		countSym := domain.ZeroDecimal()
		if input.MarketQuality.BuyCount24h > 0 && input.MarketQuality.SellCount24h > 0 {
			minCount := min64(input.MarketQuality.BuyCount24h, input.MarketQuality.SellCount24h)
			maxCount := max64(input.MarketQuality.BuyCount24h, input.MarketQuality.SellCount24h)
			countSym = domain.NewDecimalFromInt(minCount).Div(domain.NewDecimalFromInt(maxCount))
		}
		if volSym.GreaterThanOrEqual(domain.MustDecimal("0.98")) && countSym.GreaterThanOrEqual(domain.MustDecimal("0.98")) {
			flags = append(flags, Flag{
				Code:     "bot_volume_symmetry",
				Severity: SeverityWarn,
				Message:  "Buy/sell volume and count symmetry both >= 98%, suggesting bot-managed trading",
				Evidence: map[string]string{
					"buy_volume_24h_usd":  input.MarketQuality.BuyVolume24hUSD.String(),
					"sell_volume_24h_usd": input.MarketQuality.SellVolume24hUSD.String(),
					"vol_symmetry":        volSym.StringFixed(4),
					"buy_count_24h":       fmt.Sprintf("%d", input.MarketQuality.BuyCount24h),
					"sell_count_24h":      fmt.Sprintf("%d", input.MarketQuality.SellCount24h),
					"count_symmetry":      countSym.StringFixed(4),
				},
			})
			riskScore += 15
		}
	}

	if input.MarketQuality.BuyVolume24hUSD.IsZero() && input.MarketQuality.SellVolume24hUSD.IsZero() &&
		input.MarketQuality.BuyCount24h > 0 && input.MarketQuality.SellCount24h > 0 {
		minCount := min64(input.MarketQuality.BuyCount24h, input.MarketQuality.SellCount24h)
		maxCount := max64(input.MarketQuality.BuyCount24h, input.MarketQuality.SellCount24h)
		countSym := domain.NewDecimalFromInt(minCount).Div(domain.NewDecimalFromInt(maxCount))
		if countSym.GreaterThanOrEqual(domain.MustDecimal("0.995")) {
			flags = append(flags, Flag{
				Code:     "count_symmetry_only",
				Severity: SeverityWarn,
				Message:  "Buy/sell counts are near-perfectly symmetric even without split volume data",
				Evidence: map[string]string{
					"buy_count_24h":  fmt.Sprintf("%d", input.MarketQuality.BuyCount24h),
					"sell_count_24h": fmt.Sprintf("%d", input.MarketQuality.SellCount24h),
					"count_symmetry": countSym.StringFixed(4),
				},
			})
			riskScore += 15
		}
	}

	// low_trader_breadth: if total unique buyers+sellers > 0 and trades per unique participant >= 50, add warn
	totalUnique := input.MarketQuality.Buyers24h + input.MarketQuality.Sellers24h
	if totalUnique > 0 {
		totalTrades := input.MarketQuality.BuyCount24h + input.MarketQuality.SellCount24h
		tradesPerParticipant := domain.NewDecimalFromInt(totalTrades).Div(domain.NewDecimalFromInt(totalUnique))
		if tradesPerParticipant.GreaterThanOrEqual(domain.MustDecimal("50")) {
			flags = append(flags, Flag{
				Code:     "low_trader_breadth",
				Severity: SeverityWarn,
				Message:  "Trades per unique participant >= 50, suggesting low organic user base",
				Evidence: map[string]string{
					"buyers_24h":             fmt.Sprintf("%d", input.MarketQuality.Buyers24h),
					"sellers_24h":            fmt.Sprintf("%d", input.MarketQuality.Sellers24h),
					"total_unique":           fmt.Sprintf("%d", totalUnique),
					"buy_count_24h":          fmt.Sprintf("%d", input.MarketQuality.BuyCount24h),
					"sell_count_24h":         fmt.Sprintf("%d", input.MarketQuality.SellCount24h),
					"total_trades":           fmt.Sprintf("%d", totalTrades),
					"trades_per_participant": tradesPerParticipant.StringFixed(2),
				},
			})
			riskScore += 15
		}
	}

	// smooth_volume: if VolumeCV5m > 0 and VolumeCV5m <= 0.15, add warn
	if input.MarketQuality.VolumeCV5m.GreaterThan(domain.ZeroDecimal()) && input.MarketQuality.VolumeCV5m.LessThanOrEqual(domain.MustDecimal("0.15")) {
		flags = append(flags, Flag{
			Code:     "smooth_volume",
			Severity: SeverityWarn,
			Message:  "Volume coefficient of variation <= 0.15 over 5m windows, suggesting bot-driven smooth trading",
			Evidence: map[string]string{
				"volume_cv_5m": input.MarketQuality.VolumeCV5m.StringFixed(4),
			},
		})
		riskScore += 15
	}

	if input.MarketQuality.MedianAbsPriceMove5m.GreaterThan(domain.ZeroDecimal()) &&
		input.MarketQuality.MedianAbsPriceMove5m.LessThanOrEqual(domain.MustDecimal("0.0005")) &&
		input.VolumeToTVL.GreaterThanOrEqual(domain.MustDecimal("1.00")) {
		flags = append(flags, Flag{
			Code:     "price_stasis_high_volume",
			Severity: SeverityWarn,
			Message:  "Price barely moves across 5m windows while volume-to-TVL is high",
			Evidence: map[string]string{
				"median_abs_price_move_5m": input.MarketQuality.MedianAbsPriceMove5m.StringFixed(6),
				"volume_to_tvl":            input.VolumeToTVL.StringFixed(2),
			},
		})
		riskScore += 15
	}

	// high_holder_concentration: if Top10HolderPct >= 80%, add critical
	if input.MarketQuality.Top10HolderPct.GreaterThanOrEqual(domain.MustDecimal("80")) {
		flags = append(flags, Flag{
			Code:     "high_holder_concentration",
			Severity: SeverityCritical,
			Message:  "Top 10 holders own >= 80% of supply",
			Evidence: map[string]string{
				"top10_holder_pct": input.MarketQuality.Top10HolderPct.StringFixed(2),
			},
		})
		riskScore += 40
	}

	// token_tax_or_honeypot: if honeypot is true or buy/sell tax > 0, add critical
	isHoneypot := input.MarketQuality.KnownHoneypot
	buyTaxPositive := input.MarketQuality.BuyTaxPct.GreaterThan(domain.ZeroDecimal())
	sellTaxPositive := input.MarketQuality.SellTaxPct.GreaterThan(domain.ZeroDecimal())
	if isHoneypot || buyTaxPositive || sellTaxPositive {
		flags = append(flags, Flag{
			Code:     "token_tax_or_honeypot",
			Severity: SeverityCritical,
			Message:  "Token is a honeypot and/or has non-zero buy/sell tax",
			Evidence: map[string]string{
				"known_honeypot": fmt.Sprintf("%t", isHoneypot),
				"buy_tax_pct":    input.MarketQuality.BuyTaxPct.StringFixed(2),
				"sell_tax_pct":   input.MarketQuality.SellTaxPct.StringFixed(2),
			},
		})
		riskScore += 40
	}

	// native_zero_token: if token0 or token1 is 0x0000000000000000000000000000000000000000, add critical
	if input.Pool.Token0.IsZero() || input.Pool.Token1.IsZero() {
		flags = append(flags, Flag{
			Code:     "native_zero_token",
			Severity: SeverityCritical,
			Message:  "Pool contains native/zero token which may not be suitable for LP canary",
			Evidence: map[string]string{
				"token0": input.Pool.Token0.String(),
				"token1": input.Pool.Token1.String(),
			},
		})
		riskScore += 40
	}

	// thin_tvl: if TVL < 25000, add critical
	if input.Pool.TVLUSD.LessThan(domain.MustDecimal("25000")) {
		flags = append(flags, Flag{
			Code:     "thin_tvl",
			Severity: SeverityCritical,
			Message:  "TVL below $25,000 - insufficient liquidity depth",
			Evidence: map[string]string{
				"tvl_usd": input.Pool.TVLUSD.StringFixed(2),
			},
		})
		riskScore += 40
	}

	// low_real_volume: if 24h volume < 50000, add warn
	if input.Pool.Vol24h.LessThan(domain.MustDecimal("50000")) {
		flags = append(flags, Flag{
			Code:     "low_real_volume",
			Severity: SeverityWarn,
			Message:  "24h volume below $50,000 - low real trading activity",
			Evidence: map[string]string{
				"vol_24h_usd": input.Pool.Vol24h.StringFixed(2),
			},
		})
		riskScore += 15
	}

	// high_fee_but_bot_like: if estimated fee APR >= 100% and at least two bot-volume flags present, add critical
	if input.EstimatedFeeAPR.GreaterThanOrEqual(domain.MustDecimal("1")) {
		botFlagCount := 0
		for _, f := range flags {
			switch f.Code {
			case "bot_volume_symmetry", "count_symmetry_only", "low_trader_breadth", "smooth_volume", "price_stasis_high_volume":
				botFlagCount++
			}
		}
		if botFlagCount >= 2 {
			flags = append(flags, Flag{
				Code:     "high_fee_but_bot_like",
				Severity: SeverityCritical,
				Message:  "Estimated fee APR >= 100% but pool exhibits bot-volume patterns",
				Evidence: map[string]string{
					"estimated_fee_apr": input.EstimatedFeeAPR.StringFixed(2),
					"bot_flag_count":    fmt.Sprintf("%d", botFlagCount),
				},
			})
			riskScore += 40
		}
	}

	// Cap risk score at 100
	if riskScore > 100 {
		riskScore = 100
	}

	// Determine verdict
	var verdict Verdict
	switch {
	case hasCritical(flags) || riskScore >= 60:
		verdict = VerdictReject
	case riskScore >= 25:
		verdict = VerdictWatch
	default:
		verdict = VerdictCanaryAllowed
	}

	return Pack{
		PoolID:          input.Pool.ID,
		Verdict:         verdict,
		RiskScore:       riskScore,
		Flags:           flags,
		EstimatedFeeAPR: input.EstimatedFeeAPR,
		VolumeToTVL:     input.VolumeToTVL,
	}
}

func hasCritical(flags []Flag) bool {
	for _, f := range flags {
		if f.Severity == SeverityCritical {
			return true
		}
	}
	return false
}

func min(a, b domain.Decimal) domain.Decimal {
	if a.LessThan(b) {
		return a
	}
	return b
}

func min64(a, b int64) int64 {
	if a < b {
		return a
	}
	return b
}

func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}
