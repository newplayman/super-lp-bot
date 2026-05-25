package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/core/tierc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

type solanaTierCDeepAuditTarget struct {
	Protocol string
	PoolID   string
}

type solanaTierCDeepAuditRound struct {
	Round             int      `json:"round"`
	PoolID            string   `json:"pool_id"`
	Protocol          string   `json:"protocol"`
	Verdict           string   `json:"verdict"`
	RiskScore         int      `json:"risk_score"`
	Flags             []string `json:"flags"`
	QuoteForwardOK    bool     `json:"quote_forward_ok"`
	QuoteReverseOK    bool     `json:"quote_reverse_ok"`
	QuoteReason       string   `json:"quote_reason"`
	EstimatedFeeAPR   string   `json:"estimated_fee_apr"`
	EstFeePerDayUSD   string   `json:"est_fee_per_day_usd"`
	MinHoldDays       string   `json:"min_hold_days"`
	VolumeToTVL       string   `json:"volume_to_tvl"`
	Stable            bool     `json:"stable"`
	StabilityBlockers []string `json:"stability_blockers"`
}

type solanaTierCDeepAuditSummary struct {
	PoolID       string `json:"pool_id"`
	Protocol     string `json:"protocol"`
	StableRounds int    `json:"stable_rounds"`
	TotalRounds  int    `json:"total_rounds"`
	FinalStatus  string `json:"final_status"`
}

type solanaTierCDeepAuditOutput struct {
	GeneratedAt string                        `json:"generated_at"`
	Rounds      []solanaTierCDeepAuditRound   `json:"rounds"`
	Summary     []solanaTierCDeepAuditSummary `json:"summary"`
}

func runSolanaTierCDeepAuditWatchlist(ctx context.Context, cfg *config.Config, watchlist string, rounds int, intervalSeconds int, jsonOut string) error {
	targets, err := parseSolanaTierCDeepAuditWatchlist(watchlist)
	if err != nil {
		return err
	}
	if rounds <= 0 {
		rounds = 3
	}
	if intervalSeconds < 0 {
		intervalSeconds = 0
	}

	var allRounds []solanaTierCDeepAuditRound
	stableCounts := make(map[string]int)
	totalCounts := make(map[string]int)
	for round := 1; round <= rounds; round++ {
		fmt.Printf("solana_tierc_deep_audit round=%d targets=%d\n", round, len(targets))
		for _, target := range targets {
			discovered, err := resolveNativeSolanaPoolForDeepAudit(ctx, target)
			key := target.Protocol + ":" + target.PoolID
			if err != nil {
				item := solanaTierCDeepAuditRound{
					Round:             round,
					PoolID:            target.PoolID,
					Protocol:          target.Protocol,
					Verdict:           "error",
					RiskScore:         100,
					Flags:             []string{"deep_audit_resolve_failed"},
					Stable:            false,
					StabilityBlockers: []string{err.Error()},
				}
				allRounds = append(allRounds, item)
				totalCounts[key]++
				printSolanaTierCDeepAuditRound(item)
				continue
			}
			candidate, err := buildSolanaTierCCandidateFromDiscovery(ctx, cfg, discovered)
			if err != nil {
				item := solanaTierCDeepAuditRound{
					Round:             round,
					PoolID:            target.PoolID,
					Protocol:          target.Protocol,
					Verdict:           "error",
					RiskScore:         100,
					Flags:             []string{"deep_audit_build_failed"},
					Stable:            false,
					StabilityBlockers: []string{err.Error()},
				}
				allRounds = append(allRounds, item)
				totalCounts[key]++
				printSolanaTierCDeepAuditRound(item)
				continue
			}
			item := buildSolanaTierCDeepAuditRound(round, candidate)
			allRounds = append(allRounds, item)
			totalCounts[key]++
			if item.Stable {
				stableCounts[key]++
			}
			printSolanaTierCDeepAuditRound(item)
		}
		if round < rounds && intervalSeconds > 0 {
			timer := time.NewTimer(time.Duration(intervalSeconds) * time.Second)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
		}
	}

	summary := make([]solanaTierCDeepAuditSummary, 0, len(targets))
	for _, target := range targets {
		key := target.Protocol + ":" + target.PoolID
		status := "reject_or_watch"
		if totalCounts[key] == rounds && stableCounts[key] == rounds {
			status = "deep_audit_ready"
		}
		summary = append(summary, solanaTierCDeepAuditSummary{
			PoolID:       target.PoolID,
			Protocol:     target.Protocol,
			StableRounds: stableCounts[key],
			TotalRounds:  totalCounts[key],
			FinalStatus:  status,
		})
		fmt.Printf("solana_tierc_deep_audit_summary pool_id=%s protocol=%s stable_rounds=%d total_rounds=%d final_status=%s\n", target.PoolID, target.Protocol, stableCounts[key], totalCounts[key], status)
	}
	if strings.TrimSpace(jsonOut) != "" {
		out := solanaTierCDeepAuditOutput{
			GeneratedAt: time.Now().UTC().Format(time.RFC3339),
			Rounds:      allRounds,
			Summary:     summary,
		}
		data, err := json.MarshalIndent(out, "", "  ")
		if err != nil {
			return err
		}
		if err := os.WriteFile(jsonOut, data, 0644); err != nil {
			return err
		}
	}
	return nil
}

func parseSolanaTierCDeepAuditWatchlist(raw string) ([]solanaTierCDeepAuditTarget, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("solana tier C deep audit watchlist is empty")
	}
	parts := strings.Split(raw, ",")
	targets := make([]solanaTierCDeepAuditTarget, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		target := solanaTierCDeepAuditTarget{}
		pieces := strings.SplitN(part, ":", 2)
		if len(pieces) == 2 {
			target.Protocol = strings.ToLower(strings.TrimSpace(pieces[0]))
			target.PoolID = strings.TrimSpace(pieces[1])
		} else {
			target.PoolID = part
		}
		if target.PoolID == "" {
			return nil, fmt.Errorf("invalid deep audit target %q", part)
		}
		targets = append(targets, target)
	}
	if len(targets) == 0 {
		return nil, fmt.Errorf("solana tier C deep audit watchlist has no valid targets")
	}
	return targets, nil
}

func resolveNativeSolanaPoolForDeepAudit(ctx context.Context, target solanaTierCDeepAuditTarget) (ports.PoolDiscovery, error) {
	limit := 100
	protocol := strings.ToLower(strings.TrimSpace(target.Protocol))
	pools, _, err := discoverNativeSolanaPools(ctx, protocol, domain.ZeroDecimal(), limit)
	if err != nil {
		return ports.PoolDiscovery{}, err
	}
	for _, pool := range pools {
		if pool.ID == target.PoolID {
			return pool, nil
		}
	}
	return ports.PoolDiscovery{}, fmt.Errorf("pool %s not found in native protocol=%s top %d", target.PoolID, protocol, limit)
}

func buildSolanaTierCCandidateFromDiscovery(ctx context.Context, cfg *config.Config, discovered ports.PoolDiscovery) (solanaTierCCandidate, error) {
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
	score, err := scanner.New(scanner.Config{}).Score(ctx, pool)
	if err != nil {
		return solanaTierCCandidate{}, fmt.Errorf("score solana pool: %w", err)
	}
	pool.Tier_ = score.AssignTier()
	estimatedFeeAPR := estimatePoolFeeAPR(pool)
	volumeToTVL := domain.ZeroDecimal()
	if !pool.TVLUSD.IsZero() {
		volumeToTVL = pool.Vol24h.Div(pool.TVLUSD)
	}
	marketQuality, qualityErr := newSolanaTierCMarketQualityCollector().Collect(ctx, pool)
	if qualityErr != nil {
		fmt.Fprintf(os.Stderr, "warning: solana tierc deep audit market quality partial for %s: %v\n", pool.ID, qualityErr)
	}
	pack := tierc.BuildPack(buildPackInput(pool, score, estimatedFeeAPR, volumeToTVL, marketQuality))
	tokenSafety, tokenSafetyErr := collectSolanaPoolTokenSafety(ctx, cfg, pool)
	quoteCheck := newSolanaTierCQuoteCollector().Collect(ctx, pool)
	applySolanaTierCGuards(pool, marketQuality, qualityErr, tokenSafety, tokenSafetyErr, quoteCheck, &pack)
	applySolanaTierCTokenProfileGuards(pool, discovered.PriceUSD, quoteCheck, estimatedFeeAPR, &pack)
	finalizeSolanaTierCVerdict(&pack)
	lpPlan := buildSolanaTierCLPPlan(discovered.PriceUSD, estimatedFeeAPR)
	return solanaTierCCandidate{
		Pool:              pool,
		Score:             score,
		EstimatedFeeAPR:   estimatedFeeAPR,
		VolumeToTVL:       volumeToTVL,
		ReferencePriceUSD: discovered.PriceUSD,
		MarketQuality:     marketQuality,
		QuoteCheck:        quoteCheck,
		LPPlan:            lpPlan,
		Pack:              pack,
	}, nil
}

func buildSolanaTierCDeepAuditRound(round int, candidate solanaTierCCandidate) solanaTierCDeepAuditRound {
	flags := solanaTierCFlagCodes(candidate.Pack)
	stable, blockers := isSolanaTierCDeepAuditStable(candidate)
	return solanaTierCDeepAuditRound{
		Round:             round,
		PoolID:            candidate.Pool.ID,
		Protocol:          candidate.Pool.Protocol,
		Verdict:           string(candidate.Pack.Verdict),
		RiskScore:         candidate.Pack.RiskScore,
		Flags:             flags,
		QuoteForwardOK:    candidate.QuoteCheck.ForwardOK,
		QuoteReverseOK:    candidate.QuoteCheck.ReverseOK,
		QuoteReason:       candidate.QuoteCheck.Reason,
		EstimatedFeeAPR:   candidate.EstimatedFeeAPR.String(),
		EstFeePerDayUSD:   candidate.LPPlan.EstFeePerDayUSD.String(),
		MinHoldDays:       candidate.LPPlan.MinHoldDays.String(),
		VolumeToTVL:       candidate.VolumeToTVL.String(),
		Stable:            stable,
		StabilityBlockers: blockers,
	}
}

func isSolanaTierCDeepAuditStable(candidate solanaTierCCandidate) (bool, []string) {
	var blockers []string
	if candidate.Pack.RiskScore >= 60 || candidate.Pack.Verdict == tierc.VerdictReject {
		blockers = append(blockers, "risk_or_reject")
	}
	if !candidate.QuoteCheck.ForwardOK || !candidate.QuoteCheck.ReverseOK {
		blockers = append(blockers, "quote_not_roundtrip_ok")
	}
	for _, flag := range candidate.Pack.Flags {
		switch flag.Code {
		case "solana_freeze_authority_present", "solana_mint_authority_present", "solana_pump_fun_token", "solana_high_frequency_count_symmetry":
			blockers = append(blockers, flag.Code)
		}
	}
	if candidate.LPPlan.MinHoldDays.IsZero() || candidate.LPPlan.MinHoldDays.GreaterThan(domain.MustDecimal("7")) {
		blockers = append(blockers, "cost_cover_days_gt_7")
	}
	if candidate.VolumeToTVL.LessThan(domain.MustDecimal("1.00")) {
		blockers = append(blockers, "volume_to_tvl_lt_1")
	}
	return len(blockers) == 0, blockers
}

func solanaTierCFlagCodes(pack tierc.Pack) []string {
	flags := make([]string, len(pack.Flags))
	for i, flag := range pack.Flags {
		flags[i] = flag.Code
	}
	return flags
}

func printSolanaTierCDeepAuditRound(item solanaTierCDeepAuditRound) {
	fmt.Printf("solana_tierc_deep_audit_round round=%d stable=%t pool_id=%s protocol=%s verdict=%s risk_score=%d quote_forward=%t quote_reverse=%t quote_reason=%s min_hold_days=%s flags=%s blockers=%s\n",
		item.Round,
		item.Stable,
		item.PoolID,
		item.Protocol,
		item.Verdict,
		item.RiskScore,
		item.QuoteForwardOK,
		item.QuoteReverseOK,
		item.QuoteReason,
		item.MinHoldDays,
		strings.Join(item.Flags, ";"),
		strings.Join(item.StabilityBlockers, ";"),
	)
}
