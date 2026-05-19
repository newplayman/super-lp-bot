// Package geckoterminal provides a GeckoTerminal datasource adapter.
package geckoterminal

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

var (
	_ ports.Datasource           = (*Adapter)(nil)
	_ ports.HistoricalDatasource = (*Adapter)(nil)
)

type Adapter struct {
	client  *http.Client
	baseURL string
}

func NewAdapter() *Adapter {
	return &Adapter{
		client:  &http.Client{Timeout: 30 * time.Second},
		baseURL: "https://api.geckoterminal.com/api/v2",
	}
}

func NewAdapterWithClient(client *http.Client) *Adapter {
	return &Adapter{
		client:  client,
		baseURL: "https://api.geckoterminal.com/api/v2",
	}
}

func (a *Adapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	client := NewClient()
	network := mapChainToNetwork(chain)
	pools, err := client.GetPoolsByNetwork(ctx, network, limit)
	if err != nil {
		return nil, fmt.Errorf("get pools: %w", err)
	}

	result := make([]ports.PoolDiscovery, 0, len(pools))
	for _, pool := range pools {
		liquidity, err := decimal.NewFromString(pool.Attributes.LiquidityUSD)
		if err != nil {
			continue
		}
		if liquidity.LessThan(minTVLUSD) {
			continue
		}

		token0, _ := domain.ParseAddress(pool.Attributes.Token0.Address)
		token1, _ := domain.ParseAddress(pool.Attributes.Token1.Address)
		baseVolume, _ := decimal.NewFromString(pool.Attributes.BaseVolume)
		quoteVolume, _ := decimal.NewFromString(pool.Attributes.QuoteVolume)

		poolID := pool.Attributes.Address
		if poolID == "" {
			poolID = pool.ID
		}

		result = append(result, ports.PoolDiscovery{
			ID:        poolID,
			Chain:     chain,
			Protocol:  "geckoterminal",
			Token0:    token0,
			Token1:    token1,
			TVLUSD:    liquidity,
			Vol24h:    baseVolume.Add(quoteVolume),
			UpdatedAt: time.Now(),
		})
	}

	return result, nil
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	client := NewClient()
	network := mapChainToNetwork(chain)
	pool, err := client.GetPoolInfo(ctx, network, poolID)
	if err != nil {
		return nil, fmt.Errorf("get pool: %w", err)
	}
	if pool == nil {
		return nil, nil
	}

	token0, _ := domain.ParseAddress(pool.Attributes.Token0.Address)
	token1, _ := domain.ParseAddress(pool.Attributes.Token1.Address)
	liquidity, _ := decimal.NewFromString(pool.Attributes.LiquidityUSD)
	baseVolume, _ := decimal.NewFromString(pool.Attributes.BaseVolume)
	quoteVolume, _ := decimal.NewFromString(pool.Attributes.QuoteVolume)

	resolvedPoolID := pool.Attributes.Address
	if resolvedPoolID == "" {
		resolvedPoolID = pool.ID
	}

	return &ports.PoolDiscovery{
		ID:        resolvedPoolID,
		Chain:     chain,
		Protocol:  "geckoterminal",
		Token0:    token0,
		Token1:    token1,
		TVLUSD:    liquidity,
		Vol24h:    baseVolume.Add(quoteVolume),
		UpdatedAt: time.Now(),
	}, nil
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	client := NewClient()
	return client.HealthCheck(ctx)
}

func (a *Adapter) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	client := NewClient()
	network := mapChainToNetwork(chain)
	fromUnix := from.Unix()
	toUnix := to.Unix()
	limit := 1000

	timeframe := mapStepToTimeframe(resolution)
	ohlcvData, err := client.GetOHLCV(ctx, network, poolID, timeframe, fromUnix, toUnix, limit)
	if err != nil {
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