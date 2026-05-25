package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/tierc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

type solanaTierCCandidate struct {
	Pool              domain.Pool
	Score             domain.Score
	EstimatedFeeAPR   domain.Decimal
	VolumeToTVL       domain.Decimal
	ReferencePriceUSD domain.Decimal
	MarketQuality     tierc.MarketQuality
	QuoteCheck        solanaTierCQuoteCheck
	LPPlan            solanaTierCLPPlan
	Pack              tierc.Pack
}

type solanaTierCLPPlan struct {
	BudgetUSD       domain.Decimal
	RangeLowerPct   domain.Decimal
	RangeUpperPct   domain.Decimal
	RangeLowerPrice domain.Decimal
	RangeUpperPrice domain.Decimal
	EstFeePerDayUSD domain.Decimal
	CostCapUSD      domain.Decimal
	MinHoldDays     domain.Decimal
	ExitTrigger     string
}

type solanaTierCQuoteCheck struct {
	ForwardOK        bool
	ReverseOK        bool
	Reason           string
	ForwardImpactPct string
	ReverseImpactPct string
	ForwardRoutes    int
	ReverseRoutes    int
	Error            string
}

type solanaTierCQuoteCollector struct {
	mu        sync.Mutex
	cache     map[string]solanaTierCQuoteCheck
	nextQuote time.Time
	minGap    time.Duration
}

func newSolanaTierCQuoteCollector() *solanaTierCQuoteCollector {
	return &solanaTierCQuoteCollector{
		cache:  make(map[string]solanaTierCQuoteCheck),
		minGap: 1200 * time.Millisecond,
	}
}

func (c *solanaTierCQuoteCollector) Collect(ctx context.Context, pool domain.Pool) solanaTierCQuoteCheck {
	key := pool.ID + "|" + pool.Token0.String() + "|" + pool.Token1.String()
	c.mu.Lock()
	if cached, ok := c.cache[key]; ok {
		c.mu.Unlock()
		return cached
	}
	waitFor := time.Duration(0)
	now := time.Now()
	if c.nextQuote.After(now) {
		waitFor = c.nextQuote.Sub(now)
		now = c.nextQuote
	}
	c.nextQuote = now.Add(c.minGap)
	c.mu.Unlock()
	if waitFor > 0 {
		timer := time.NewTimer(waitFor)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			return solanaTierCQuoteCheck{Error: ctx.Err().Error()}
		case <-timer.C:
		}
	}
	check := collectSolanaTierCQuoteCheck(ctx, pool)
	if check.Reason == "rate_limited" {
		timer := time.NewTimer(3 * time.Second)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			check.Error = ctx.Err().Error()
			check.Reason = "transient_http_error"
		case <-timer.C:
			check = collectSolanaTierCQuoteCheck(ctx, pool)
		}
	}
	c.mu.Lock()
	c.cache[key] = check
	c.mu.Unlock()
	return check
}

func runSolanaTierCDiscovery(ctx context.Context, cfg *config.Config, minTVLUSD, maxTVLUSD, minVol24hUSD, minVolumeToTVL domain.Decimal, limit int, jsonOut string, includeRejects bool, majorOnly bool, protocolFilter string) error {
	if limit <= 0 {
		limit = 10
	}
	if minTVLUSD.IsZero() {
		minTVLUSD = domain.MustDecimal("10000")
	}
	if maxTVLUSD.IsZero() {
		maxTVLUSD = domain.MustDecimal("1500000")
	}
	if minVol24hUSD.IsZero() {
		minVol24hUSD = domain.MustDecimal("25000")
	}
	if minVolumeToTVL.IsZero() {
		minVolumeToTVL = domain.MustDecimal("0.75")
	}
	protocolFilter = strings.ToLower(strings.TrimSpace(protocolFilter))

	discoveryLimit := limit * 4
	if discoveryLimit < 20 {
		discoveryLimit = 20
	}
	pools, source, err := discoverNativeSolanaPools(ctx, protocolFilter, minTVLUSD, discoveryLimit)
	if err == nil && len(pools) > 0 {
		fmt.Printf("solana_tierc_discovery_source=%s\n", source)
	} else {
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: solana native discovery unavailable: %v\n", err)
		}
		ds := geckoterminal.NewAdapter()
		pools, err = ds.DiscoverPools(ctx, domain.ChainSolana, "", minTVLUSD, discoveryLimit)
		if err != nil {
			fallback := dexscreener.NewAdapter()
			fallbackPools, fallbackErr := fallback.DiscoverPools(ctx, domain.ChainSolana, "", minTVLUSD, discoveryLimit)
			if fallbackErr == nil && len(fallbackPools) > 0 {
				pools = fallbackPools
				fmt.Println("solana_tierc_discovery_source=dexscreener")
			} else {
				cached, cachedErr := loadCachedSolanaDiscoveryPools(ctx, cfg, discoveryLimit)
				if cachedErr != nil || len(cached) == 0 {
					return fmt.Errorf("solana tier C discovery failed: %w; dexscreener unavailable: %v; cached pools unavailable: %v", err, fallbackErr, cachedErr)
				}
				pools = cached
				fmt.Println("solana_tierc_discovery_source=postgres_cache")
			}
		} else {
			fmt.Println("solana_tierc_discovery_source=geckoterminal")
		}
	}

	scorer := scanner.New(scanner.Config{})
	qualityCollector := newSolanaTierCMarketQualityCollector()
	quoteCollector := newSolanaTierCQuoteCollector()
	candidates := make([]solanaTierCCandidate, 0, len(pools))
	for _, discovered := range pools {
		if discovered.Chain != domain.ChainSolana {
			continue
		}
		if discovered.TVLUSD.LessThan(minTVLUSD) || discovered.TVLUSD.GreaterThan(maxTVLUSD) {
			continue
		}
		if discovered.Vol24h.LessThan(minVol24hUSD) || discovered.TVLUSD.IsZero() {
			continue
		}
		volToTVL := discovered.Vol24h.Div(discovered.TVLUSD)
		if volToTVL.LessThan(minVolumeToTVL) {
			continue
		}
		if protocolFilter != "" && strings.ToLower(strings.TrimSpace(discovered.Protocol)) != protocolFilter {
			continue
		}
		if majorOnly && !isSolanaMajorAssetPair(discovered.Token0, discovered.Token1) {
			continue
		}

		pool := domain.Pool{
			ID:        discovered.ID,
			Chain:     discovered.Chain,
			Protocol:  discovered.Protocol,
			Token0:    discovered.Token0,
			Token1:    discovered.Token1,
			FeeBPS:    discovered.FeeBPS,
			TVLUSD:    discovered.TVLUSD,
			Vol24h:    discovered.Vol24h,
			UpdatedAt: discovered.UpdatedAt.Unix(),
		}
		score, scoreErr := scorer.Score(ctx, pool)
		if scoreErr != nil {
			continue
		}
		pool.Tier_ = score.AssignTier()
		estimatedFeeAPR := estimatePoolFeeAPR(pool)
		marketQuality, qualityErr := qualityCollector.Collect(ctx, pool)
		if qualityErr != nil {
			fmt.Fprintf(os.Stderr, "warning: solana tierc market quality partial for %s: %v\n", pool.ID, qualityErr)
		}
		pack := tierc.BuildPack(buildPackInput(pool, score, estimatedFeeAPR, volToTVL, marketQuality))
		tokenSafety, tokenSafetyErr := collectSolanaPoolTokenSafety(ctx, cfg, pool)
		quoteCheck := quoteCollector.Collect(ctx, pool)
		applySolanaTierCGuards(pool, marketQuality, qualityErr, tokenSafety, tokenSafetyErr, quoteCheck, &pack)
		applySolanaTierCTokenProfileGuards(pool, discovered.PriceUSD, quoteCheck, estimatedFeeAPR, &pack)
		finalizeSolanaTierCVerdict(&pack)
		lpPlan := buildSolanaTierCLPPlan(discovered.PriceUSD, estimatedFeeAPR)

		candidates = append(candidates, solanaTierCCandidate{
			Pool:              pool,
			Score:             score,
			EstimatedFeeAPR:   estimatedFeeAPR,
			VolumeToTVL:       volToTVL,
			ReferencePriceUSD: discovered.PriceUSD,
			MarketQuality:     marketQuality,
			QuoteCheck:        quoteCheck,
			LPPlan:            lpPlan,
			Pack:              pack,
		})
	}

	sort.SliceStable(candidates, func(i, j int) bool {
		vi := tierCDiscoveryVerdictRank(candidates[i].Pack.Verdict)
		vj := tierCDiscoveryVerdictRank(candidates[j].Pack.Verdict)
		if vi != vj {
			return vi < vj
		}
		pi := solanaProtocolPriority(candidates[i].Pool.Protocol)
		pj := solanaProtocolPriority(candidates[j].Pool.Protocol)
		if pi != pj {
			return pi < pj
		}
		if !candidates[i].VolumeToTVL.Equal(candidates[j].VolumeToTVL) {
			return candidates[i].VolumeToTVL.GreaterThan(candidates[j].VolumeToTVL)
		}
		if !candidates[i].EstimatedFeeAPR.Equal(candidates[j].EstimatedFeeAPR) {
			return candidates[i].EstimatedFeeAPR.GreaterThan(candidates[j].EstimatedFeeAPR)
		}
		return candidates[i].Pool.TVLUSD.LessThan(candidates[j].Pool.TVLUSD)
	})

	fmt.Printf("solana_tierc_discovery filters min_tvl_usd=%s max_tvl_usd=%s min_vol24h_usd=%s min_vol_tvl=%s limit=%d scanned=%d matched=%d\n",
		minTVLUSD.StringFixed(0),
		maxTVLUSD.StringFixed(0),
		minVol24hUSD.StringFixed(0),
		minVolumeToTVL.StringFixed(2),
		limit,
		len(pools),
		len(candidates),
	)
	fmt.Println("rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|range_pct|range_price|est_fee_day_usd|cost_cap_usd|min_hold_days|exit_trigger|buy_count_24h|sell_count_24h|quote_forward|quote_reverse|quote_reason|quote_impact_fwd|quote_impact_rev|token0|token1|pool_url")

	rank := 0
	for i := 0; i < len(candidates) && rank < limit; i++ {
		c := candidates[i]
		if !includeRejects && c.Pack.Verdict == tierc.VerdictReject {
			continue
		}
		rank++
		printSolanaTierCCandidateLine(rank, c)
	}
	if len(candidates) == 0 {
		fmt.Println("solana_tierc_discovery no candidates matched current filters")
	}
	if jsonOut != "" {
		if err := writeSolanaTierCJSONOutput(jsonOut, candidates, includeRejects); err != nil {
			fmt.Fprintf(os.Stderr, "warning: failed to write Solana Tier C JSON output: %v\n", err)
		}
	}
	return nil
}

func runSolanaTierCAuditPool(ctx context.Context, cfg *config.Config, poolID string, jsonOut string) error {
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return fmt.Errorf("pool id is required")
	}
	if discovered, err := resolveNativeSolanaPoolForDeepAudit(ctx, solanaTierCDeepAuditTarget{PoolID: poolID}); err == nil {
		candidate, err := buildSolanaTierCCandidateFromDiscovery(ctx, cfg, discovered)
		if err != nil {
			return err
		}
		fmt.Printf("solana_tierc_audit_pool pool_id=%s source=native protocol=%s\n", candidate.Pool.ID, candidate.Pool.Protocol)
		fmt.Println("rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|range_pct|range_price|est_fee_day_usd|cost_cap_usd|min_hold_days|exit_trigger|buy_count_24h|sell_count_24h|quote_forward|quote_reverse|quote_reason|quote_impact_fwd|quote_impact_rev|token0|token1|pool_url")
		printSolanaTierCCandidateLine(1, candidate)
		if jsonOut != "" {
			return writeSolanaTierCJSONOutput(jsonOut, []solanaTierCCandidate{candidate}, true)
		}
		return nil
	}
	ds := geckoterminal.NewAdapter()
	metadata, err := ds.GetPoolMetadata(ctx, domain.ChainSolana, poolID)
	if err != nil {
		return fmt.Errorf("resolve solana pool metadata: %w", err)
	}
	if metadata == nil {
		return fmt.Errorf("solana pool not found: %s", poolID)
	}
	pool := domain.Pool{
		ID:        metadata.ID,
		Chain:     metadata.Chain,
		Protocol:  metadata.Protocol,
		Token0:    metadata.Token0,
		Token1:    metadata.Token1,
		FeeBPS:    metadata.FeeBPS,
		TVLUSD:    metadata.TVLUSD,
		Vol24h:    metadata.Vol24h,
		UpdatedAt: metadata.UpdatedAt.Unix(),
	}
	score, err := scanner.New(scanner.Config{}).Score(ctx, pool)
	if err != nil {
		return fmt.Errorf("score solana pool: %w", err)
	}
	pool.Tier_ = score.AssignTier()
	estimatedFeeAPR := estimatePoolFeeAPR(pool)
	volumeToTVL := domain.ZeroDecimal()
	if !pool.TVLUSD.IsZero() {
		volumeToTVL = pool.Vol24h.Div(pool.TVLUSD)
	}
	qualityCollector := newSolanaTierCMarketQualityCollector()
	marketQuality, qualityErr := qualityCollector.Collect(ctx, pool)
	if qualityErr != nil {
		fmt.Fprintf(os.Stderr, "warning: solana tierc market quality partial for %s: %v\n", pool.ID, qualityErr)
	}
	pack := tierc.BuildPack(buildPackInput(pool, score, estimatedFeeAPR, volumeToTVL, marketQuality))
	tokenSafety, tokenSafetyErr := collectSolanaPoolTokenSafety(ctx, cfg, pool)
	quoteCheck := newSolanaTierCQuoteCollector().Collect(ctx, pool)
	applySolanaTierCGuards(pool, marketQuality, qualityErr, tokenSafety, tokenSafetyErr, quoteCheck, &pack)
	applySolanaTierCTokenProfileGuards(pool, metadata.PriceUSD, quoteCheck, estimatedFeeAPR, &pack)
	finalizeSolanaTierCVerdict(&pack)
	lpPlan := buildSolanaTierCLPPlan(metadata.PriceUSD, estimatedFeeAPR)

	candidate := solanaTierCCandidate{
		Pool:              pool,
		Score:             score,
		EstimatedFeeAPR:   estimatedFeeAPR,
		VolumeToTVL:       volumeToTVL,
		ReferencePriceUSD: metadata.PriceUSD,
		MarketQuality:     marketQuality,
		QuoteCheck:        quoteCheck,
		LPPlan:            lpPlan,
		Pack:              pack,
	}
	fmt.Printf("solana_tierc_audit_pool pool_id=%s source=geckoterminal protocol=%s\n", pool.ID, pool.Protocol)
	fmt.Println("rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|range_pct|range_price|est_fee_day_usd|cost_cap_usd|min_hold_days|exit_trigger|buy_count_24h|sell_count_24h|quote_forward|quote_reverse|quote_reason|quote_impact_fwd|quote_impact_rev|token0|token1|pool_url")
	printSolanaTierCCandidateLine(1, candidate)
	if jsonOut != "" {
		return writeSolanaTierCJSONOutput(jsonOut, []solanaTierCCandidate{candidate}, true)
	}
	return nil
}

type solanaTierCMarketQualityCollector struct {
	client *dexscreener.Client
}

func newSolanaTierCMarketQualityCollector() solanaTierCMarketQualityCollector {
	return solanaTierCMarketQualityCollector{client: dexscreener.NewClient()}
}

func (c solanaTierCMarketQualityCollector) Collect(ctx context.Context, pool domain.Pool) (tierc.MarketQuality, error) {
	info, err := c.client.GetPoolByAddress(ctx, domain.ChainSolana.String(), pool.ID)
	if err != nil {
		return tierc.MarketQuality{}, err
	}
	if info == nil {
		return tierc.MarketQuality{}, fmt.Errorf("pool not found in dexscreener")
	}
	return tierc.MarketQuality{
		BuyCount24h:  int64(info.Txns.H24.Buys),
		SellCount24h: int64(info.Txns.H24.Sells),
	}, nil
}

type solanaTokenSafety struct {
	Token                  string
	MintAuthorityPresent   bool
	FreezeAuthorityPresent bool
	Token2022              bool
}

func applySolanaTierCGuards(pool domain.Pool, marketQuality tierc.MarketQuality, qualityErr error, tokenSafety []solanaTokenSafety, tokenSafetyErr error, quoteCheck solanaTierCQuoteCheck, pack *tierc.Pack) {
	if pack == nil {
		return
	}
	if pool.FeeBPS == 0 {
		addTierCFlag(pack, "solana_fee_bps_unknown", tierc.SeverityWarn, "Pool fee bps is missing or zero; LP fee projection cannot be trusted for canary sizing")
	}
	if !isSolanaTierCProtocolKnown(pool.Protocol) {
		addTierCFlag(pack, "solana_protocol_unproven", tierc.SeverityWarn, "Solana DEX protocol is not in the first-pass Tier C allowlist")
	}
	if solanaProtocolPriority(pool.Protocol) >= 4 {
		addTierCFlag(pack, "solana_protocol_low_priority", tierc.SeverityWarn, "Protocol is not in the top-priority Solana LP implementation lane")
	}
	if !isSolanaMajorAssetPair(pool.Token0, pool.Token1) {
		addTierCFlag(pack, "solana_non_major_pair", tierc.SeverityWarn, "Pair is not SOL/USDC, SOL/USDT, or SOL/JitoSOL; keep in watch until token-level safety checks are added")
	}
	if qualityErr != nil && marketQuality.BuyCount24h == 0 && marketQuality.SellCount24h == 0 {
		addTierCFlag(pack, "market_quality_incomplete", tierc.SeverityWarn, "Solana market-quality enrichment is incomplete; keep in watch until single-pool audit confirms it")
	}
	if tokenSafetyErr != nil {
		addTierCFlag(pack, "solana_token_safety_incomplete", tierc.SeverityWarn, "Solana token mint/freeze safety check did not complete")
	}
	if !quoteCheck.ForwardOK || !quoteCheck.ReverseOK {
		addTierCFlag(pack, "solana_jupiter_quote_incomplete", tierc.SeverityWarn, "Jupiter 1 USDC round-trip quote is not available in both directions")
	}
	switch quoteCheck.Reason {
	case "route_unavailable", "forward_zero_output":
		addTierCFlag(pack, "solana_jupiter_route_unavailable", tierc.SeverityCritical, "Jupiter cannot provide a safe 1 USDC round-trip route; LP funding or exit may be blocked")
	case "rate_limited", "transient_http_error":
		addTierCFlag(pack, "solana_jupiter_quote_transient_error", tierc.SeverityWarn, "Jupiter quote failed with a transient HTTP/rate-limit style error")
	case "unknown_error":
		addTierCFlag(pack, "solana_jupiter_quote_unknown_error", tierc.SeverityWarn, "Jupiter quote failed with an unclassified error")
	}
	if isSolanaHighFrequencySymmetricFlow(pool, marketQuality) {
		addTierCFlag(pack, "solana_high_frequency_count_symmetry", tierc.SeverityCritical, "High-frequency buy/sell counts are mirror-like while volume/TVL is elevated; likely bot or incentive-driven flow")
	}
	for _, safety := range tokenSafety {
		if safety.FreezeAuthorityPresent {
			addTierCFlag(pack, "solana_freeze_authority_present", tierc.SeverityCritical, "Solana token has freeze authority")
		}
		if safety.Token2022 {
			addTierCFlag(pack, "solana_token2022_extension", tierc.SeverityCritical, "Solana token uses Token-2022; LP canary stays blocked until extension behavior is explicitly supported")
		}
		if safety.MintAuthorityPresent {
			addTierCFlag(pack, "solana_mint_authority_present", tierc.SeverityWarn, "Solana token still has mint authority")
		}
	}
	if hasTierCFlag(*pack, "market_quality_incomplete") ||
		hasTierCFlag(*pack, "solana_protocol_unproven") ||
		hasTierCFlag(*pack, "solana_non_major_pair") ||
		hasTierCFlag(*pack, "solana_fee_bps_unknown") ||
		hasTierCFlag(*pack, "solana_mint_authority_present") ||
		hasTierCFlag(*pack, "solana_token_safety_incomplete") ||
		hasTierCFlag(*pack, "solana_jupiter_quote_incomplete") {
		if pack.Verdict == tierc.VerdictCanaryAllowed {
			pack.Verdict = tierc.VerdictWatch
		}
		if pack.RiskScore < 20 {
			pack.RiskScore = 20
		}
	}
	if hasTierCFlag(*pack, "solana_high_frequency_count_symmetry") {
		pack.Verdict = tierc.VerdictReject
		if pack.RiskScore < 60 {
			pack.RiskScore = 60
		}
	}
	if hasTierCFlag(*pack, "solana_jupiter_route_unavailable") {
		pack.Verdict = tierc.VerdictReject
		if pack.RiskScore < 60 {
			pack.RiskScore = 60
		}
	}
}

func applySolanaTierCTokenProfileGuards(pool domain.Pool, referencePriceUSD domain.Decimal, quoteCheck solanaTierCQuoteCheck, estimatedFeeAPR domain.Decimal, pack *tierc.Pack) {
	if pack == nil {
		return
	}
	if !isSolanaMajorAssetPair(pool.Token0, pool.Token1) && (isLikelyPumpFunMint(pool.Token0.String()) || isLikelyPumpFunMint(pool.Token1.String())) {
		addTierCFlag(pack, "solana_pump_fun_token", tierc.SeverityCritical, "Pair includes a likely pump.fun token mint; keep blocked from canary LP until holder and route quality pass deeper review")
	}
	if !isSolanaMajorAssetPair(pool.Token0, pool.Token1) && referencePriceUSD.GreaterThan(domain.ZeroDecimal()) && referencePriceUSD.LessThan(domain.MustDecimal("0.00001")) {
		addTierCFlag(pack, "solana_micro_price_token", tierc.SeverityWarn, "Reference price is below 0.00001 USD; sizing, slippage, and price-range math are more fragile")
	}
	if !isSolanaMajorAssetPair(pool.Token0, pool.Token1) && (!quoteCheck.ForwardOK || !quoteCheck.ReverseOK) {
		addTierCFlag(pack, "solana_non_major_quote_unstable", tierc.SeverityWarn, "Non-major token does not have stable round-trip quote evidence")
	}
	if !isSolanaMajorAssetPair(pool.Token0, pool.Token1) && estimatedFeeAPR.GreaterThanOrEqual(domain.MustDecimal("10")) {
		addTierCFlag(pack, "solana_extreme_fee_apr_non_major", tierc.SeverityWarn, "Estimated fee APR exceeds 1000% on a non-major pair; likely incentive, bot, or ephemeral flow")
	}
	if hasTierCFlag(*pack, "solana_pump_fun_token") {
		pack.Verdict = tierc.VerdictReject
		if pack.RiskScore < 60 {
			pack.RiskScore = 60
		}
	}
	if hasTierCFlag(*pack, "solana_non_major_quote_unstable") && hasTierCFlag(*pack, "solana_micro_price_token") {
		pack.Verdict = tierc.VerdictReject
		if pack.RiskScore < 60 {
			pack.RiskScore = 60
		}
	}
	if hasTierCFlag(*pack, "solana_extreme_fee_apr_non_major") && hasTierCFlag(*pack, "solana_jupiter_quote_incomplete") {
		pack.Verdict = tierc.VerdictReject
		if pack.RiskScore < 60 {
			pack.RiskScore = 60
		}
	}
}

func isLikelyPumpFunMint(token string) bool {
	return strings.HasSuffix(strings.TrimSpace(token), "pump")
}

func finalizeSolanaTierCVerdict(pack *tierc.Pack) {
	if pack == nil {
		return
	}
	if pack.RiskScore >= 60 {
		pack.Verdict = tierc.VerdictReject
		return
	}
	if pack.RiskScore >= 25 && pack.Verdict == tierc.VerdictCanaryAllowed {
		pack.Verdict = tierc.VerdictWatch
	}
}

func classifySolanaJupiterQuoteFailure(message string) string {
	normalized := strings.ToLower(strings.TrimSpace(message))
	switch {
	case normalized == "":
		return "unknown_error"
	case strings.Contains(normalized, "429") ||
		strings.Contains(normalized, "rate limit") ||
		strings.Contains(normalized, "too many requests"):
		return "rate_limited"
	case strings.Contains(normalized, "no route") ||
		strings.Contains(normalized, "route not found") ||
		strings.Contains(normalized, "could not find") ||
		strings.Contains(normalized, "not tradable") ||
		strings.Contains(normalized, "token not tradable") ||
		strings.Contains(normalized, "market not found"):
		return "route_unavailable"
	case strings.Contains(normalized, "status=5") ||
		strings.Contains(normalized, "status=502") ||
		strings.Contains(normalized, "status=503") ||
		strings.Contains(normalized, "status=504") ||
		strings.Contains(normalized, "timeout") ||
		strings.Contains(normalized, "context deadline"):
		return "transient_http_error"
	default:
		return "unknown_error"
	}
}

func isSolanaHighFrequencySymmetricFlow(pool domain.Pool, marketQuality tierc.MarketQuality) bool {
	if marketQuality.BuyCount24h < 10000 || marketQuality.SellCount24h < 10000 {
		return false
	}
	minCount := marketQuality.BuyCount24h
	maxCount := marketQuality.SellCount24h
	if minCount > maxCount {
		minCount, maxCount = maxCount, minCount
	}
	if maxCount == 0 {
		return false
	}
	countSymmetry := domain.NewDecimalFromInt(minCount).Div(domain.NewDecimalFromInt(maxCount))
	volumeToTVL := domain.ZeroDecimal()
	if !pool.TVLUSD.IsZero() {
		volumeToTVL = pool.Vol24h.Div(pool.TVLUSD)
	}
	return countSymmetry.GreaterThanOrEqual(domain.MustDecimal("0.97")) && volumeToTVL.GreaterThanOrEqual(domain.MustDecimal("5.00"))
}

func collectSolanaPoolTokenSafety(ctx context.Context, cfg *config.Config, pool domain.Pool) ([]solanaTokenSafety, error) {
	endpoint := solanaReadinessEndpoint(cfg)
	if strings.TrimSpace(endpoint) == "" {
		return nil, fmt.Errorf("solana rpc endpoint is empty")
	}
	tokens := []domain.Address{pool.Token0, pool.Token1}
	out := make([]solanaTokenSafety, 0, len(tokens))
	var lastErr error
	for _, token := range tokens {
		if token.IsZero() {
			continue
		}
		safety, err := fetchSolanaTokenSafety(ctx, endpoint, token.String())
		if err != nil {
			lastErr = err
			continue
		}
		out = append(out, safety)
	}
	if lastErr != nil && len(out) == 0 {
		return out, lastErr
	}
	return out, nil
}

func collectSolanaTierCQuoteCheck(ctx context.Context, pool domain.Pool) solanaTierCQuoteCheck {
	target := pool.Token0.String()
	if target == solanaUSDCAddress {
		target = pool.Token1.String()
	}
	check := solanaTierCQuoteCheck{}
	_, forward, err := fetchJupiterQuote(ctx, solanaUSDCAddress, target, "1000000", 100)
	if err != nil {
		check.Error = err.Error()
		check.Reason = classifySolanaJupiterQuoteFailure(check.Error)
		return check
	}
	check.ForwardOK = true
	check.ForwardImpactPct = forward.PriceImpactPct
	check.ForwardRoutes = len(forward.RoutePlan)
	if strings.TrimSpace(forward.OutAmount) == "" || forward.OutAmount == "0" {
		check.Error = "forward quote returned zero output"
		check.Reason = "forward_zero_output"
		check.ForwardOK = false
		return check
	}
	_, reverse, err := fetchJupiterQuote(ctx, target, solanaUSDCAddress, forward.OutAmount, 100)
	if err != nil {
		check.Error = err.Error()
		check.Reason = classifySolanaJupiterQuoteFailure(check.Error)
		return check
	}
	check.ReverseOK = true
	check.ReverseImpactPct = reverse.PriceImpactPct
	check.ReverseRoutes = len(reverse.RoutePlan)
	return check
}

func fetchSolanaTokenSafety(ctx context.Context, endpoint string, token string) (solanaTokenSafety, error) {
	raw, err := solanaJSONRPC(ctx, endpoint, "getAccountInfo", []any{
		token,
		map[string]any{"encoding": "jsonParsed", "commitment": "processed"},
	})
	if err != nil {
		return solanaTokenSafety{Token: token}, err
	}
	var decoded struct {
		Value *struct {
			Owner string `json:"owner"`
			Data  struct {
				Parsed *struct {
					Info map[string]any `json:"info"`
				} `json:"parsed"`
			} `json:"data"`
		} `json:"value"`
	}
	if err := json.Unmarshal(raw, &decoded); err != nil {
		return solanaTokenSafety{Token: token}, fmt.Errorf("decode token account info: %w", err)
	}
	if decoded.Value == nil || decoded.Value.Data.Parsed == nil {
		return solanaTokenSafety{Token: token}, fmt.Errorf("token mint account not found or not jsonParsed")
	}
	info := decoded.Value.Data.Parsed.Info
	safety := solanaTokenSafety{
		Token:     token,
		Token2022: decoded.Value.Owner == "TokenzQdBNbLqP5VEhdkAS6EPqJz6tb2AAi9JXn3Ukio9",
	}
	if value, ok := info["mintAuthority"]; ok && value != nil && strings.TrimSpace(fmt.Sprint(value)) != "" && fmt.Sprint(value) != "<nil>" {
		safety.MintAuthorityPresent = true
	}
	if value, ok := info["freezeAuthority"]; ok && value != nil && strings.TrimSpace(fmt.Sprint(value)) != "" && fmt.Sprint(value) != "<nil>" {
		safety.FreezeAuthorityPresent = true
	}
	return safety, nil
}

func addTierCFlag(pack *tierc.Pack, code string, severity tierc.FlagSeverity, message string) {
	if hasTierCFlag(*pack, code) {
		return
	}
	pack.Flags = append(pack.Flags, tierc.Flag{Code: code, Severity: severity, Message: message})
	switch severity {
	case tierc.SeverityCritical:
		pack.RiskScore += 40
	case tierc.SeverityWarn:
		pack.RiskScore += 20
	default:
		pack.RiskScore += 5
	}
	if pack.RiskScore >= 40 && severity == tierc.SeverityCritical {
		pack.Verdict = tierc.VerdictReject
	}
}

func hasTierCFlag(pack tierc.Pack, code string) bool {
	for _, flag := range pack.Flags {
		if flag.Code == code {
			return true
		}
	}
	return false
}

func isSolanaTierCProtocolKnown(protocol string) bool {
	switch strings.ToLower(strings.TrimSpace(protocol)) {
	case "orca-whirlpool", "raydium-clmm", "raydium", "meteora", "meteora-dlmm", "pancakeswap-v3-solana":
		return true
	default:
		return false
	}
}

func solanaProtocolPriority(protocol string) int {
	switch strings.ToLower(strings.TrimSpace(protocol)) {
	case "raydium-clmm", "raydium":
		return 1
	case "orca-whirlpool":
		return 2
	case "meteora-dlmm":
		return 3
	case "meteora":
		return 4
	case "pancakeswap-v3-solana":
		return 5
	default:
		return 9
	}
}

func isSolanaMajorAssetPair(token0 domain.Address, token1 domain.Address) bool {
	a := token0.String()
	b := token1.String()
	return isSolanaMajorAsset(a) && isSolanaMajorAsset(b)
}

func isSolanaMajorAsset(token string) bool {
	switch token {
	case solanaWrappedSOLAddress, solanaUSDCAddress, "Es9vMFrzaCERmJfrF4H2FYD4G5DzzU6rybbtXdy41vP":
		return true
	default:
		return false
	}
}

func buildSolanaTierCLPPlan(referencePriceUSD domain.Decimal, estimatedFeeAPR domain.Decimal) solanaTierCLPPlan {
	budget := domain.MustDecimal("10")
	rangeLowerPct := domain.MustDecimal("-2.50")
	rangeUpperPct := domain.MustDecimal("2.50")
	costCap := domain.MustDecimal("0.16")
	plan := solanaTierCLPPlan{
		BudgetUSD:       budget,
		RangeLowerPct:   rangeLowerPct,
		RangeUpperPct:   rangeUpperPct,
		CostCapUSD:      costCap,
		EstFeePerDayUSD: budget.Mul(estimatedFeeAPR).Div(domain.MustDecimal("365")),
		ExitTrigger:     "price_outside_range_or_il_gte_1.5pct_or_fee_rate_untrusted",
	}
	if referencePriceUSD.GreaterThan(domain.ZeroDecimal()) {
		plan.RangeLowerPrice = referencePriceUSD.Mul(domain.MustDecimal("0.975"))
		plan.RangeUpperPrice = referencePriceUSD.Mul(domain.MustDecimal("1.025"))
	}
	if plan.EstFeePerDayUSD.GreaterThan(domain.ZeroDecimal()) {
		plan.MinHoldDays = costCap.Div(plan.EstFeePerDayUSD)
	}
	return plan
}

func printSolanaTierCCandidateLine(rank int, c solanaTierCCandidate) {
	score := c.Score.Total
	if score == 0 {
		score = c.Score.ComputeTotal()
	}
	flagCodes := make([]string, len(c.Pack.Flags))
	for j, f := range c.Pack.Flags {
		flagCodes[j] = f.Code
	}
	rangePct := fmt.Sprintf("%s..%s", c.LPPlan.RangeLowerPct.StringFixed(2), c.LPPlan.RangeUpperPct.StringFixed(2))
	rangePrice := "-"
	if c.LPPlan.RangeLowerPrice.GreaterThan(domain.ZeroDecimal()) && c.LPPlan.RangeUpperPrice.GreaterThan(domain.ZeroDecimal()) {
		rangePrice = c.LPPlan.RangeLowerPrice.StringFixed(6) + ".." + c.LPPlan.RangeUpperPrice.StringFixed(6)
	}
	minHoldDays := "-"
	if c.LPPlan.MinHoldDays.GreaterThan(domain.ZeroDecimal()) {
		minHoldDays = c.LPPlan.MinHoldDays.StringFixed(2)
	}
	fmt.Printf("%d|%s|%d|%s|%s|%s|%d|%.2f|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%d|%d|%t|%t|%s|%s|%s|%s|%s|%s\n",
		rank,
		c.Pack.Verdict,
		c.Pack.RiskScore,
		strings.Join(flagCodes, ";"),
		c.Pool.ID,
		c.Pool.Protocol,
		c.Pool.FeeBPS,
		score,
		c.EstimatedFeeAPR.Mul(domain.MustDecimal("100")).StringFixed(2),
		c.VolumeToTVL.StringFixed(2),
		c.Pool.TVLUSD.StringFixed(2),
		c.Pool.Vol24h.StringFixed(2),
		rangePct,
		rangePrice,
		c.LPPlan.EstFeePerDayUSD.StringFixed(6),
		c.LPPlan.CostCapUSD.StringFixed(2),
		minHoldDays,
		c.LPPlan.ExitTrigger,
		c.MarketQuality.BuyCount24h,
		c.MarketQuality.SellCount24h,
		c.QuoteCheck.ForwardOK,
		c.QuoteCheck.ReverseOK,
		c.QuoteCheck.Reason,
		c.QuoteCheck.ForwardImpactPct,
		c.QuoteCheck.ReverseImpactPct,
		c.Pool.Token0.String(),
		c.Pool.Token1.String(),
		"https://www.geckoterminal.com/solana/pools/"+c.Pool.ID,
	)
}

func writeSolanaTierCJSONOutput(path string, candidates []solanaTierCCandidate, includeRejects bool) error {
	out := make([]jsonCandidate, 0, len(candidates))
	for _, c := range candidates {
		if !includeRejects && c.Pack.Verdict == tierc.VerdictReject {
			continue
		}
		flagCodes := make([]string, len(c.Pack.Flags))
		for j, f := range c.Pack.Flags {
			flagCodes[j] = f.Code
		}
		item := jsonCandidate{
			PoolID:          c.Pool.ID,
			Verdict:         string(c.Pack.Verdict),
			RiskScore:       c.Pack.RiskScore,
			Flags:           flagCodes,
			EstimatedFeeAPR: c.EstimatedFeeAPR.String(),
			VolumeToTVL:     c.VolumeToTVL.String(),
			Protocol:        c.Pool.Protocol,
			FeeBPS:          c.Pool.FeeBPS,
			TVLUSD:          c.Pool.TVLUSD.String(),
			Vol24hUSD:       c.Pool.Vol24h.String(),
			Token0:          c.Pool.Token0.String(),
			Token1:          c.Pool.Token1.String(),
		}
		item.LPPlan.BudgetUSD = c.LPPlan.BudgetUSD.String()
		item.LPPlan.RangeLowerPct = c.LPPlan.RangeLowerPct.String()
		item.LPPlan.RangeUpperPct = c.LPPlan.RangeUpperPct.String()
		item.LPPlan.RangeLowerPrice = c.LPPlan.RangeLowerPrice.String()
		item.LPPlan.RangeUpperPrice = c.LPPlan.RangeUpperPrice.String()
		item.LPPlan.EstFeePerDayUSD = c.LPPlan.EstFeePerDayUSD.String()
		item.LPPlan.CostCapUSD = c.LPPlan.CostCapUSD.String()
		item.LPPlan.MinHoldDays = c.LPPlan.MinHoldDays.String()
		item.LPPlan.ExitTrigger = c.LPPlan.ExitTrigger
		item.Quote.ForwardOK = c.QuoteCheck.ForwardOK
		item.Quote.ReverseOK = c.QuoteCheck.ReverseOK
		item.Quote.Reason = c.QuoteCheck.Reason
		item.Quote.ForwardImpactPct = c.QuoteCheck.ForwardImpactPct
		item.Quote.ReverseImpactPct = c.QuoteCheck.ReverseImpactPct
		item.Quote.Error = c.QuoteCheck.Error
		item.MarketQuality.BuyCount24h = c.MarketQuality.BuyCount24h
		item.MarketQuality.SellCount24h = c.MarketQuality.SellCount24h
		out = append(out, item)
	}
	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}
