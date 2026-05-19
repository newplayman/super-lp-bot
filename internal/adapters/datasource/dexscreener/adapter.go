package dexscreener

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
	client := NewClient()
	pools, err := client.SearchPools(ctx, chain.String(), "", "")
	if err != nil {
		return nil, fmt.Errorf("search pools: %w", err)
	}

	result := make([]ports.PoolDiscovery, 0, len(pools))

	for _, pool := range pools {
		liquidity, err := decimal.NewFromString(pool.Liquidity.USD)
		if err != nil {
			continue
		}
		if liquidity.LessThan(minTVLUSD) {
			continue
		}

		token0, _ := domain.ParseAddress(pool.Token0.Address)
		token1, _ := domain.ParseAddress(pool.Token1.Address)
		volume24h, _ := decimal.NewFromString(pool.Volume.H24)

		parsed := ports.PoolDiscovery{
			ID:        pool.PoolAddress,
			Chain:     chain,
			Protocol:  pool.DEX,
			Token0:    token0,
			Token1:    token1,
			TVLUSD:    liquidity,
			Vol24h:    volume24h,
			UpdatedAt: time.Now(),
		}

		result = append(result, parsed)
		if limit > 0 && len(result) >= limit {
			break
		}
	}

	return result, nil
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	client := NewClient()
	pool, err := client.GetPoolByAddress(ctx, chain.String(), poolID)
	if err != nil {
		return nil, fmt.Errorf("get pool: %w", err)
	}
	if pool == nil {
		return nil, nil
	}

	token0, _ := domain.ParseAddress(pool.Token0.Address)
	token1, _ := domain.ParseAddress(pool.Token1.Address)
	liquidity, _ := decimal.NewFromString(pool.Liquidity.USD)
	volume24h, _ := decimal.NewFromString(pool.Volume.H24)

	return &ports.PoolDiscovery{
		ID:        pool.PoolAddress,
		Chain:     chain,
		Protocol:  pool.DEX,
		Token0:    token0,
		Token1:    token1,
		TVLUSD:    liquidity,
		Vol24h:    volume24h,
		UpdatedAt: time.Now(),
	}, nil
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	client := NewClient()
	return client.HealthCheck(ctx)
}

func (a *Adapter) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	client := NewClient()
	swaps, err := client.GetRecentSwaps(ctx, chain.String(), poolID)
	if err != nil {
		return nil, fmt.Errorf("get swaps: %w", err)
	}

	result := make([]ports.HistoricalPrice, 0, len(swaps))
	for _, swap := range swaps {
		ts := time.Unix(swap.BlockTimestamp, 0)
		if ts.Before(from) || ts.After(to) {
			continue
		}

		priceUSD, _ := decimal.NewFromString(swap.PriceUSD)
		amount0, _ := decimal.NewFromString(swap.TokenAmount0)
		amount1, _ := decimal.NewFromString(swap.TokenAmount1)

		result = append(result, ports.HistoricalPrice{
			PoolID:      poolID,
			Chain:       chain,
			Timestamp:   ts,
			BlockNumber: swap.BlockNumber,
			Price0:      amount0,
			Price1:      amount1,
			Liquidity:   decimal.Zero,
			Volume24h:   decimal.Zero,
		})
		_ = priceUSD
	}

	return result, nil
}

func (a *Adapter) GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]ports.Swap, error) {
	client := NewClient()
	swaps, err := client.GetRecentSwaps(ctx, chain.String(), poolID)
	if err != nil {
		return nil, err
	}

	result := make([]ports.Swap, 0, len(swaps))
	for _, swap := range swaps {
		amount0, err0 := decimal.NewFromString(swap.TokenAmount0)
		amount1, err1 := decimal.NewFromString(swap.TokenAmount1)
		if err0 != nil || err1 != nil {
			continue
		}

		result = append(result, ports.Swap{
			ID:          swap.ID,
			PoolID:      swap.PoolAddress,
			Chain:       chain,
			Timestamp:   time.Unix(swap.BlockTimestamp, 0),
			BlockNumber: swap.BlockNumber,
			Amount0:     amount0,
			Amount1:     amount1,
			Trader:      domain.Address{},
			Tick:        0,
			SqrtPriceX96: decimal.Zero,
		})

		if limit > 0 && len(result) >= limit {
			break
		}
	}

	return result, nil
}

func (a *Adapter) GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*ports.PoolDiscovery, error) {
	return a.GetPoolMetadata(ctx, chain, poolID)
}