package main

import (
	"context"
	"errors"
	"fmt"
	"math"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/holderconcentration/basescan"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/core/tierc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

type tierCMarketQualityCollector interface {
	Collect(ctx context.Context, pool domain.Pool) (tierc.MarketQuality, error)
}

var errTierCMarketQualityCooldown = errors.New("tierc market quality collector cooldown active")

type baseTierCMarketQualityCollector struct {
	client         *geckoterminal.Client
	holderProvider tierc.HolderConcentrationProvider
	traderProvider tierc.TraderConcentrationProvider

	cacheTTL         time.Duration
	rateLimitBackoff time.Duration
	minPrimaryGap    time.Duration

	mu            sync.Mutex
	cache         map[string]tierCMarketQualityCacheEntry
	cooldownUntil time.Time
	nextPrimaryAt time.Time
}

type tierCMarketQualityCacheEntry struct {
	quality   tierc.MarketQuality
	expiresAt time.Time
	fetchedAt time.Time
}

func newBaseTierCMarketQualityCollector() tierCMarketQualityCollector {
	holderProviders := []tierc.HolderConcentrationProvider{}
	snapshotPath := strings.TrimSpace(os.Getenv("LPBOT_TIERC_HOLDER_SNAPSHOT_PATH"))
	if snapshotPath == "" {
		snapshotPath = tierc.DefaultHolderSnapshotPath
	}
	if snapshotProvider, err := tierc.NewHolderSnapshotProviderFromFile(snapshotPath); err == nil {
		holderProviders = append(holderProviders, snapshotProvider)
	}
	if provider, ok := basescan.NewProviderFromEnv(); ok {
		holderProviders = append(holderProviders, provider)
	}
	holderProvider := tierc.HolderConcentrationProvider(tierc.NoopHolderConcentrationProvider{})
	if len(holderProviders) > 0 {
		holderProvider = tierc.ChainedHolderConcentrationProvider{Providers: holderProviders}
	}
	return &baseTierCMarketQualityCollector{
		client:         geckoterminal.NewClient(),
		holderProvider: holderProvider,
		traderProvider: tierc.NoopTraderConcentrationProvider{},
		cacheTTL:       tierCHolderAwareCacheTTL(),
		rateLimitBackoff: 4 * time.Minute,
		minPrimaryGap:  1200 * time.Millisecond,
		cache:          make(map[string]tierCMarketQualityCacheEntry),
	}
}

func (c *baseTierCMarketQualityCollector) Collect(ctx context.Context, pool domain.Pool) (tierc.MarketQuality, error) {
	if cached, ok := c.cached(pool.ID, false); ok {
		return cached, nil
	}
	if c.inCooldown() {
		if cached, ok := c.cached(pool.ID, true); ok {
			return cached, nil
		}
		return tierc.MarketQuality{}, errTierCMarketQualityCooldown
	}

	network, err := tierCChainToGeckoNetwork(pool.Chain)
	if err != nil {
		return tierc.MarketQuality{}, err
	}

	var (
		quality tierc.MarketQuality
		errs    []error
	)

	if err := c.acquireSlot(ctx); err != nil {
		return tierc.MarketQuality{}, err
	}
	poolInfo, infoErr := c.client.GetPoolInfo(ctx, network, pool.ID)
	if infoErr != nil {
		if isTierCRateLimited(infoErr) {
			c.setCooldown(0)
		}
		errs = append(errs, fmt.Errorf("pool info: %w", infoErr))
	} else if poolInfo != nil {
		quality.BuyCount24h = poolInfo.Attributes.Transactions.H24.Buys
		quality.SellCount24h = poolInfo.Attributes.Transactions.H24.Sells
		quality.Buyers24h = poolInfo.Attributes.Transactions.H24.Buyers
		quality.Sellers24h = poolInfo.Attributes.Transactions.H24.Sellers
	}

	from := time.Now().Add(-24 * time.Hour)
	to := time.Now()
	var candles []geckoterminal.OHLCV
	var candleErr error
	if err := c.acquireSlot(ctx); err != nil {
		candleErr = err
	} else {
		candles, candleErr = c.client.GetOHLCV(ctx, network, pool.ID, "5m", from.Unix(), to.Unix(), 288)
	}
	if candleErr != nil {
		if isTierCRateLimited(candleErr) {
			c.setCooldown(0)
		}
		errs = append(errs, fmt.Errorf("ohlcv: %w", candleErr))
	} else {
		quality.VolumeCV5m = candleVolumeCV(candles)
		quality.MedianAbsPriceMove5m = candleMedianAbsMove(candles)
	}

	top10, holderErr := c.maxTop10HolderPct(ctx, pool)
	if holderErr != nil {
		errs = append(errs, fmt.Errorf("holder concentration: %w", holderErr))
	} else {
		quality.Top10HolderPct = top10
	}

	if c.traderProvider != nil {
		if _, traderErr := c.traderProvider.Concentration(ctx, pool.Chain, pool.ID); traderErr != nil {
			errs = append(errs, fmt.Errorf("trader concentration: %w", traderErr))
		}
	}

	if infoErr == nil || candleErr == nil {
		c.store(pool.ID, quality)
	} else if cached, ok := c.cached(pool.ID, true); ok {
		quality = cached
	}
	if len(errs) == 0 {
		return quality, nil
	}
	if infoErr == nil || candleErr == nil {
		return quality, joinErrors(errs)
	}
	return quality, joinErrors(errs)
}

func (c *baseTierCMarketQualityCollector) maxTop10HolderPct(ctx context.Context, pool domain.Pool) (domain.Decimal, error) {
	if c.holderProvider == nil {
		return domain.ZeroDecimal(), nil
	}
	var maxPct domain.Decimal
	var lastErr error
	for _, token := range []domain.Address{pool.Token0, pool.Token1} {
		if token.IsZero() {
			continue
		}
		pct, err := c.holderProvider.Top10HolderPct(ctx, pool.Chain, token)
		if err != nil {
			lastErr = err
			continue
		}
		if pct.GreaterThan(maxPct) {
			maxPct = pct
		}
	}
	if maxPct.GreaterThan(domain.ZeroDecimal()) {
		return maxPct, nil
	}
	if lastErr != nil {
		return domain.ZeroDecimal(), lastErr
	}
	return maxPct, nil
}

func (c *baseTierCMarketQualityCollector) cached(poolID string, allowStale bool) (tierc.MarketQuality, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.cache[poolID]
	if !ok {
		return tierc.MarketQuality{}, false
	}
	if !allowStale && time.Now().After(entry.expiresAt) {
		return tierc.MarketQuality{}, false
	}
	return entry.quality, true
}

func (c *baseTierCMarketQualityCollector) store(poolID string, quality tierc.MarketQuality) {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now()
	c.cache[poolID] = tierCMarketQualityCacheEntry{
		quality:   quality,
		expiresAt: now.Add(c.cacheTTL),
		fetchedAt: now,
	}
}

func (c *baseTierCMarketQualityCollector) inCooldown() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return time.Now().Before(c.cooldownUntil)
}

func (c *baseTierCMarketQualityCollector) setCooldown(retryAfter time.Duration) {
	if retryAfter <= 0 {
		retryAfter = c.rateLimitBackoff
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cooldownUntil = time.Now().Add(retryAfter)
}

func (c *baseTierCMarketQualityCollector) acquireSlot(ctx context.Context) error {
	if c.minPrimaryGap <= 0 {
		return nil
	}
	waitFor := time.Duration(0)
	now := time.Now()

	c.mu.Lock()
	if c.nextPrimaryAt.After(now) {
		waitFor = c.nextPrimaryAt.Sub(now)
		now = c.nextPrimaryAt
	}
	c.nextPrimaryAt = now.Add(c.minPrimaryGap)
	c.mu.Unlock()

	if waitFor <= 0 {
		return nil
	}
	timer := time.NewTimer(waitFor)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func candleVolumeCV(candles []geckoterminal.OHLCV) domain.Decimal {
	if len(candles) == 0 {
		return domain.ZeroDecimal()
	}
	values := make([]float64, 0, len(candles))
	for _, candle := range candles {
		volume, ok := candleVolume(candle).Float64()
		if !ok {
			continue
		}
		values = append(values, volume)
	}
	return floatSeriesCV(values)
}

func candleMedianAbsMove(candles []geckoterminal.OHLCV) domain.Decimal {
	if len(candles) == 0 {
		return domain.ZeroDecimal()
	}
	moves := make([]float64, 0, len(candles))
	for _, candle := range candles {
		open, err := decimal.NewFromString(candle.Open)
		if err != nil || open.IsZero() {
			continue
		}
		closeValue, err := decimal.NewFromString(candle.Close)
		if err != nil {
			continue
		}
		move, ok := closeValue.Sub(open).Abs().Div(open).Float64()
		if !ok {
			continue
		}
		moves = append(moves, move)
	}
	if len(moves) == 0 {
		return domain.ZeroDecimal()
	}
	return domain.NewDecimalFromFloat(medianFloat(moves))
}

func candleVolume(candle geckoterminal.OHLCV) domain.Decimal {
	volume, err := decimal.NewFromString(candle.Volume)
	if err != nil {
		return domain.ZeroDecimal()
	}
	return volume
}

func tierCChainToGeckoNetwork(chain domain.ChainID) (string, error) {
	switch chain {
	case domain.ChainBase:
		return "base", nil
	case domain.ChainSolana:
		return "solana", nil
	default:
		return "", fmt.Errorf("unsupported GeckoTerminal network for chain %s", chain)
	}
}

func floatSeriesCV(values []float64) domain.Decimal {
	if len(values) == 0 {
		return domain.ZeroDecimal()
	}
	var sum float64
	for _, value := range values {
		sum += value
	}
	mean := sum / float64(len(values))
	if mean == 0 {
		return domain.ZeroDecimal()
	}
	var variance float64
	for _, value := range values {
		diff := value - mean
		variance += diff * diff
	}
	variance /= float64(len(values))
	return domain.NewDecimalFromFloat(math.Sqrt(variance) / mean)
}

func medianFloat(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sort.Float64s(values)
	mid := len(values) / 2
	if len(values)%2 == 1 {
		return values[mid]
	}
	return (values[mid-1] + values[mid]) / 2
}

func joinErrors(errs []error) error {
	if len(errs) == 0 {
		return nil
	}
	message := errs[0].Error()
	for i := 1; i < len(errs); i++ {
		message += "; " + errs[i].Error()
	}
	return fmt.Errorf("%s", message)
}

func isTierCRateLimited(err error) bool {
	var rateLimitErr *geckoterminal.RateLimitError
	return errors.As(err, &rateLimitErr)
}

func isTierCMarketQualityCooldown(err error) bool {
	return errors.Is(err, errTierCMarketQualityCooldown)
}

func tierCHolderAwareCacheTTL() time.Duration {
	if strings.TrimSpace(os.Getenv("BASESCAN_API_KEY")) != "" || strings.TrimSpace(os.Getenv("ETHERSCAN_API_KEY")) != "" {
		return 30 * time.Minute
	}
	return 20 * time.Minute
}
