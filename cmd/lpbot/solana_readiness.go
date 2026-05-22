package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
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
	"github.com/shopspring/decimal"
)

const solanaWrappedSOLAddress = "So11111111111111111111111111111111111111112"
const solanaUSDCAddress = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
const solanaKnownSOLUSDCPool = "DJNtGuBGEQiUCWE8F981M2C3ZghZt2XLD8f2sQdZ6rsZ"
const defaultJupiterQuoteURL = "https://api.jup.ag/swap/v1/quote"

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

func runSolanaQuoteReadiness(ctx context.Context, inputMint string, outputMint string, amountRaw string, slippageBPS int) error {
	inputMint = strings.TrimSpace(inputMint)
	outputMint = strings.TrimSpace(outputMint)
	if inputMint == "" {
		inputMint = solanaUSDCAddress
	}
	if outputMint == "" {
		outputMint = solanaWrappedSOLAddress
	}
	amount, err := strconv.ParseUint(strings.TrimSpace(amountRaw), 10, 64)
	if err != nil || amount == 0 {
		return fmt.Errorf("invalid quote amount raw %q", amountRaw)
	}
	if slippageBPS <= 0 || slippageBPS > 500 {
		return fmt.Errorf("slippage bps must be between 1 and 500")
	}

	endpoint := strings.TrimSpace(os.Getenv("JUPITER_QUOTE_URL"))
	if endpoint == "" {
		endpoint = defaultJupiterQuoteURL
	}
	parsed, err := url.Parse(endpoint)
	if err != nil {
		return fmt.Errorf("parse jupiter quote url: %w", err)
	}
	q := parsed.Query()
	q.Set("inputMint", inputMint)
	q.Set("outputMint", outputMint)
	q.Set("amount", strconv.FormatUint(amount, 10))
	q.Set("slippageBps", strconv.Itoa(slippageBPS))
	q.Set("restrictIntermediateTokens", "true")
	q.Set("instructionVersion", "V2")
	parsed.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	if err != nil {
		return err
	}
	req.Header.Set("accept", "application/json")
	if apiKey := strings.TrimSpace(os.Getenv("JUPITER_API_KEY")); apiKey != "" {
		req.Header.Set("x-api-key", apiKey)
	}

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("jupiter quote request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("jupiter quote status=%d body=%q", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var quote struct {
		InputMint            string `json:"inputMint"`
		InAmount             string `json:"inAmount"`
		OutputMint           string `json:"outputMint"`
		OutAmount            string `json:"outAmount"`
		OtherAmountThreshold string `json:"otherAmountThreshold"`
		SwapMode             string `json:"swapMode"`
		SlippageBPS          int    `json:"slippageBps"`
		PriceImpactPct       string `json:"priceImpactPct"`
		ContextSlot          uint64 `json:"contextSlot"`
		TimeTaken            any    `json:"timeTaken"`
		RoutePlan            []struct {
			Percent  int `json:"percent"`
			SwapInfo struct {
				AmmKey     string `json:"ammKey"`
				Label      string `json:"label"`
				InputMint  string `json:"inputMint"`
				OutputMint string `json:"outputMint"`
				InAmount   string `json:"inAmount"`
				OutAmount  string `json:"outAmount"`
			} `json:"swapInfo"`
		} `json:"routePlan"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&quote); err != nil {
		return fmt.Errorf("decode jupiter quote: %w", err)
	}
	if len(quote.RoutePlan) == 0 {
		return fmt.Errorf("jupiter quote returned no route")
	}

	routeLabels := make([]string, 0, len(quote.RoutePlan))
	for _, route := range quote.RoutePlan {
		label := strings.TrimSpace(route.SwapInfo.Label)
		if label == "" {
			label = shortAddress(route.SwapInfo.AmmKey)
		}
		routeLabels = append(routeLabels, fmt.Sprintf("%s:%d%%", label, route.Percent))
	}
	fmt.Printf("solana_quote_readiness source=jupiter input=%s output=%s in_amount=%s out_amount=%s threshold=%s slippage_bps=%d price_impact_pct=%s routes=%d context_slot=%d\n",
		shortAddress(quote.InputMint),
		shortAddress(quote.OutputMint),
		quote.InAmount,
		quote.OutAmount,
		quote.OtherAmountThreshold,
		quote.SlippageBPS,
		quote.PriceImpactPct,
		len(quote.RoutePlan),
		quote.ContextSlot,
	)
	fmt.Printf("solana_quote_route labels=%s\n", strings.Join(routeLabels, ","))
	fmt.Println("solana_quote_execution=not_built not_signed not_broadcast")
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
				cached, cachedErr := loadCachedSolanaDiscoveryPools(ctx, cfg, limit)
				if cachedErr != nil || len(cached) == 0 {
					pools = []ports.PoolDiscovery{staticKnownSolanaSOLUSDCPool()}
					fmt.Printf("solana_discovery_source=static_known_pool reason=%q cached_error=%v\n", knownErr.Error(), cachedErr)
				} else {
					pools = cached
					fmt.Println("solana_discovery_source=postgres_cache")
				}
			} else if knownPool == nil {
				cached, cachedErr := loadCachedSolanaDiscoveryPools(ctx, cfg, limit)
				if cachedErr != nil || len(cached) == 0 {
					pools = []ports.PoolDiscovery{staticKnownSolanaSOLUSDCPool()}
					fmt.Printf("solana_discovery_source=static_known_pool reason=%q cached_error=%v\n", "known pool not found", cachedErr)
				} else {
					pools = cached
					fmt.Println("solana_discovery_source=postgres_cache")
				}
			} else {
				pools = []ports.PoolDiscovery{*knownPool}
				fmt.Println("solana_discovery_source=dexscreener_known_pool")
			}
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
		if err := persistSolanaDiscoveryPools(ctx, cfg, pools, minTVLUSD, minVol24hUSD); err != nil {
			return err
		}
	}
	return nil
}

func loadCachedSolanaDiscoveryPools(ctx context.Context, cfg *config.Config, limit int) ([]ports.PoolDiscovery, error) {
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		return nil, fmt.Errorf("postgres dsn is empty")
	}
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return nil, fmt.Errorf("open postgres for cached solana pools: %w", err)
	}
	defer store.Close()
	if err := ensureSolanaPoolRiskTable(ctx, store.DB()); err != nil {
		return nil, err
	}
	if limit <= 0 {
		limit = 10
	}
	rows, err := store.DB().QueryContext(ctx, `
		SELECT p.pool_id, p.protocol, p.token0, p.token1, p.fee_bps,
		       COALESCE(r.tvl_usd, '0'), COALESCE(r.vol24h_usd, '0'), p.updated_at
		FROM pools p
		LEFT JOIN solana_pool_risk r ON r.pool_id = p.pool_id AND r.chain = p.chain
		WHERE p.chain = 2
		ORDER BY COALESCE(r.eligible, false) DESC, p.updated_at DESC
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("query cached solana pools: %w", err)
	}
	defer rows.Close()

	var pools []ports.PoolDiscovery
	for rows.Next() {
		var poolID, protocol, token0Raw, token1Raw, tvlRaw, volRaw string
		var feeBPS int
		var updatedAt int64
		if err := rows.Scan(&poolID, &protocol, &token0Raw, &token1Raw, &feeBPS, &tvlRaw, &volRaw, &updatedAt); err != nil {
			return nil, fmt.Errorf("scan cached solana pool: %w", err)
		}
		token0, err := domain.ParseAddress(token0Raw)
		if err != nil {
			return nil, fmt.Errorf("parse cached solana token0 %s: %w", poolID, err)
		}
		token1, err := domain.ParseAddress(token1Raw)
		if err != nil {
			return nil, fmt.Errorf("parse cached solana token1 %s: %w", poolID, err)
		}
		pools = append(pools, ports.PoolDiscovery{
			ID:        poolID,
			Chain:     domain.ChainSolana,
			Protocol:  protocol,
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    uint(feeBPS),
			TVLUSD:    parseDecimalOrZero(tvlRaw),
			Vol24h:    parseDecimalOrZero(volRaw),
			UpdatedAt: time.Unix(updatedAt, 0),
		})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(pools) == 0 {
		return nil, fmt.Errorf("no cached solana pools")
	}
	return pools, nil
}

func staticKnownSolanaSOLUSDCPool() ports.PoolDiscovery {
	return ports.PoolDiscovery{
		ID:        solanaKnownSOLUSDCPool,
		Chain:     domain.ChainSolana,
		Protocol:  "pancakeswap-v3-solana",
		Token0:    domain.MustParseAddress(solanaWrappedSOLAddress),
		Token1:    domain.MustParseAddress(solanaUSDCAddress),
		FeeBPS:    0,
		TVLUSD:    domain.MustDecimal("2300000"),
		Vol24h:    domain.MustDecimal("20000000"),
		UpdatedAt: time.Now(),
	}
}

func parseDecimalOrZero(value string) domain.Decimal {
	parsed, err := decimal.NewFromString(strings.TrimSpace(value))
	if err != nil {
		return domain.NewDecimalFromInt(0)
	}
	return parsed
}

func persistSolanaDiscoveryPools(ctx context.Context, cfg *config.Config, pools []ports.PoolDiscovery, minTVLUSD domain.Decimal, minVol24hUSD domain.Decimal) error {
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return fmt.Errorf("open postgres for solana discovery persistence: %w", err)
	}
	defer store.Close()
	if err := ensureSolanaPoolRiskTable(ctx, store.DB()); err != nil {
		return err
	}

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
		ok, reason := solanaPoolRiskEligible(discovered, minTVLUSD, minVol24hUSD)
		if err := upsertSolanaPoolRisk(ctx, store.DB(), discovered, ok, reason); err != nil {
			return err
		}
		persisted++
		if ok {
			eligible++
		}
	}
	fmt.Printf("solana_discovery_persisted pools=%d eligible=%d\n", persisted, eligible)
	return nil
}

func ensureSolanaPoolRiskTable(ctx context.Context, db *sql.DB) error {
	if db == nil {
		return nil
	}
	_, err := db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS solana_pool_risk (
			pool_id TEXT PRIMARY KEY,
			chain INTEGER NOT NULL,
			protocol TEXT NOT NULL DEFAULT '',
			eligible BOOLEAN NOT NULL DEFAULT false,
			reason TEXT NOT NULL DEFAULT '',
			tvl_usd TEXT NOT NULL DEFAULT '0',
			vol24h_usd TEXT NOT NULL DEFAULT '0',
			updated_at BIGINT NOT NULL DEFAULT 0
		)
	`)
	if err != nil {
		return fmt.Errorf("ensure solana pool risk table: %w", err)
	}
	return nil
}

func upsertSolanaPoolRisk(ctx context.Context, db *sql.DB, pool ports.PoolDiscovery, eligible bool, reason string) error {
	_, err := db.ExecContext(ctx, `
		INSERT INTO solana_pool_risk (pool_id, chain, protocol, eligible, reason, tvl_usd, vol24h_usd, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (pool_id) DO UPDATE SET
			chain = EXCLUDED.chain,
			protocol = EXCLUDED.protocol,
			eligible = EXCLUDED.eligible,
			reason = EXCLUDED.reason,
			tvl_usd = EXCLUDED.tvl_usd,
			vol24h_usd = EXCLUDED.vol24h_usd,
			updated_at = EXCLUDED.updated_at
	`, pool.ID, solanaReadinessChainIDToInt(pool.Chain), pool.Protocol, eligible, reason, pool.TVLUSD.String(), pool.Vol24h.String(), time.Now().Unix())
	if err != nil {
		return fmt.Errorf("upsert solana pool risk %s: %w", pool.ID, err)
	}
	return nil
}

func solanaReadinessChainIDToInt(chain domain.ChainID) int {
	switch chain {
	case domain.ChainBase:
		return 1
	case domain.ChainSolana:
		return 2
	default:
		return 0
	}
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
