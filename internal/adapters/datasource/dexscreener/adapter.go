package dexscreener

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

var ErrNotImplemented = errors.New("not implemented: DexScreener M0.11")

type Adapter struct {
	client  *http.Client
	baseURL string
}

func NewAdapter() *Adapter {
	return &Adapter{
		client:  &http.Client{Timeout: 30 * time.Second},
		baseURL: "https://api.dexscreener.com",
	}
}

func NewAdapterWithClient(client *http.Client) *Adapter {
	return &Adapter{
		client:  client,
		baseURL: "https://api.dexscreener.com",
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
	return nil, ErrNotImplemented
}

func (a *Adapter) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	client := NewClient()
	swaps, err := client.GetRecentSwaps(ctx, chain.String(), poolID)
	if err != nil {
		return nil, err
	}

	result := make([]ports.Swap, 0, len(swaps))
	for _, swap := range swaps {
		parsed, err := parseSwapData(swap, chain)
		if err != nil {
			continue
		}
		result = append(result, parsed)
	}

	return result, nil
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	return nil, ErrNotImplemented
}

func parseSwapData(s SwapData, chain domain.ChainID) (ports.Swap, error) {
	amount0 := parseDecimal(s.TokenAmount0)
	amount1 := parseDecimal(s.TokenAmount1)

	return ports.Swap{
		ID:          s.ID,
		PoolID:      s.PoolAddress,
		Chain:       chain,
		Timestamp:   time.Unix(s.BlockTimestamp, 0),
		BlockNumber: s.BlockNumber,
		Amount0:     domain.Decimal(amount0),
		Amount1:     domain.Decimal(amount1),
		Trader:      domain.Address{},
		Tick:        0,
		SqrtPriceX96: domain.Decimal{},
	}, nil
}

func parseDecimal(s string) decimal.Decimal {
	if s == "" {
		return decimal.Zero
	}
	d, err := decimal.NewFromString(s)
	if err != nil {
		return decimal.Zero
	}
	return d
}
