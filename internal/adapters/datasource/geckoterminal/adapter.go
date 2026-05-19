// Package geckoterminal provides a GeckoTerminal datasource adapter.
package geckoterminal

import (
	"context"
	"errors"
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

var ErrNotImplemented = errors.New("not implemented: GeckoTerminal Phase 1")

type Adapter struct {
	client  *http.Client
	baseURL string
}

func NewAdapter() *Adapter {
	return &Adapter{
		client: &http.Client{Timeout: 30 * time.Second},
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
	return nil, ErrNotImplemented
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	return ErrNotImplemented
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

		result = append(result, ports.HistoricalPrice{
			PoolID:     poolID,
			Chain:     chain,
			Timestamp: time.Unix(blockTime, 0),
			BlockNumber: uint64(blockTime),
			Price0:    domain.Decimal(open),
			Price1:    domain.Decimal(close),
			Liquidity: domain.Decimal{},
			Volume24h: domain.Decimal{},
		})
	}

	return result, nil
}

func (a *Adapter) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	return nil, ErrNotImplemented
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func mapChainToNetwork(chain domain.ChainID) string {
	switch chain {
	case domain.ChainBase:
		return "base"
	case domain.ChainSolana:
		return "solana"
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