// Package solana provides a Solana datasource adapter using Jupiter API.
package solana

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

var (
	_ ports.Datasource           = (*Adapter)(nil)
	_ ports.HistoricalDatasource = (*Adapter)(nil)
)

var ErrNotImplemented = errors.New("not implemented: Solana adapter")

type Adapter struct {
	client *Client
}

func NewAdapter() *Adapter {
	return &Adapter{client: NewClient()}
}

func NewAdapterWithClient(client *Client) *Adapter {
	return &Adapter{client: client}
}

func (a *Adapter) DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	return a.client.HealthCheck(ctx)
}

func (a *Adapter) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	return nil, ErrNotImplemented
}

func (a *Adapter) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	if limit <= 0 {
		limit = 100
	}
	trades, err := a.client.GetRecentTrades(ctx, poolID, limit)
	if err != nil {
		return nil, fmt.Errorf("fetch trades: %w", err)
	}

	swaps := make([]ports.Swap, 0, len(trades))
	for _, trade := range trades {
		tradeTime := time.Unix(trade.BlockTime, 0)
		if tradeTime.Before(from) || tradeTime.After(to) {
			continue
		}

		swap := ports.Swap{
			ID:         trade.ID,
			PoolID:     poolID,
			Chain:      domain.ChainSolana,
			Timestamp:  tradeTime,
			BlockNumber: uint64(trade.BlockTime),
			Amount0:    domain.Decimal(decimal.NewFromInt(trade.SolAmount)),
			Amount1:    domain.Decimal(decimal.NewFromInt(trade.TokenAmount)),
			Trader:     domain.Address{},
			Tick:       0,
			SqrtPriceX96: domain.Decimal{},
		}
		swaps = append(swaps, swap)
	}

	return swaps, nil
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}