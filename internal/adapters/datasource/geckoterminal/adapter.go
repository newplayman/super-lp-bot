// Package geckoterminal provides a GeckoTerminal datasource adapter.
package geckoterminal

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/metrics"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

var (
	_ ports.Datasource           = (*Adapter)(nil)
	_ ports.HistoricalDatasource = (*Adapter)(nil)
)

type Adapter struct {
	client           *http.Client
	baseURL          string
	cacheTTL         time.Duration
	rateLimitBackoff time.Duration
	fallback         *dexscreener.Adapter
	mu               sync.Mutex
	poolCache        map[string]poolCacheEntry
	cooldownUntil    time.Time
}

type poolCacheEntry struct {
	pools     []ports.PoolDiscovery
	expiresAt time.Time
	fetchedAt time.Time
}

func NewAdapter() *Adapter {
	return &Adapter{
		client:           &http.Client{Timeout: 30 * time.Second},
		baseURL:          "https://api.geckoterminal.com/api/v2",
		cacheTTL:         90 * time.Second,
		rateLimitBackoff: 2 * time.Minute,
		fallback:         dexscreener.NewAdapter(),
		poolCache:        make(map[string]poolCacheEntry),
	}
}

func NewAdapterWithClient(client *http.Client) *Adapter {
	return &Adapter{
		client:           client,
		baseURL:          "https://api.geckoterminal.com/api/v2",
		cacheTTL:         90 * time.Second,
		rateLimitBackoff: 2 * time.Minute,
		fallback:         dexscreener.NewAdapterWithClient(client),
		poolCache:        make(map[string]poolCacheEntry),
	}
}

func (a *Adapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	cacheKey := fmt.Sprintf("%s:%s:%s:%d", chain, protocol, minTVLUSD.String(), limit)
	if cached, ok := a.cachedPools(cacheKey, false); ok {
		metrics.IncDatasourceCacheHit("geckoterminal", "fresh")
		return cached, nil
	}
	if a.inCooldown() {
		if cached, ok := a.cachedPools(cacheKey, true); ok {
			metrics.IncDatasourceCacheHit("geckoterminal", "stale")
			return cached, nil
		}
		if fallback, err := a.fallback.DiscoverPools(ctx, chain, protocol, minTVLUSD, limit); err == nil && len(fallback) > 0 {
			metrics.IncDatasourceFallback("geckoterminal", "dexscreener", "discover_pools_cooldown")
			a.storePools(cacheKey, fallback)
			return fallback, nil
		}
	}

	result, err := a.discoverPoolsPrimary(ctx, chain, minTVLUSD, limit)
	if err != nil {
		if fallback, fallbackErr := a.fallback.DiscoverPools(ctx, chain, protocol, minTVLUSD, limit); fallbackErr == nil && len(fallback) > 0 {
			metrics.IncDatasourceFallback("geckoterminal", "dexscreener", "discover_pools_error")
			a.storePools(cacheKey, fallback)
			return fallback, nil
		}
		return nil, fmt.Errorf("get pools: %w", err)
	}
	if len(result) == 0 {
		if fallback, fallbackErr := a.fallback.DiscoverPools(ctx, chain, protocol, minTVLUSD, limit); fallbackErr == nil && len(fallback) > 0 {
			metrics.IncDatasourceFallback("geckoterminal", "dexscreener", "discover_pools_empty")
			a.storePools(cacheKey, fallback)
			return fallback, nil
		}
	}

	a.storePools(cacheKey, result)
	return result, nil
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	metadata, _, err := a.GetPoolMetadataWithSource(ctx, chain, poolID)
	return metadata, err
}

func (a *Adapter) GetPoolMetadataWithSource(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, string, error) {
	metadata, err := a.getPoolMetadataPrimary(ctx, chain, poolID)
	if err == nil && metadata != nil {
		return metadata, "geckoterminal", nil
	}

	fallback, fallbackErr := a.fallback.GetPoolMetadata(ctx, chain, poolID)
	if fallbackErr == nil && fallback != nil {
		op := "get_pool_metadata"
		if err == nil {
			op = "get_pool_metadata_empty"
		}
		metrics.IncDatasourceFallback("geckoterminal", "dexscreener", op)
		return fallback, "dexscreener", nil
	}

	if err != nil {
		return nil, "", fmt.Errorf("get pool: %w", err)
	}
	if fallbackErr != nil {
		return nil, "", fmt.Errorf("fallback get pool: %w", fallbackErr)
	}
	return nil, "", nil
}

func (a *Adapter) getPoolMetadataPrimary(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	client := NewClientWithHTTP(a.client, a.baseURL)
	network := mapChainToNetwork(chain)
	pool, err := client.GetPoolInfo(ctx, network, poolID)
	if err != nil {
		var rateLimit *RateLimitError
		if errors.As(err, &rateLimit) {
			metrics.IncDatasourceRateLimit("geckoterminal")
			a.setCooldown(rateLimit.RetryAfter)
		}
		return nil, err
	}
	if pool == nil {
		return nil, nil
	}

	token0, _ := domain.ParseAddress(resolveTokenAddress(pool.Attributes.Token0.Address, pool.Relationships.BaseToken.Data.ID))
	token1, _ := domain.ParseAddress(resolveTokenAddress(pool.Attributes.Token1.Address, pool.Relationships.QuoteToken.Data.ID))
	liquidity, _ := decimal.NewFromString(firstNonEmpty(pool.Attributes.LiquidityUSD, pool.Attributes.ReserveInUSD, "0"))
	volume, _ := decimal.NewFromString(firstNonEmpty(pool.Attributes.VolumeUSD.H24, pool.Attributes.BaseVolume, pool.Attributes.QuoteVolume, "0"))

	resolvedPoolID := pool.Attributes.Address
	if resolvedPoolID == "" {
		resolvedPoolID = stripNetworkPrefix(pool.ID)
	}
	protocol := pool.Relationships.Dex.Data.ID
	if protocol == "" {
		protocol = "geckoterminal"
	}

	return &ports.PoolDiscovery{
		ID:        resolvedPoolID,
		Chain:     chain,
		Protocol:  protocol,
		Token0:    token0,
		Token1:    token1,
		FeeBPS:    parseFeeBPS(pool.Attributes.Name),
		TVLUSD:    liquidity,
		Vol24h:    volume,
		UpdatedAt: time.Now(),
	}, nil
}

func (a *Adapter) discoverPoolsPrimary(ctx context.Context, chain domain.ChainID, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	client := NewClientWithHTTP(a.client, a.baseURL)
	network := mapChainToNetwork(chain)
	pools, err := client.GetPoolsByNetwork(ctx, network, limit)
	if err != nil {
		var rateLimit *RateLimitError
		if errors.As(err, &rateLimit) {
			metrics.IncDatasourceRateLimit("geckoterminal")
			a.setCooldown(rateLimit.RetryAfter)
			if cached, ok := a.cachedPools(fmt.Sprintf("%s:::%d", chain, limit), true); ok {
				metrics.IncDatasourceCacheHit("geckoterminal", "rate_limited_stale")
				return cached, nil
			}
		}
		return nil, err
	}

	result := make([]ports.PoolDiscovery, 0, len(pools))
	for _, pool := range pools {
		liquidity, err := decimal.NewFromString(firstNonEmpty(
			pool.Attributes.LiquidityUSD,
			pool.Attributes.ReserveInUSD,
			pool.Attributes.BaseLiquidityUSD,
			pool.Attributes.QuoteLiquidityUSD,
		))
		if err != nil || liquidity.LessThan(minTVLUSD) {
			continue
		}

		token0, err := domain.ParseAddress(resolveTokenAddress(pool.Attributes.Token0.Address, pool.Relationships.BaseToken.Data.ID))
		if err != nil {
			continue
		}
		token1, err := domain.ParseAddress(resolveTokenAddress(pool.Attributes.Token1.Address, pool.Relationships.QuoteToken.Data.ID))
		if err != nil {
			continue
		}
		volume, _ := decimal.NewFromString(firstNonEmpty(pool.Attributes.VolumeUSD.H24, pool.Attributes.BaseVolume, pool.Attributes.QuoteVolume, "0"))

		poolID := pool.Attributes.Address
		if poolID == "" {
			poolID = stripNetworkPrefix(pool.ID)
		}
		protocol := pool.Relationships.Dex.Data.ID
		if protocol == "" {
			protocol = "geckoterminal"
		}

		result = append(result, ports.PoolDiscovery{
			ID:        poolID,
			Chain:     chain,
			Protocol:  protocol,
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    parseFeeBPS(pool.Attributes.Name),
			TVLUSD:    liquidity,
			Vol24h:    volume,
			UpdatedAt: time.Now(),
		})
	}

	return result, nil
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	client := NewClientWithHTTP(a.client, a.baseURL)
	return client.HealthCheck(ctx)
}

func (a *Adapter) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	result, err := a.getPriceHistoryPrimary(ctx, chain, poolID, from, to, resolution)
	if err == nil && len(result) > 0 {
		return result, nil
	}

	fallback, fallbackErr := a.fallback.GetPriceHistory(ctx, chain, poolID, from, to, resolution)
	if fallbackErr == nil && len(fallback) > 0 {
		op := "price_history_empty"
		if err != nil {
			op = "price_history_error"
		}
		metrics.IncDatasourceFallback("geckoterminal", "dexscreener", op)
		return fallback, nil
	}

	if err != nil {
		return nil, err
	}
	if fallbackErr != nil {
		return nil, fmt.Errorf("fallback get price history: %w", fallbackErr)
	}
	return result, nil
}

func (a *Adapter) getPriceHistoryPrimary(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	client := NewClientWithHTTP(a.client, a.baseURL)
	network := mapChainToNetwork(chain)
	fromUnix := from.Unix()
	toUnix := to.Unix()
	limit := 1000

	timeframe := mapStepToTimeframe(resolution)
	ohlcvData, err := client.GetOHLCV(ctx, network, poolID, timeframe, fromUnix, toUnix, limit)
	if err != nil {
		var rateLimit *RateLimitError
		if errors.As(err, &rateLimit) {
			metrics.IncDatasourceRateLimit("geckoterminal")
			a.setCooldown(rateLimit.RetryAfter)
		}
		return nil, err
	}

	result := make([]ports.HistoricalPrice, 0, len(ohlcvData))
	for _, candle := range ohlcvData {
		open, _ := decimal.NewFromString(candle.Attributes.OHLCVOpen)
		close, _ := decimal.NewFromString(candle.Attributes.OHLCVClose)

		var blockTime int64
		if candle.Attributes.BlockTime != "" {
			blockTime, _ = parseTimestamp(candle.Attributes.BlockTime)
		}

		volume, _ := decimal.NewFromString(candle.Attributes.OHLCVVolume)

		result = append(result, ports.HistoricalPrice{
			PoolID:      poolID,
			Chain:       chain,
			Timestamp:   time.Unix(blockTime, 0),
			BlockNumber: uint64(blockTime),
			Price0:      open,
			Price1:      close,
			Liquidity:   decimal.Zero,
			Volume24h:   volume,
		})
	}

	return result, nil
}

func (a *Adapter) cachedPools(key string, allowStale bool) ([]ports.PoolDiscovery, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()

	entry, ok := a.poolCache[key]
	if !ok || len(entry.pools) == 0 {
		return nil, false
	}
	if !allowStale && time.Now().After(entry.expiresAt) {
		return nil, false
	}
	return clonePoolDiscoveries(entry.pools), true
}

func (a *Adapter) storePools(key string, pools []ports.PoolDiscovery) {
	a.mu.Lock()
	defer a.mu.Unlock()

	now := time.Now()
	a.poolCache[key] = poolCacheEntry{
		pools:     clonePoolDiscoveries(pools),
		expiresAt: now.Add(a.cacheTTL),
		fetchedAt: now,
	}
}

func (a *Adapter) inCooldown() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return time.Now().Before(a.cooldownUntil)
}

func (a *Adapter) setCooldown(retryAfter time.Duration) {
	if retryAfter <= 0 {
		retryAfter = a.rateLimitBackoff
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.cooldownUntil = time.Now().Add(retryAfter)
}

func clonePoolDiscoveries(pools []ports.PoolDiscovery) []ports.PoolDiscovery {
	out := make([]ports.PoolDiscovery, len(pools))
	copy(out, pools)
	return out
}

func (a *Adapter) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	// GeckoTerminal doesn't provide swap-level data via OHLCV
	// Return empty slice - swap data would come from DexScreener
	return []ports.Swap{}, nil
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	// Historical pool state not available via GeckoTerminal
	// Return current state as best effort
	return a.GetPoolMetadata(ctx, chain, poolID)
}

func mapChainToNetwork(chain domain.ChainID) string {
	switch chain {
	case domain.ChainBase:
		return "base"
	case domain.ChainSolana:
		return "sol"
	default:
		return "eth"
	}
}

func mapStepToTimeframe(step time.Duration) string {
	switch {
	case step >= 24*time.Hour:
		return "1d"
	case step >= time.Hour:
		return "1h"
	case step >= time.Minute:
		return "1m"
	default:
		return "1h"
	}
}

func parseTimestamp(ts string) (int64, error) {
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return 0, err
	}
	return t.Unix(), nil
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func resolveTokenAddress(attrAddress string, relationshipID string) string {
	if strings.TrimSpace(attrAddress) != "" {
		return attrAddress
	}
	return stripNetworkPrefix(relationshipID)
}

func stripNetworkPrefix(value string) string {
	if idx := strings.LastIndex(value, "_"); idx >= 0 && idx+1 < len(value) {
		return value[idx+1:]
	}
	return value
}

func parseFeeBPS(name string) uint {
	fields := strings.Fields(name)
	if len(fields) == 0 {
		return 0
	}
	last := strings.TrimSuffix(fields[len(fields)-1], "%")
	if last == fields[len(fields)-1] {
		return 0
	}
	percent, err := strconv.ParseFloat(last, 64)
	if err != nil {
		return 0
	}
	return uint(percent * 100)
}
