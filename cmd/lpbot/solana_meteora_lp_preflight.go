package main

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

type solanaMeteoraLPPreflightLeg struct {
	Mint             string
	TargetRaw        uint64
	SizeQuoteInRaw   uint64
	SizeQuoteOutRaw  uint64
	SizeQuoteImpact  string
	FundingPlan      solanaFundingPlan
	FundingFromMint  string
	FundingAmountRaw uint64
}

type solanaMeteoraLPPreflightResult struct {
	PoolID                string
	Protocol              string
	Token0                string
	Token1                string
	Wallet                string
	TotalBudgetUSD        domain.Decimal
	RangeLowerPct         domain.Decimal
	RangeUpperPct         domain.Decimal
	PoolPrice             domain.Decimal
	RangeLowerPrice       domain.Decimal
	RangeUpperPrice       domain.Decimal
	EstimatedFeeAPR       domain.Decimal
	EstimatedFeePerDayUSD domain.Decimal
	FundingCostUSD        domain.Decimal
	LPOpenGasUSD          domain.Decimal
	TotalCostUSD          domain.Decimal
	PaybackDays           domain.Decimal
	SOLRequiredRaw        uint64
	USDCRequiredRaw       uint64
	SOLBalanceRaw         uint64
	USDCBalanceRaw        uint64
	ChainValueUSDC        domain.Decimal
	Legs                  []solanaMeteoraLPPreflightLeg
	Verdict               string
	RiskScore             int
	Flags                 []string
	QuoteForwardOK        bool
	QuoteReverseOK        bool
	Ready                 bool
	Blocker               string
}

func runSolanaMeteoraLPPreflight(ctx context.Context, cfg *config.Config, poolID string, userPublicKey string, totalUSD string, rangePct string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) error {
	result, err := buildSolanaMeteoraLPPreflightResult(ctx, cfg, poolID, userPublicKey, totalUSD, rangePct, slippageBPS, maxPriorityLamports, reserveLamports)
	if err != nil {
		return err
	}
	printSolanaMeteoraLPPreflight(result)
	return nil
}

func buildSolanaMeteoraLPPreflightResult(ctx context.Context, cfg *config.Config, poolID string, userPublicKey string, totalUSD string, rangePct string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) (solanaMeteoraLPPreflightResult, error) {
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("meteora pool id is required")
	}
	totalBudgetUSD, err := decimalFromStringStrict(totalUSD)
	if err != nil || !totalBudgetUSD.GreaterThan(domain.ZeroDecimal()) {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("invalid solana meteora lp total usd %q", totalUSD)
	}
	rangePctDec, err := decimalFromStringStrict(rangePct)
	if err != nil || !rangePctDec.GreaterThan(domain.ZeroDecimal()) {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("invalid solana meteora lp range pct %q", rangePct)
	}
	if reserveLamports == 0 {
		reserveLamports = solanaFundingMinReserveLamports
	}

	discovered, err := resolveNativeSolanaPoolForDeepAudit(ctx, solanaTierCDeepAuditTarget{Protocol: "meteora-dlmm", PoolID: poolID})
	if err != nil {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("resolve meteora dlmm pool: %w", err)
	}
	candidate, err := buildSolanaTierCCandidateFromDiscovery(ctx, cfg, discovered)
	if err != nil {
		return solanaMeteoraLPPreflightResult{}, err
	}

	quotes := newSolanaFundingQuoteClient()
	halfUSDCRaw := uint64(totalBudgetUSD.Div(domain.MustDecimal("2")).Mul(domain.MustDecimal("1000000")).Round(0).IntPart())
	if halfUSDCRaw == 0 {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("solana meteora lp budget too small: %s", totalBudgetUSD.String())
	}

	token0 := candidate.Pool.Token0.String()
	token1 := candidate.Pool.Token1.String()
	leg0, err := buildSolanaMeteoraLPPreflightLeg(ctx, cfg, quotes, userPublicKey, token0, halfUSDCRaw, slippageBPS, maxPriorityLamports, reserveLamports)
	if err != nil {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("build token0 leg: %w", err)
	}
	leg1, err := buildSolanaMeteoraLPPreflightLeg(ctx, cfg, quotes, userPublicKey, token1, halfUSDCRaw, slippageBPS, maxPriorityLamports, reserveLamports)
	if err != nil {
		return solanaMeteoraLPPreflightResult{}, fmt.Errorf("build token1 leg: %w", err)
	}

	flags := make([]string, len(candidate.Pack.Flags))
	for i, flag := range candidate.Pack.Flags {
		flags[i] = flag.Code
	}
	result := solanaMeteoraLPPreflightResult{
		PoolID:                candidate.Pool.ID,
		Protocol:              candidate.Pool.Protocol,
		Token0:                token0,
		Token1:                token1,
		Wallet:                leg0.FundingPlan.Wallet,
		TotalBudgetUSD:        totalBudgetUSD,
		RangeLowerPct:         rangePctDec.Neg(),
		RangeUpperPct:         rangePctDec,
		PoolPrice:             candidate.ReferencePriceUSD,
		EstimatedFeeAPR:       candidate.EstimatedFeeAPR,
		EstimatedFeePerDayUSD: totalBudgetUSD.Mul(candidate.EstimatedFeeAPR).Div(domain.MustDecimal("365")),
		Legs:                  []solanaMeteoraLPPreflightLeg{leg0, leg1},
		Verdict:               string(candidate.Pack.Verdict),
		RiskScore:             candidate.Pack.RiskScore,
		Flags:                 flags,
		QuoteForwardOK:        candidate.QuoteCheck.ForwardOK,
		QuoteReverseOK:        candidate.QuoteCheck.ReverseOK,
		SOLBalanceRaw:         leg0.FundingPlan.SOLBalanceRaw,
		USDCBalanceRaw:        leg0.FundingPlan.USDCBalanceRaw,
		ChainValueUSDC:        leg0.FundingPlan.EstimatedChainValueUSDC,
	}
	if result.PoolPrice.GreaterThan(domain.ZeroDecimal()) {
		offset := rangePctDec.Div(domain.MustDecimal("100"))
		result.RangeLowerPrice = result.PoolPrice.Mul(domain.MustDecimal("1").Sub(offset))
		result.RangeUpperPrice = result.PoolPrice.Mul(domain.MustDecimal("1").Add(offset))
	}
	lpGasLamports := maxPriorityLamports + solanaBaseNetworkFeeLamports
	result.LPOpenGasUSD = rawSOLToDecimal(lpGasLamports).Mul(leg0.FundingPlan.EstimatedSOLPriceUSDC)
	result.SOLRequiredRaw = reserveLamports + lpGasLamports
	for _, leg := range result.Legs {
		result.FundingCostUSD = result.FundingCostUSD.Add(leg.FundingPlan.FundingSwapCostUSDC).Add(leg.FundingPlan.FundingNetworkFeeUSDC).Add(leg.FundingPlan.FundingMaxSlippageUSDC)
		if leg.Mint == solanaWrappedSOLAddress {
			result.SOLRequiredRaw += leg.TargetRaw
		}
		if leg.Mint == solanaUSDCAddress {
			result.USDCRequiredRaw += leg.TargetRaw
		}
		if leg.FundingPlan.Status == "requires_prefund_swap" {
			if leg.FundingPlan.FundingMint == solanaWrappedSOLAddress {
				result.SOLRequiredRaw += leg.FundingPlan.FundingAmountInRaw + leg.FundingPlan.FundingNetworkFeeLamports
			}
			if leg.FundingPlan.FundingMint == solanaUSDCAddress {
				result.USDCRequiredRaw += leg.FundingPlan.FundingAmountInRaw
				result.SOLRequiredRaw += leg.FundingPlan.FundingNetworkFeeLamports
			}
		}
	}
	result.TotalCostUSD = result.FundingCostUSD.Add(result.LPOpenGasUSD)
	if result.EstimatedFeePerDayUSD.GreaterThan(domain.ZeroDecimal()) {
		result.PaybackDays = result.TotalCostUSD.Div(result.EstimatedFeePerDayUSD)
	}
	result.Ready, result.Blocker = solanaMeteoraLPPreflightReadiness(result)
	return result, nil
}

func buildSolanaMeteoraLPPreflightLeg(ctx context.Context, cfg *config.Config, quotes *solanaFundingQuoteClient, userPublicKey string, mint string, halfUSDCRaw uint64, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) (solanaMeteoraLPPreflightLeg, error) {
	mint = strings.TrimSpace(mint)
	targetRaw := halfUSDCRaw
	impact := "0"
	if mint != solanaUSDCAddress {
		quote, err := solanaMeteoraQuoteWithRetry(ctx, quotes, solanaUSDCAddress, mint, strconv.FormatUint(halfUSDCRaw, 10), slippageBPS)
		if err != nil {
			return solanaMeteoraLPPreflightLeg{}, err
		}
		targetRaw = mustParseUint64(quote.OutAmount)
		impact = strings.TrimSpace(quote.PriceImpactPct)
	}
	fundingQuotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaFundingPlanWithQuoteRetry(ctx, cfg, userPublicKey, mint, strconv.FormatUint(targetRaw, 10), slippageBPS, maxPriorityLamports, reserveLamports, fundingQuotes)
	if err != nil {
		return solanaMeteoraLPPreflightLeg{}, err
	}
	return solanaMeteoraLPPreflightLeg{
		Mint:             mint,
		TargetRaw:        targetRaw,
		SizeQuoteInRaw:   halfUSDCRaw,
		SizeQuoteOutRaw:  targetRaw,
		SizeQuoteImpact:  impact,
		FundingPlan:      plan,
		FundingFromMint:  plan.FundingMint,
		FundingAmountRaw: plan.FundingAmountInRaw,
	}, nil
}

func solanaMeteoraQuoteWithRetry(ctx context.Context, quotes *solanaFundingQuoteClient, inputMint string, outputMint string, amountRaw string, slippageBPS int) (jupiterQuoteSummary, error) {
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		quote, err := quotes.Quote(ctx, inputMint, outputMint, amountRaw, slippageBPS)
		if err == nil {
			return quote, nil
		}
		lastErr = err
		if !isSolanaMeteoraQuoteCooldown(err) {
			return jupiterQuoteSummary{}, err
		}
		if err := solanaMeteoraWaitForQuoteCooldown(ctx); err != nil {
			return jupiterQuoteSummary{}, err
		}
	}
	return jupiterQuoteSummary{}, lastErr
}

func estimateSolanaFundingPlanWithQuoteRetry(ctx context.Context, cfg *config.Config, userPublicKey string, targetMint string, amountRaw string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, quotes *solanaFundingQuoteClient) (solanaFundingPlan, error) {
	var last solanaFundingPlan
	for attempt := 0; attempt < 3; attempt++ {
		attemptQuotes := quotes
		if attempt > 0 {
			attemptQuotes = newSolanaFundingQuoteClient()
		}
		plan, err := estimateSolanaFundingPlan(ctx, cfg, userPublicKey, targetMint, amountRaw, slippageBPS, maxPriorityLamports, reserveLamports, attemptQuotes)
		if err != nil {
			return solanaFundingPlan{}, err
		}
		last = plan
		if plan.Status != "funding_path_unavailable" || !isSolanaMeteoraRetryableFundingBlocker(plan.Blocker) {
			return plan, nil
		}
		if err := solanaMeteoraWaitForFundingRetry(ctx, plan.Blocker); err != nil {
			return solanaFundingPlan{}, err
		}
	}
	return last, nil
}

func isSolanaMeteoraQuoteCooldown(err error) bool {
	if err == nil {
		return false
	}
	return isSolanaMeteoraQuoteCooldownText(err.Error())
}

func isSolanaMeteoraQuoteCooldownText(value string) bool {
	lower := strings.ToLower(strings.TrimSpace(value))
	return strings.Contains(lower, "cooldown active") || strings.Contains(lower, "status=429") || strings.Contains(lower, "rate limit")
}

func isSolanaMeteoraRetryableFundingBlocker(value string) bool {
	lower := strings.ToLower(strings.TrimSpace(value))
	return isSolanaMeteoraQuoteCooldownText(lower) || strings.Contains(lower, "no same-chain usdc/sol route could fund target mint")
}

func solanaMeteoraWaitForFundingRetry(ctx context.Context, blocker string) error {
	if isSolanaMeteoraQuoteCooldownText(blocker) {
		return solanaMeteoraWaitForQuoteCooldown(ctx)
	}
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func solanaMeteoraWaitForQuoteCooldown(ctx context.Context) error {
	timer := time.NewTimer(solanaFundingQuoteCooldown + time.Second)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func solanaMeteoraLPPreflightReadiness(result solanaMeteoraLPPreflightResult) (bool, string) {
	if result.Protocol != "meteora-dlmm" {
		return false, "protocol_not_meteora_dlmm"
	}
	if strings.EqualFold(result.Verdict, "reject") {
		return false, "tierc_audit_reject"
	}
	if !result.QuoteForwardOK || !result.QuoteReverseOK {
		return false, "jupiter_entry_or_exit_quote_unavailable"
	}
	for _, leg := range result.Legs {
		if leg.TargetRaw == 0 {
			return false, "zero_leg_target"
		}
		switch leg.FundingPlan.Status {
		case "ready_direct", "requires_prefund_swap":
		default:
			return false, "funding_plan_not_ready:" + leg.FundingPlan.Status
		}
	}
	if result.SOLBalanceRaw < result.SOLRequiredRaw {
		return false, "insufficient_combined_sol_after_prefund_and_lp_gas"
	}
	if result.USDCBalanceRaw < result.USDCRequiredRaw {
		return false, "insufficient_combined_usdc_after_prefund"
	}
	if result.EstimatedFeePerDayUSD.LessThanOrEqual(domain.ZeroDecimal()) {
		return false, "fee_projection_unavailable"
	}
	if result.PaybackDays.GreaterThan(domain.MustDecimal("3")) {
		return false, "cost_payback_days_gt_3"
	}
	return true, ""
}

func printSolanaMeteoraLPPreflight(result solanaMeteoraLPPreflightResult) {
	fmt.Printf("solana_meteora_lp_preflight pool_id=%s protocol=%s wallet=%s budget_usd=%s ready=%t blocker=%q verdict=%s risk_score=%d flags=%s\n",
		result.PoolID,
		result.Protocol,
		shortAddress(result.Wallet),
		result.TotalBudgetUSD.StringFixed(2),
		result.Ready,
		result.Blocker,
		result.Verdict,
		result.RiskScore,
		strings.Join(result.Flags, ";"),
	)
	fmt.Printf("solana_meteora_lp_range pool_price=%s range_pct=%s..%s range_price=%s..%s exit_trigger=%q\n",
		result.PoolPrice.StringFixed(12),
		result.RangeLowerPct.StringFixed(2),
		result.RangeUpperPct.StringFixed(2),
		result.RangeLowerPrice.StringFixed(12),
		result.RangeUpperPrice.StringFixed(12),
		"price_outside_range_or_il_gte_1.5pct_or_exit_quote_fails",
	)
	fmt.Printf("solana_meteora_lp_economics est_fee_apr_pct=%s est_fee_day_usd=%s funding_cost_usd=%s lp_open_gas_usd=%s total_cost_usd=%s payback_days=%s quote_forward=%t quote_reverse=%t\n",
		result.EstimatedFeeAPR.Mul(domain.MustDecimal("100")).StringFixed(2),
		result.EstimatedFeePerDayUSD.StringFixed(6),
		result.FundingCostUSD.StringFixed(6),
		result.LPOpenGasUSD.StringFixed(6),
		result.TotalCostUSD.StringFixed(6),
		result.PaybackDays.StringFixed(2),
		result.QuoteForwardOK,
		result.QuoteReverseOK,
	)
	fmt.Printf("solana_meteora_lp_combined_funding same_chain_only=true sol_balance_raw=%d sol_required_raw=%d usdc_balance_raw=%d usdc_required_raw=%d chain_value_usdc=%s\n",
		result.SOLBalanceRaw,
		result.SOLRequiredRaw,
		result.USDCBalanceRaw,
		result.USDCRequiredRaw,
		result.ChainValueUSDC.StringFixed(6),
	)
	for i, leg := range result.Legs {
		fmt.Printf("solana_meteora_lp_leg index=%d mint=%s target_raw=%d sizing_from_usdc_raw=%d sizing_out_raw=%d sizing_impact_pct=%s funding_status=%s funding_blocker=%q direct_balance_raw=%d shortfall_raw=%d prefund_from=%s prefund_amount_raw=%d prefund_expected_out_raw=%d prefund_gas_usd=%s prefund_slippage_usd=%s\n",
			i,
			shortAddress(leg.Mint),
			leg.TargetRaw,
			leg.SizeQuoteInRaw,
			leg.SizeQuoteOutRaw,
			leg.SizeQuoteImpact,
			leg.FundingPlan.Status,
			leg.FundingPlan.Blocker,
			leg.FundingPlan.DirectBalanceRaw,
			leg.FundingPlan.DirectShortfallRaw,
			shortAddress(leg.FundingPlan.FundingMint),
			leg.FundingPlan.FundingAmountInRaw,
			leg.FundingPlan.FundingExpectedOutRaw,
			leg.FundingPlan.FundingNetworkFeeUSDC.StringFixed(6),
			leg.FundingPlan.FundingMaxSlippageUSDC.StringFixed(6),
		)
	}
}
