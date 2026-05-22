package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	solrpc "github.com/lpbot/lpbot/internal/adapters/simulator/sol_rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/core/scanner"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

const solanaWrappedSOLAddress = "So11111111111111111111111111111111111111112"
const solanaUSDCAddress = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
const solanaKnownSOLUSDCPool = "DJNtGuBGEQiUCWE8F981M2C3ZghZt2XLD8f2sQdZ6rsZ"

var solanaReadinessProtocolAllowlist = map[string]bool{
	"orca-whirlpool":        true,
	"raydium-clmm":          true,
	"pancakeswap-v3-solana": true,
}

func runSolanaReadiness(ctx context.Context, cfg *config.Config) error {
	endpoint := solanaReadinessEndpoint(cfg)
	if endpoint == "" {
		return fmt.Errorf("solana rpc endpoint is empty")
	}
	fmt.Printf("solana_readiness endpoint=%s\n", redactRPCURL(endpoint))

	health, err := solanaJSONRPC(ctx, endpoint, "getHealth", []any{})
	if err != nil {
		return fmt.Errorf("getHealth: %w", err)
	}
	fmt.Printf("solana_health=%s\n", compactJSON(health))

	slot, err := solanaJSONRPC(ctx, endpoint, "getSlot", []any{map[string]any{"commitment": "processed"}})
	if err != nil {
		return fmt.Errorf("getSlot: %w", err)
	}
	fmt.Printf("solana_slot=%s\n", compactJSON(slot))

	blockhash, err := solanaJSONRPC(ctx, endpoint, "getLatestBlockhash", []any{map[string]any{"commitment": "processed"}})
	if err != nil {
		return fmt.Errorf("getLatestBlockhash: %w", err)
	}
	fmt.Printf("solana_latest_blockhash=%s\n", compactJSON(blockhash))

	fees, err := solanaJSONRPC(ctx, endpoint, "getRecentPrioritizationFees", []any{})
	if err != nil {
		fmt.Printf("solana_priority_fees=unavailable error=%q\n", err.Error())
	} else {
		fmt.Printf("solana_priority_fees=%s\n", compactJSON(fees))
	}

	feePayer := strings.TrimSpace(os.Getenv("SOLANA_FEE_PAYER_ADDRESS"))
	if feePayer == "" {
		fmt.Println("solana_simulate=skipped reason=missing_fee_payer env=SOLANA_FEE_PAYER_ADDRESS")
		return nil
	}

	from, err := domain.ParseAddress(feePayer)
	if err != nil {
		return fmt.Errorf("invalid SOLANA_FEE_PAYER_ADDRESS: %w", err)
	}
	if from.Chain() != domain.ChainSolana {
		return fmt.Errorf("SOLANA_FEE_PAYER_ADDRESS is not a solana address")
	}
	to := domain.MustParseAddress("So11111111111111111111111111111111111111112")
	fmt.Printf("solana_fee_payer=%s\n", shortAddress(from.String()))
	sim := solrpc.New(solrpc.Config{RPCEndpoint: endpoint})
	result, err := sim.Simulate(ctx, domain.UnsignedTx{
		ID:    "solana-readiness-simulate",
		Chain: domain.ChainSolana,
		From:  from,
		To:    to,
		Value: domain.NewDecimalFromInt(1),
	}, domain.BlockRef{Chain: domain.ChainSolana})
	if err != nil {
		return fmt.Errorf("simulateTransaction: %w", err)
	}
	fmt.Printf("solana_simulate success=%t gas_used=%d error=%q\n", result.Success, result.GasUsed, result.Error)
	if !result.Success {
		return fmt.Errorf("solana simulate failed: %s", result.Error)
	}
	return nil
}

func runSolanaDiscoveryReadiness(ctx context.Context, cfg *config.Config, minTVLUSD domain.Decimal, minVol24hUSD domain.Decimal, limit int) error {
	if limit <= 0 {
		limit = 10
	}
	if minTVLUSD.IsNegative() {
		return fmt.Errorf("min tvl must be non-negative")
	}
	if minVol24hUSD.IsNegative() {
		return fmt.Errorf("min volume must be non-negative")
	}

	gecko := geckoterminal.NewAdapter()
	var ds ports.Datasource = gecko
	if err := gecko.HealthCheck(ctx); err != nil {
		fmt.Printf("solana_discovery_health=warning source=geckoterminal error=%q\n", err.Error())
	}
	pools, err := ds.DiscoverPools(ctx, domain.ChainSolana, "", minTVLUSD, limit)
	if err != nil {
		fmt.Printf("solana_discovery_primary=failed source=geckoterminal error=%q\n", err.Error())
		fallback := dexscreener.NewAdapter()
		pools, err = fallback.DiscoverPools(ctx, domain.ChainSolana, "", minTVLUSD, limit)
		if err != nil {
			fmt.Printf("solana_discovery_fallback=failed source=dexscreener error=%q\n", err.Error())
			knownPool, knownErr := fallback.GetPoolMetadata(ctx, domain.ChainSolana, solanaKnownSOLUSDCPool)
			if knownErr != nil {
				return fmt.Errorf("discover solana known pool fallback: %w", knownErr)
			}
			if knownPool == nil {
				return fmt.Errorf("discover solana known pool fallback: pool %s not found", solanaKnownSOLUSDCPool)
			}
			pools = []ports.PoolDiscovery{*knownPool}
			fmt.Println("solana_discovery_source=dexscreener_known_pool")
		} else {
			fmt.Println("solana_discovery_source=dexscreener")
		}
		ds = fallback
	} else {
		fmt.Println("solana_discovery_source=geckoterminal")
	}
	fmt.Printf("solana_discovery_readiness pools=%d min_tvl_usd=%s limit=%d\n", len(pools), minTVLUSD.String(), limit)
	if len(pools) == 0 {
		return fmt.Errorf("no solana pools discovered")
	}
	eligible := 0
	for i, pool := range pools {
		ok, reason := solanaPoolRiskEligible(pool, minTVLUSD, minVol24hUSD)
		if ok {
			eligible++
		}
		fmt.Printf("solana_pool rank=%d eligible=%t reason=%s id=%s protocol=%s tvl_usd=%s vol24h_usd=%s token0=%s token1=%s\n",
			i+1,
			ok,
			reason,
			pool.ID,
			pool.Protocol,
			pool.TVLUSD.String(),
			pool.Vol24h.String(),
			shortAddress(pool.Token0.String()),
			shortAddress(pool.Token1.String()),
		)
	}
	fmt.Printf("solana_discovery_filter eligible=%d min_tvl_usd=%s min_vol24h_usd=%s protocols=%s\n",
		eligible, minTVLUSD.String(), minVol24hUSD.String(), strings.Join(solanaProtocolAllowlistNames(), ","))

	if cfg != nil && strings.TrimSpace(cfg.Store.PostgresDSN) != "" {
		if err := persistSolanaDiscoveryPools(ctx, cfg, pools, minVol24hUSD); err != nil {
			return err
		}
	}
	return nil
}

func persistSolanaDiscoveryPools(ctx context.Context, cfg *config.Config, pools []ports.PoolDiscovery, minVol24hUSD domain.Decimal) error {
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return fmt.Errorf("open postgres for solana discovery persistence: %w", err)
	}
	defer store.Close()

	s := scanner.New(scanner.Config{})
	persisted := 0
	eligible := 0
	for _, discovered := range pools {
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
		score, err := s.Score(ctx, pool)
		if err != nil {
			return fmt.Errorf("score solana pool %s: %w", pool.Key(), err)
		}
		pool.Tier_ = s.AssignTier(score)
		if err := store.PoolRepo().UpsertPool(ctx, ports.PoolWithScore{
			Pool:  pool,
			Score: score,
		}); err != nil {
			return fmt.Errorf("upsert solana pool %s: %w", pool.Key(), err)
		}
		persisted++
		if ok, _ := solanaPoolRiskEligible(discovered, discovered.TVLUSD, minVol24hUSD); ok {
			eligible++
		}
	}
	fmt.Printf("solana_discovery_persisted pools=%d eligible=%d\n", persisted, eligible)
	return nil
}

func solanaPoolRiskEligible(pool ports.PoolDiscovery, minTVLUSD domain.Decimal, minVol24hUSD domain.Decimal) (bool, string) {
	if pool.Chain != domain.ChainSolana {
		return false, "wrong_chain"
	}
	if !solanaReadinessProtocolAllowlist[strings.ToLower(pool.Protocol)] {
		return false, "protocol_not_allowed"
	}
	if !isSolanaSOLUSDCPair(pool.Token0, pool.Token1) {
		return false, "not_sol_usdc"
	}
	if pool.TVLUSD.LessThan(minTVLUSD) {
		return false, "tvl_below_min"
	}
	if pool.Vol24h.LessThan(minVol24hUSD) {
		return false, "volume_below_min"
	}
	return true, "eligible"
}

func isSolanaSOLUSDCPair(token0 domain.Address, token1 domain.Address) bool {
	a := token0.String()
	b := token1.String()
	return (a == solanaWrappedSOLAddress && b == solanaUSDCAddress) ||
		(a == solanaUSDCAddress && b == solanaWrappedSOLAddress)
}

func solanaProtocolAllowlistNames() []string {
	names := make([]string, 0, len(solanaReadinessProtocolAllowlist))
	for name := range solanaReadinessProtocolAllowlist {
		names = append(names, name)
	}
	return names
}

func solanaReadinessEndpoint(cfg *config.Config) string {
	if cfg != nil {
		if endpoint := strings.TrimSpace(cfg.Chains.Solana.RPCPrimary); endpoint != "" {
			return endpoint
		}
		for _, endpoint := range cfg.Chains.Solana.RPCFallback {
			if strings.TrimSpace(endpoint) != "" {
				return strings.TrimSpace(endpoint)
			}
		}
	}
	return solrpc.DefaultRPCEndpoint
}

func solanaJSONRPC(ctx context.Context, endpoint string, method string, params []any) (json.RawMessage, error) {
	body, err := json.Marshal(map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  method,
		"params":  params,
	})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("content-type", "application/json")
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var decoded struct {
		Result json.RawMessage `json:"result"`
		Error  *struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		return nil, err
	}
	if decoded.Error != nil {
		return nil, fmt.Errorf("rpc error code=%d message=%s", decoded.Error.Code, decoded.Error.Message)
	}
	if len(decoded.Result) == 0 {
		return nil, fmt.Errorf("empty result")
	}
	return decoded.Result, nil
}

func compactJSON(raw json.RawMessage) string {
	var out bytes.Buffer
	if err := json.Compact(&out, raw); err != nil {
		return string(raw)
	}
	text := out.String()
	if len(text) > 360 {
		return text[:360] + "..."
	}
	return text
}

func redactRPCURL(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" {
		return "<redacted>"
	}
	parsed.User = nil
	if parsed.RawQuery != "" {
		parsed.RawQuery = "redacted=1"
	}
	parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
	if len(parts) > 0 && len(parts[0]) > 8 {
		parsed.Path = "/<redacted>/"
	}
	return parsed.String()
}

func shortAddress(address string) string {
	if len(address) <= 12 {
		return address
	}
	return address[:6] + "..." + address[len(address)-4:]
}
