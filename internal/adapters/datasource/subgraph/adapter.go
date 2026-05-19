// Package subgraph provides a subgraph datasource adapter for Base Uniswap V3.
package subgraph

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

var ErrNotImplemented = errors.New("not implemented: Subgraph adapter")

type Adapter struct {
	client *Client
}

func NewAdapter() *Adapter {
	return &Adapter{client: NewClient()}
}

func NewAdapterWithURL(url string) *Adapter {
	return &Adapter{client: NewClientWithURL(url)}
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
		limit = 1000
	}
	swapEntities, err := a.client.QuerySwaps(ctx, poolID, from, to, limit)
	if err != nil {
		return nil, fmt.Errorf("query swaps: %w", err)
	}

	swaps := make([]ports.Swap, 0, len(swapEntities))
	for _, entity := range swapEntities {
		swap, err := parseSwapEntity(entity)
		if err != nil {
			continue
		}
		swaps = append(swaps, swap)
	}

	return swaps, nil
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func parseSwapEntity(entity SwapEntity) (ports.Swap, error) {
	amount0, _ := parseBigInt(entity.Amount0, 18)
	amount1, _ := parseBigInt(entity.Amount1, 18)

	timestampUnix, _ := parseTimestamp(entity.Timestamp)
	var blockNumber uint64
	fmt.Sscanf(entity.BlockNumber, "%d", &blockNumber)

	return ports.Swap{
		ID:         entity.ID,
		PoolID:     entity.Pool.ID,
		Chain:      domain.ChainBase,
		Timestamp:  time.Unix(timestampUnix, 0),
		BlockNumber: blockNumber,
		Amount0:    domain.Decimal(amount0),
		Amount1:    domain.Decimal(amount1),
		Trader:     domain.Address{},
		Tick:       0,
		SqrtPriceX96: domain.Decimal{},
	}, nil
}

func parseBigInt(value string, decimals int) (decimal.Decimal, error) {
	if value == "" {
		return decimal.Zero, nil
	}
	val, err := decimal.NewFromString(value)
	if err != nil {
		return decimal.Zero, err
	}
	divisor := decimal.NewFromInt(int64(decimals))
	return val.Div(divisor), nil
}

func parseTimestamp(ts string) (int64, error) {
	var unix int64
	_, err := fmt.Sscanf(ts, "%d", &unix)
	return unix, err
}