package tierc

import (
	"strings"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestBuildPack_CHECKNegative(t *testing.T) {
	// CHECK/USDC Aerodrome pool: should reject due to bot-volume patterns
	pool := domain.Pool{
		ID:     "0x3c4384f3664b37a3cb5a5cb3452b4b4a3aa1256f",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0x9126236476EFBA9AD8AB77855C60EB5BF37586EB"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("886992.88"),
		Vol24h: domain.MustDecimal("4790372.57"),
		FeeBPS: 25,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 50},
		EstimatedFeeAPR: domain.MustDecimal("4.9281"), // ~492.81%
		VolumeToTVL:     domain.MustDecimal("5.40"),
		MarketQuality: MarketQuality{
			BuyVolume24hUSD:      domain.MustDecimal("2394000"),
			SellVolume24hUSD:     domain.MustDecimal("2401000"),
			BuyCount24h:          13898,
			SellCount24h:         13874,
			Buyers24h:            133,
			Sellers24h:           166,
			VolumeCV5m:           domain.MustDecimal("0.115"),
			MedianAbsPriceMove5m: domain.MustDecimal("0.00014"),
			Top10HolderPct:       domain.MustDecimal("91.05"),
			KnownHoneypot:        false,
			BuyTaxPct:            domain.ZeroDecimal(),
			SellTaxPct:           domain.ZeroDecimal(),
		},
	}

	pack := BuildPack(input)

	if pack.Verdict != VerdictReject {
		t.Errorf("CHECK negative test: expected verdict=reject, got %s", pack.Verdict)
	}

	codes := make(map[string]bool)
	for _, f := range pack.Flags {
		codes[f.Code] = true
	}

	expectedFlags := []string{
		"bot_volume_symmetry",
		"low_trader_breadth",
		"smooth_volume",
		"high_holder_concentration",
		"high_fee_but_bot_like",
	}
	for _, code := range expectedFlags {
		if !codes[code] {
			t.Errorf("CHECK negative test: expected flag %q not found in %v", code, codes)
		}
	}

	if pack.RiskScore < 60 {
		t.Errorf("CHECK negative test: expected risk_score >= 60 for reject, got %d", pack.RiskScore)
	}
}

func TestBuildPack_CHECKKnownNegativeRejectsWithoutMarketQuality(t *testing.T) {
	pool := domain.Pool{
		ID:     "0x3c4384f3664b37a3cb5a5cb3452b4b4a3aa1256f",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0x9126236476EFBA9AD8AB77855C60EB5BF37586EB"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("886992.88"),
		Vol24h: domain.MustDecimal("4790372.57"),
		FeeBPS: 25,
	}

	pack := BuildPack(PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 40},
		EstimatedFeeAPR: domain.MustDecimal("4.9281"),
		VolumeToTVL:     domain.MustDecimal("5.40"),
	})

	if pack.Verdict != VerdictReject {
		t.Errorf("known CHECK negative: expected verdict=reject, got %s", pack.Verdict)
	}
	found := false
	for _, f := range pack.Flags {
		if f.Code == "known_negative_check" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("known CHECK negative: expected flag known_negative_check")
	}
}

func TestBuildPack_NativeZeroTokenReject(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xtest123",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0x0000000000000000000000000000000000000000"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("100000"),
		Vol24h: domain.MustDecimal("500000"),
		FeeBPS: 30,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 70},
		EstimatedFeeAPR: domain.MustDecimal("0.5"),
		VolumeToTVL:     domain.MustDecimal("5.0"),
		MarketQuality: MarketQuality{
			BuyVolume24hUSD:  domain.MustDecimal("100000"),
			SellVolume24hUSD: domain.MustDecimal("100000"),
			BuyCount24h:      100,
			SellCount24h:     100,
			Buyers24h:        50,
			Sellers24h:       50,
		},
	}

	pack := BuildPack(input)

	if pack.Verdict != VerdictReject {
		t.Errorf("native zero token: expected verdict=reject, got %s", pack.Verdict)
	}

	found := false
	for _, f := range pack.Flags {
		if f.Code == "native_zero_token" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("native zero token: expected flag 'native_zero_token' not found")
	}
}

func TestBuildPack_CleanCanaryAllowed(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xcleantest",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("500000"),
		Vol24h: domain.MustDecimal("300000"),
		FeeBPS: 30,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 65},
		EstimatedFeeAPR: domain.MustDecimal("0.20"),
		VolumeToTVL:     domain.MustDecimal("0.60"),
		MarketQuality: MarketQuality{
			BuyVolume24hUSD:  domain.MustDecimal("150000"),
			SellVolume24hUSD: domain.MustDecimal("120000"),
			BuyCount24h:      500,
			SellCount24h:     450,
			Buyers24h:        200,
			Sellers24h:       180,
			VolumeCV5m:       domain.MustDecimal("0.50"),
			Top10HolderPct:   domain.MustDecimal("45"),
			KnownHoneypot:    false,
			BuyTaxPct:        domain.ZeroDecimal(),
			SellTaxPct:       domain.ZeroDecimal(),
		},
	}

	pack := BuildPack(input)

	if pack.Verdict != VerdictCanaryAllowed {
		t.Errorf("clean canary: expected verdict=canary_allowed, got %s", pack.Verdict)
	}

	if pack.RiskScore >= 25 {
		t.Errorf("clean canary: expected risk_score < 25 for canary_allowed, got %d", pack.RiskScore)
	}
}

func TestBuildPack_WatchVerdict(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xwatchtest",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("100000"),
		Vol24h: domain.MustDecimal("40000"), // below 50000, should trigger low_real_volume warn
		FeeBPS: 30,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 55},
		EstimatedFeeAPR: domain.MustDecimal("0.30"),
		VolumeToTVL:     domain.MustDecimal("0.40"),
		MarketQuality: MarketQuality{
			BuyVolume24hUSD:  domain.MustDecimal("20000"),
			SellVolume24hUSD: domain.MustDecimal("18000"),
			BuyCount24h:      100,
			SellCount24h:     90,
			Buyers24h:        40,
			Sellers24h:       35,
			VolumeCV5m:       domain.MustDecimal("0.10"), // smooth volume
			Top10HolderPct:   domain.MustDecimal("30"),
			KnownHoneypot:    false,
			BuyTaxPct:        domain.ZeroDecimal(),
			SellTaxPct:       domain.ZeroDecimal(),
		},
	}

	pack := BuildPack(input)

	if pack.Verdict != VerdictWatch {
		t.Errorf("watch verdict: expected verdict=watch, got %s", pack.Verdict)
	}
	if pack.RiskScore < 25 {
		t.Errorf("watch verdict: expected risk_score >= 25 for watch, got %d", pack.RiskScore)
	}
}

func TestBuildPack_CountOnlySymmetryWarn(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xcountsymmetry",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("300000"),
		Vol24h: domain.MustDecimal("450000"),
		FeeBPS: 30,
	}

	pack := BuildPack(PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 52},
		EstimatedFeeAPR: domain.MustDecimal("0.40"),
		VolumeToTVL:     domain.MustDecimal("1.50"),
		MarketQuality: MarketQuality{
			BuyCount24h:          1200,
			SellCount24h:         1198,
			Buyers24h:            30,
			Sellers24h:           32,
			VolumeCV5m:           domain.MustDecimal("0.12"),
			MedianAbsPriceMove5m: domain.MustDecimal("0.00030"),
		},
	})

	if pack.Verdict != VerdictWatch && pack.Verdict != VerdictReject {
		t.Fatalf("count-only symmetry: expected watch or reject, got %s", pack.Verdict)
	}
	if !hasFlag(pack.Flags, "count_symmetry_only") {
		t.Fatalf("count-only symmetry: expected count_symmetry_only flag")
	}
}

func TestBuildPack_PriceStasisHighVolumeWarn(t *testing.T) {
	pool := domain.Pool{
		ID:     "0xpricestasis",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("600000"),
		Vol24h: domain.MustDecimal("1800000"),
		FeeBPS: 30,
	}

	pack := BuildPack(PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 60},
		EstimatedFeeAPR: domain.MustDecimal("1.10"),
		VolumeToTVL:     domain.MustDecimal("3.00"),
		MarketQuality: MarketQuality{
			BuyCount24h:          800,
			SellCount24h:         790,
			Buyers24h:            50,
			Sellers24h:           60,
			VolumeCV5m:           domain.MustDecimal("0.10"),
			MedianAbsPriceMove5m: domain.MustDecimal("0.00014"),
		},
	})

	if !hasFlag(pack.Flags, "price_stasis_high_volume") {
		t.Fatalf("price stasis: expected price_stasis_high_volume flag")
	}
}

func TestBuildPack_RiskScoreCap(t *testing.T) {
	// Build a pack that would exceed 100 risk score
	pool := domain.Pool{
		ID:     "0xmaxtest",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0x9126236476EFBA9AD8AB77855C60EB5BF37586EB"),
		Token1: domain.MustParseAddress("0x0000000000000000000000000000000000000000"), // native zero
		TVLUSD: domain.MustDecimal("5000"),                                            // thin_tvl
		Vol24h: domain.MustDecimal("20000"),
		FeeBPS: 100,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 40},
		EstimatedFeeAPR: domain.MustDecimal("5.0"), // >= 100%
		VolumeToTVL:     domain.MustDecimal("4.0"),
		MarketQuality: MarketQuality{
			BuyVolume24hUSD:  domain.MustDecimal("10000"),
			SellVolume24hUSD: domain.MustDecimal("10000"),
			BuyCount24h:      1000,
			SellCount24h:     1000,
			Buyers24h:        10,
			Sellers24h:       10,
			VolumeCV5m:       domain.MustDecimal("0.05"),
			Top10HolderPct:   domain.MustDecimal("95"),
			KnownHoneypot:    true,
			BuyTaxPct:        domain.MustDecimal("5"),
			SellTaxPct:       domain.MustDecimal("5"),
		},
	}

	pack := BuildPack(input)

	if pack.RiskScore > 100 {
		t.Errorf("risk score cap: expected risk_score <= 100, got %d", pack.RiskScore)
	}
}

func TestBuildPack_VerdictRejectOnCritical(t *testing.T) {
	// Pool with honeypot flag should reject regardless of risk score
	pool := domain.Pool{
		ID:     "0xhoneypott",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("1000000"),
		Vol24h: domain.MustDecimal("1000000"),
		FeeBPS: 30,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 80},
		EstimatedFeeAPR: domain.MustDecimal("0.10"),
		VolumeToTVL:     domain.MustDecimal("1.0"),
		MarketQuality: MarketQuality{
			Top10HolderPct: domain.MustDecimal("20"),
			KnownHoneypot:  true,
			BuyTaxPct:      domain.ZeroDecimal(),
			SellTaxPct:     domain.ZeroDecimal(),
		},
	}

	pack := BuildPack(input)

	if pack.Verdict != VerdictReject {
		t.Errorf("honeypot reject: expected verdict=reject, got %s", pack.Verdict)
	}

	found := false
	for _, f := range pack.Flags {
		if f.Code == "token_tax_or_honeypot" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("honeypot reject: expected flag 'token_tax_or_honeypot' not found")
	}
}

func TestBuildPack_FlagCodes(t *testing.T) {
	// Verify flag codes are semicolon-friendly (no special chars)
	pool := domain.Pool{
		ID:     "0xflagtest",
		Chain:  domain.ChainBase,
		Token0: domain.MustParseAddress("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
		Token1: domain.MustParseAddress("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
		TVLUSD: domain.MustDecimal("10000"),
		Vol24h: domain.MustDecimal("20000"),
		FeeBPS: 30,
	}
	input := PackInput{
		Pool:            pool,
		Score:           domain.Score{Total: 50},
		EstimatedFeeAPR: domain.MustDecimal("0.50"),
		VolumeToTVL:     domain.MustDecimal("2.0"),
		MarketQuality: MarketQuality{
			Top10HolderPct: domain.MustDecimal("90"),
		},
	}

	pack := BuildPack(input)

	for _, f := range pack.Flags {
		if strings.Contains(f.Code, "|") || strings.Contains(f.Code, ";") {
			t.Errorf("flag code %q should not contain | or ;", f.Code)
		}
	}
}

func hasFlag(flags []Flag, code string) bool {
	for _, flag := range flags {
		if flag.Code == code {
			return true
		}
	}
	return false
}
