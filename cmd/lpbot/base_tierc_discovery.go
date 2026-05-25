package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/tierc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

type baseTierCCandidate struct {
	Pool            domain.Pool
	Score           domain.Score
	EstimatedFeeAPR domain.Decimal
	VolumeToTVL     domain.Decimal
	MarketQuality   tierc.MarketQuality
	Pack            tierc.Pack
}

func runBaseTierCDiscovery(ctx context.Context, cfg *config.Config, minTVLUSD, maxTVLUSD, minVol24hUSD, minVolumeToTVL, minEstimatedFeeAPR domain.Decimal, limit int, jsonOut string, includeRejects bool) error {
	if limit <= 0 {
		limit = 10
	}
	if minTVLUSD.IsZero() {
		minTVLUSD = domain.MustDecimal("25000")
	}
	if maxTVLUSD.IsZero() {
		maxTVLUSD = domain.MustDecimal("2500000")
	}
	if minVol24hUSD.IsZero() {
		minVol24hUSD = domain.MustDecimal("50000")
	}
	if minVolumeToTVL.IsZero() {
		minVolumeToTVL = domain.MustDecimal("0.50")
	}
	if minEstimatedFeeAPR.IsZero() {
		minEstimatedFeeAPR = domain.MustDecimal("0.25")
	}

	ds := geckoterminal.NewAdapter()
	qualityCollector := newBaseTierCMarketQualityCollector()
	s := scanner.New(scanner.Config{
		Datasource: ds,
		Chain:      domain.ChainBase,
		MinTVLUSD:  minTVLUSD,
	})

	scoredPools, err := s.ScanOnce(ctx)
	if err != nil {
		scoredPools, err = loadBaseTierCScoredPoolsFromStore(ctx, cfg)
		if err != nil {
			return fmt.Errorf("base tier C discovery scan failed: %w", err)
		}
		fmt.Printf("base_tierc_discovery fallback=store_snapshot reason=%q\n", "live_scan_rate_limited")
	}

	candidates := make([]baseTierCCandidate, 0, len(scoredPools))
	for _, scored := range scoredPools {
		pool := scored.Pool
		if pool.Chain != domain.ChainBase || pool.Tier_ != domain.TierC {
			continue
		}
		if pool.TVLUSD.LessThan(minTVLUSD) || pool.TVLUSD.GreaterThan(maxTVLUSD) {
			continue
		}
		if pool.Vol24h.LessThan(minVol24hUSD) || pool.TVLUSD.IsZero() {
			continue
		}
		volToTVL := pool.Vol24h.Div(pool.TVLUSD)
		if volToTVL.LessThan(minVolumeToTVL) {
			continue
		}
		estimatedFeeAPR := estimatePoolFeeAPR(pool)
		if estimatedFeeAPR.LessThan(minEstimatedFeeAPR) {
			continue
		}
		marketQuality, qualityErr := qualityCollector.Collect(ctx, pool)
		if qualityErr != nil && !isTierCMarketQualityCooldown(qualityErr) {
			fmt.Fprintf(os.Stderr, "warning: tierc market quality partial for %s: %v\n", pool.ID, qualityErr)
		}
		pack := tierc.BuildPack(buildPackInput(pool, scored.Score, estimatedFeeAPR, volToTVL, marketQuality))
		if shouldDowngradeTierCBatchVerdict(marketQuality, qualityErr, pack) {
			pack.Flags = append(pack.Flags, tierc.Flag{
				Code:     "market_quality_incomplete",
				Severity: tierc.SeverityWarn,
				Message:  "Batch discovery is missing key market-quality enrichment, so this pool stays in watch until a single-pool audit confirms it",
			})
			pack.Verdict = tierc.VerdictWatch
			if pack.RiskScore < 20 {
				pack.RiskScore = 20
			}
		}
		candidates = append(candidates, baseTierCCandidate{
			Pool:            pool,
			Score:           scored.Score,
			EstimatedFeeAPR: estimatedFeeAPR,
			VolumeToTVL:     volToTVL,
			MarketQuality:   marketQuality,
			Pack:            pack,
		})
	}

	sort.SliceStable(candidates, func(i, j int) bool {
		vi := tierCDiscoveryVerdictRank(candidates[i].Pack.Verdict)
		vj := tierCDiscoveryVerdictRank(candidates[j].Pack.Verdict)
		if vi != vj {
			return vi < vj
		}
		if !candidates[i].EstimatedFeeAPR.Equal(candidates[j].EstimatedFeeAPR) {
			return candidates[i].EstimatedFeeAPR.GreaterThan(candidates[j].EstimatedFeeAPR)
		}
		if !candidates[i].VolumeToTVL.Equal(candidates[j].VolumeToTVL) {
			return candidates[i].VolumeToTVL.GreaterThan(candidates[j].VolumeToTVL)
		}
		left := candidates[i].Score.Total
		if left == 0 {
			left = candidates[i].Score.ComputeTotal()
		}
		right := candidates[j].Score.Total
		if right == 0 {
			right = candidates[j].Score.ComputeTotal()
		}
		if left != right {
			return left > right
		}
		return candidates[i].Pool.TVLUSD.LessThan(candidates[j].Pool.TVLUSD)
	})

	fmt.Printf("base_tierc_discovery filters min_tvl_usd=%s max_tvl_usd=%s min_vol24h_usd=%s min_vol_tvl=%s min_fee_apr=%s limit=%d scanned=%d matched=%d\n",
		minTVLUSD.StringFixed(0),
		maxTVLUSD.StringFixed(0),
		minVol24hUSD.StringFixed(0),
		minVolumeToTVL.StringFixed(2),
		minEstimatedFeeAPR.Mul(domain.MustDecimal("100")).StringFixed(2)+"%",
		limit,
		len(scoredPools),
		len(candidates),
	)
	fmt.Println("rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|buyers_24h|sellers_24h|buy_count_24h|sell_count_24h|volume_cv_5m|median_abs_price_move_5m|token0|token1|gecko_url")

	rejects := 0
	for i := 0; i < len(candidates); i++ {
		c := candidates[i]
		if c.Pack.Verdict == tierc.VerdictReject {
			rejects++
		}
	}

	displayLimit := limit
	if !includeRejects {
		// Skip rejected candidates in output, but track them
		rejectCount := rejects
		displayLimit = 0
		for i := 0; i < len(candidates) && displayLimit < limit; i++ {
			if candidates[i].Pack.Verdict == tierc.VerdictReject {
				continue
			}
			displayLimit++
		}
		_ = rejectCount // not printed but tracked for summary
	}

	rank := 0
	for i := 0; i < len(candidates) && rank < displayLimit; i++ {
		c := candidates[i]
		if !includeRejects && c.Pack.Verdict == tierc.VerdictReject {
			continue
		}
		rank++
		score := c.Score.Total
		if score == 0 {
			score = c.Score.ComputeTotal()
		}
		flagCodes := make([]string, len(c.Pack.Flags))
		for j, f := range c.Pack.Flags {
			flagCodes[j] = f.Code
		}
		fmt.Printf("%d|%s|%d|%s|%s|%s|%d|%.2f|%s|%s|%s|%s|%d|%d|%d|%d|%s|%s|%s|%s|%s\n",
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
			c.MarketQuality.Buyers24h,
			c.MarketQuality.Sellers24h,
			c.MarketQuality.BuyCount24h,
			c.MarketQuality.SellCount24h,
			c.MarketQuality.VolumeCV5m.StringFixed(4),
			c.MarketQuality.MedianAbsPriceMove5m.StringFixed(6),
			c.Pool.Token0.String(),
			c.Pool.Token1.String(),
			baseGeckoPoolURL(c.Pool.ID),
		)
	}

	if len(candidates) == 0 {
		fmt.Println("base_tierc_discovery no candidates matched current filters")
	}

	// Write JSON output if path is provided
	if jsonOut != "" {
		if err := writeJSONOutput(jsonOut, candidates, includeRejects); err != nil {
			fmt.Fprintf(os.Stderr, "warning: failed to write JSON output: %v\n", err)
		}
	}
	return nil
}

func runBaseTierCAuditPool(ctx context.Context, cfg *config.Config, poolID string, jsonOut string) error {
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return fmt.Errorf("pool id is required")
	}

	pool, err := resolveBaseTierCPool(ctx, cfg, poolID)
	if err != nil {
		return err
	}

	score, err := scanner.New(scanner.Config{}).Score(ctx, pool)
	if err != nil {
		return fmt.Errorf("score pool: %w", err)
	}
	pool.Tier_ = score.AssignTier()
	estimatedFeeAPR := estimatePoolFeeAPR(pool)
	volumeToTVL := domain.ZeroDecimal()
	if !pool.TVLUSD.IsZero() {
		volumeToTVL = pool.Vol24h.Div(pool.TVLUSD)
	}
	qualityCollector := newBaseTierCMarketQualityCollector()
	marketQuality, qualityErr := qualityCollector.Collect(ctx, pool)
	if qualityErr != nil && !isTierCMarketQualityCooldown(qualityErr) {
		fmt.Fprintf(os.Stderr, "warning: tierc market quality partial for %s: %v\n", pool.ID, qualityErr)
	}

	candidate := baseTierCCandidate{
		Pool:            pool,
		Score:           score,
		EstimatedFeeAPR: estimatedFeeAPR,
		VolumeToTVL:     volumeToTVL,
		MarketQuality:   marketQuality,
		Pack:            tierc.BuildPack(buildPackInput(pool, score, estimatedFeeAPR, volumeToTVL, marketQuality)),
	}

	fmt.Printf("base_tierc_audit_pool pool_id=%s\n", pool.ID)
	fmt.Println("rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|buyers_24h|sellers_24h|buy_count_24h|sell_count_24h|volume_cv_5m|median_abs_price_move_5m|token0|token1|gecko_url")
	printBaseTierCCandidateLine(1, candidate)

	if jsonOut != "" {
		if err := writeJSONOutput(jsonOut, []baseTierCCandidate{candidate}, true); err != nil {
			return fmt.Errorf("write json output: %w", err)
		}
	}
	return nil
}

func shouldDowngradeTierCBatchVerdict(marketQuality tierc.MarketQuality, qualityErr error, pack tierc.Pack) bool {
	if qualityErr == nil || pack.Verdict != tierc.VerdictCanaryAllowed {
		return false
	}
	return marketQuality.Buyers24h == 0 &&
		marketQuality.Sellers24h == 0 &&
		marketQuality.BuyCount24h == 0 &&
		marketQuality.SellCount24h == 0 &&
		marketQuality.VolumeCV5m.IsZero() &&
		marketQuality.MedianAbsPriceMove5m.IsZero()
}

func tierCDiscoveryVerdictRank(verdict tierc.Verdict) int {
	switch verdict {
	case tierc.VerdictCanaryAllowed:
		return 0
	case tierc.VerdictWatch:
		return 1
	case tierc.VerdictReject:
		return 2
	default:
		return 3
	}
}

func estimatePoolFeeAPR(pool domain.Pool) domain.Decimal {
	if pool.TVLUSD.IsZero() || pool.Vol24h.IsZero() || pool.FeeBPS == 0 {
		return domain.ZeroDecimal()
	}
	feeRate := domain.NewDecimalFromInt(int64(pool.FeeBPS)).Div(domain.MustDecimal("10000"))
	return pool.Vol24h.Mul(feeRate).Div(pool.TVLUSD).Mul(domain.MustDecimal("365"))
}

func baseGeckoPoolURL(poolID string) string {
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return ""
	}
	return "https://www.geckoterminal.com/base/pools/" + poolID
}

func buildPackInput(pool domain.Pool, score domain.Score, estimatedFeeAPR, volumeToTVL domain.Decimal, marketQuality tierc.MarketQuality) tierc.PackInput {
	return tierc.PackInput{
		Pool:            pool,
		Score:           score,
		EstimatedFeeAPR: estimatedFeeAPR,
		VolumeToTVL:     volumeToTVL,
		MarketQuality:   marketQuality,
	}
}

func printBaseTierCCandidateLine(rank int, c baseTierCCandidate) {
	score := c.Score.Total
	if score == 0 {
		score = c.Score.ComputeTotal()
	}
	flagCodes := make([]string, len(c.Pack.Flags))
	for j, f := range c.Pack.Flags {
		flagCodes[j] = f.Code
	}
	fmt.Printf("%d|%s|%d|%s|%s|%s|%d|%.2f|%s|%s|%s|%s|%d|%d|%d|%d|%s|%s|%s|%s|%s\n",
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
		c.MarketQuality.Buyers24h,
		c.MarketQuality.Sellers24h,
		c.MarketQuality.BuyCount24h,
		c.MarketQuality.SellCount24h,
		c.MarketQuality.VolumeCV5m.StringFixed(4),
		c.MarketQuality.MedianAbsPriceMove5m.StringFixed(6),
		c.Pool.Token0.String(),
		c.Pool.Token1.String(),
		baseGeckoPoolURL(c.Pool.ID),
	)
}

type jsonCandidate struct {
	PoolID          string   `json:"pool_id"`
	Verdict         string   `json:"verdict"`
	RiskScore       int      `json:"risk_score"`
	Flags           []string `json:"flags"`
	EstimatedFeeAPR string   `json:"estimated_fee_apr"`
	VolumeToTVL     string   `json:"volume_to_tvl"`
	Protocol        string   `json:"protocol"`
	FeeBPS          uint     `json:"fee_bps"`
	TVLUSD          string   `json:"tvl_usd"`
	Vol24hUSD       string   `json:"vol_24h_usd"`
	Token0          string   `json:"token0"`
	Token1          string   `json:"token1"`
	LPPlan          struct {
		BudgetUSD       string `json:"budget_usd"`
		RangeLowerPct   string `json:"range_lower_pct"`
		RangeUpperPct   string `json:"range_upper_pct"`
		RangeLowerPrice string `json:"range_lower_price"`
		RangeUpperPrice string `json:"range_upper_price"`
		EstFeePerDayUSD string `json:"est_fee_per_day_usd"`
		CostCapUSD      string `json:"cost_cap_usd"`
		MinHoldDays     string `json:"min_hold_days"`
		ExitTrigger     string `json:"exit_trigger"`
	} `json:"lp_plan"`
	Quote struct {
		ForwardOK        bool   `json:"forward_ok"`
		ReverseOK        bool   `json:"reverse_ok"`
		Reason           string `json:"reason"`
		ForwardImpactPct string `json:"forward_impact_pct"`
		ReverseImpactPct string `json:"reverse_impact_pct"`
		Error            string `json:"error"`
	} `json:"quote"`
	MarketQuality struct {
		Buyers24h            int64  `json:"buyers_24h"`
		Sellers24h           int64  `json:"sellers_24h"`
		BuyCount24h          int64  `json:"buy_count_24h"`
		SellCount24h         int64  `json:"sell_count_24h"`
		VolumeCV5m           string `json:"volume_cv_5m"`
		MedianAbsPriceMove5m string `json:"median_abs_price_move_5m"`
		Top10HolderPct       string `json:"top10_holder_pct"`
	} `json:"market_quality"`
}

func writeJSONOutput(path string, candidates []baseTierCCandidate, includeRejects bool) error {
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
		item.MarketQuality.Buyers24h = c.MarketQuality.Buyers24h
		item.MarketQuality.Sellers24h = c.MarketQuality.Sellers24h
		item.MarketQuality.BuyCount24h = c.MarketQuality.BuyCount24h
		item.MarketQuality.SellCount24h = c.MarketQuality.SellCount24h
		item.MarketQuality.VolumeCV5m = c.MarketQuality.VolumeCV5m.String()
		item.MarketQuality.MedianAbsPriceMove5m = c.MarketQuality.MedianAbsPriceMove5m.String()
		item.MarketQuality.Top10HolderPct = c.MarketQuality.Top10HolderPct.String()
		out = append(out, item)
	}
	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func loadBaseTierCScoredPoolsFromStore(ctx context.Context, cfg *config.Config) ([]scanner.ScoredPool, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config is nil for store fallback")
	}

	store, err := openConfiguredStore(cfg)
	if err != nil {
		return nil, err
	}

	pools, err := store.PoolRepo().ListPools(ctx, ports.PoolFilter{
		Chain: domain.ChainBase,
		Tier:  domain.TierC,
		Limit: 200,
	})
	if err != nil {
		return nil, err
	}

	scorer := scanner.New(scanner.Config{})
	scored := make([]scanner.ScoredPool, 0, len(pools))
	for _, pool := range pools {
		score, scoreErr := scorer.Score(ctx, pool)
		if scoreErr != nil {
			continue
		}
		pool.Tier_ = score.AssignTier()
		scored = append(scored, scanner.ScoredPool{
			Pool:  pool,
			Score: score,
		})
	}
	return scored, nil
}

func resolveBaseTierCPool(ctx context.Context, cfg *config.Config, poolID string) (domain.Pool, error) {
	if cfg != nil {
		if pool, err := loadBasePoolFromStore(ctx, cfg, poolID); err == nil {
			return pool, nil
		}
	}

	ds := geckoterminal.NewAdapter()
	metadata, err := ds.GetPoolMetadata(ctx, domain.ChainBase, poolID)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("load live pool metadata: %w", err)
	}
	if metadata == nil {
		return domain.Pool{}, fmt.Errorf("pool metadata not found for %s", poolID)
	}
	resolvedPoolID := strings.TrimSpace(metadata.ID)
	if resolvedPoolID == "" {
		resolvedPoolID = strings.TrimSpace(poolID)
	}
	return domain.Pool{
		ID:        resolvedPoolID,
		Chain:     metadata.Chain,
		Protocol:  metadata.Protocol,
		Token0:    metadata.Token0,
		Token1:    metadata.Token1,
		FeeBPS:    metadata.FeeBPS,
		TVLUSD:    metadata.TVLUSD,
		Vol24h:    metadata.Vol24h,
		UpdatedAt: metadata.UpdatedAt.Unix(),
	}, nil
}

func loadBasePoolFromStore(ctx context.Context, cfg *config.Config, poolID string) (domain.Pool, error) {
	store, err := openConfiguredStore(cfg)
	if err != nil {
		return domain.Pool{}, err
	}
	pools, err := store.PoolRepo().ListPools(ctx, ports.PoolFilter{
		Chain: domain.ChainBase,
		Limit: 500,
	})
	if err != nil {
		return domain.Pool{}, err
	}
	for _, pool := range pools {
		if strings.EqualFold(strings.TrimSpace(pool.ID), strings.TrimSpace(poolID)) {
			return pool, nil
		}
	}
	return domain.Pool{}, fmt.Errorf("pool %s not found in store", poolID)
}

func openConfiguredStore(cfg *config.Config) (ports.Store, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config is nil for store access")
	}
	backend := strings.ToLower(strings.TrimSpace(cfg.Store.Backend))
	if backend == "" {
		backend = "sqlite"
	}
	switch backend {
	case "sqlite":
		return sqlite.NewStore(cfg.Store.SQLitePath)
	case "postgres", "postgresql", "pg":
		return postgres.NewFromDSN(cfg.Store.PostgresDSN)
	default:
		return nil, fmt.Errorf("unsupported store backend: %s", cfg.Store.Backend)
	}
}
