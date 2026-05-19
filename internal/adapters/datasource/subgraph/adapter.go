// Package subgraph provides a subgraph datasource adapter for Base Uniswap V3.
package subgraph

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
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
	if limit <= 0 {
		limit = 50
	}

	query := `query DiscoverPools($limit: Int!) {
		pools(first: $limit, orderBy: totalValueLockedUSD, orderDirection: desc) {
			id
			token0 { id symbol decimals }
			token1 { id symbol decimals }
			feeTier
			totalValueLockedUSD
			volumeUSD
			txCount
		}
	}`

	variables := map[string]interface{}{
		"limit": limit,
	}

	result, err := a.client.executeQuery(ctx, query, variables)
	if err != nil {
		return nil, fmt.Errorf("query pools: %w", err)
	}

	var poolsResult struct {
		Pools []PoolEntity `json:"pools"`
	}
	if err := json.Unmarshal(result, &poolsResult); err != nil {
		return nil, fmt.Errorf("unmarshal result: %w", err)
	}

	discovered := make([]ports.PoolDiscovery, 0, len(poolsResult.Pools))
	for _, pool := range poolsResult.Pools {
		// Use VolumeUSD as proxy for liquidity (subgraph may not have TVL)
		tvl, _ := decimal.NewFromString(pool.VolumeUSD)
		// Add a multiplier to approximate TVL from volume
		tvl = tvl.Mul(decimal.NewFromInt(100))
		if tvl.LessThan(minTVLUSD) {
			continue
		}

		token0, _ := domain.ParseAddress(pool.Token0.ID)
		token1, _ := domain.ParseAddress(pool.Token1.ID)
		volume, _ := decimal.NewFromString(pool.VolumeUSD)

		discovered = append(discovered, ports.PoolDiscovery{
			ID:        pool.ID,
			Chain:     chain,
			Protocol:  "uniswap_v3",
			Token0:    token0,
			Token1:    token1,
			TVLUSD:    tvl,
			Vol24h:    volume,
			UpdatedAt: time.Now(),
		})
	}

	return discovered, nil
}

func (a *Adapter) GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*ports.PoolDiscovery, error) {
	query := `query GetPool($pool: String!) {
		pools(where: { id: $pool }) {
			id
			token0 { id symbol decimals }
			token1 { id symbol decimals }
			feeTier
			totalValueLockedUSD
			volumeUSD
			txCount
		}
	}`

	variables := map[string]interface{}{
		"pool": strings.ToLower(poolID),
	}

	result, err := a.client.executeQuery(ctx, query, variables)
	if err != nil {
		return nil, fmt.Errorf("query pool: %w", err)
	}

	var poolsResult struct {
		Pools []PoolEntity `json:"pools"`
	}
	if err := json.Unmarshal(result, &poolsResult); err != nil {
		return nil, fmt.Errorf("unmarshal result: %w", err)
	}

	if len(poolsResult.Pools) == 0 {
		return nil, nil
	}

	pool := poolsResult.Pools[0]
	token0, _ := domain.ParseAddress(pool.Token0.ID)
	token1, _ := domain.ParseAddress(pool.Token1.ID)
	volume, _ := decimal.NewFromString(pool.VolumeUSD)
	tvl := volume.Mul(decimal.NewFromInt(100)) // Approximate TVL from volume

	return &ports.PoolDiscovery{
		ID:        pool.ID,
		Chain:     chain,
		Protocol:  "uniswap_v3",
		Token0:    token0,
		Token1:    token1,
		TVLUSD:    tvl,
		Vol24h:    volume,
		UpdatedAt: time.Now(),
	}, nil
}

func (a *Adapter) HealthCheck(ctx context.Context) error {
	return a.client.HealthCheck(ctx)
}

func (a *Adapter) GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]ports.HistoricalPrice, error) {
	swaps, err := a.GetSwaps(ctx, chain, poolID, from, to, 1000)
	if err != nil {
		return nil, err
	}

	result := make([]ports.HistoricalPrice, 0, len(swaps))
	for _, swap := range swaps {
		result = append(result, ports.HistoricalPrice{
			PoolID:      poolID,
			Chain:       chain,
			Timestamp:   swap.Timestamp,
			BlockNumber: swap.BlockNumber,
			Price0:      swap.Amount0,
			Price1:      swap.Amount1,
			Liquidity:   decimal.Zero,
			Volume24h:   decimal.Zero,
		})
	}

	return result, nil
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
	return a.GetPoolMetadata(ctx, chain, poolID)
}

func parseSwapEntity(entity SwapEntity) (ports.Swap, error) {
	amount0, _ := parseBigInt(entity.Amount0, 18)
	amount1, _ := parseBigInt(entity.Amount1, 18)

	timestampUnix, _ := parseTimestamp(entity.Timestamp)
	var blockNum uint64
	fmt.Sscanf(entity.BlockNumber, "%d", &blockNum)

	return ports.Swap{
		ID:          entity.ID,
		PoolID:      entity.Pool.ID,
		Chain:       domain.ChainBase,
		Timestamp:   time.Unix(timestampUnix, 0),
		BlockNumber: blockNum,
		Amount0:     amount0,
		Amount1:     amount1,
		Trader:      domain.Address{},
		Tick:        0,
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