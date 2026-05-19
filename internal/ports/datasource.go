// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// Datasource interfaces (this file):
//
//   - Datasource: live pool discovery and metadata from external sources
//   - HistoricalDatasource: historical price and swap data for backtesting
//
// See spec §8.1 (Phase 0: 历史回测) and §2.3 (端口接口集).
package ports

import (
	"context"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
)

// PoolDiscovery represents a discovered pool from external sources.
type PoolDiscovery struct {
	// ID is the on-chain pool address.
	ID string
	// Chain is the blockchain network.
	Chain domain.ChainID
	// Protocol is the DEX protocol name (e.g., "uniswap_v3", "whirlpool").
	Protocol string
	// Token0 is the first token address in the pair.
	Token0 domain.Address
	// Token1 is the second token address in the pair.
	Token1 domain.Address
	// FeeBPS is the pool fee in basis points.
	FeeBPS uint
	// TVLUSD is the total value locked in USD.
	TVLUSD domain.Decimal
	// Vol24h is the 24-hour trading volume in USD.
	Vol24h domain.Decimal
	// UpdatedAt is the timestamp of the last update from the data source.
	UpdatedAt time.Time
}

// HistoricalPrice represents a price data point for a pool.
type HistoricalPrice struct {
	// PoolID is the pool identifier.
	PoolID string
	// Chain is the blockchain network.
	Chain domain.ChainID
	// Timestamp is the time of the price data point.
	Timestamp time.Time
	// BlockNumber is the block number at this price point.
	BlockNumber uint64
	// Price0 is the price of token0 in terms of token1 (or USD).
	Price0 domain.Decimal
	// Price1 is the price of token1 in terms of token0 (or USD).
	Price1 domain.Decimal
	// Liquidity is the pool liquidity at this time.
	Liquidity domain.Decimal
	// Volume24h is the 24-hour volume at this time.
	Volume24h domain.Decimal
}

// Swap represents a historical swap event for backtesting.
type Swap struct {
	// ID is the unique identifier for this swap (source-specific).
	ID string
	// PoolID is the pool where the swap occurred.
	PoolID string
	// Chain is the blockchain network.
	Chain domain.ChainID
	// Timestamp is the time of the swap.
	Timestamp time.Time
	// BlockNumber is the block number of the swap.
	BlockNumber uint64
	// Amount0 is the amount of token0 swapped.
	Amount0 domain.Decimal
	// Amount1 is the amount of token1 swapped.
	Amount1 domain.Decimal
	// Trader is the address of the trader (may be zero address for privacy).
	Trader domain.Address
	// Tick is the tick at which the swap occurred (V3 pools).
	Tick int
	// SqrtPriceX96 is the square root price at the time of swap (V3 pools).
	SqrtPriceX96 domain.Decimal
}

// Datasource defines the interface for discovering pools and fetching
// metadata from external data sources.
//
// Datasource implementations are used by the Scanner module to discover
// candidate pools for further analysis. Data sources include DexScreener,
// GeckoTerminal, Birdeye, and DeFiLlama (see spec §2.2 adapter layout).
//
// Thread safety: implementations must be safe for concurrent use.
type Datasource interface {
	// DiscoverPools returns a list of pools matching the given criteria.
	// It supports filtering by chain, protocol, minimum TVL, and other criteria.
	//
	// Parameters:
	//   - ctx: execution context for cancellation
	//   - chain: filter by chain (pass empty for all chains)
	//   - protocol: filter by protocol (pass empty for all protocols)
	//   - minTVLUSD: minimum TVL in USD (pass zero for no minimum)
	//   - limit: maximum number of results (pass zero for default)
	//
	// Returns a list of discovered pools sorted by TVL descending.
	// Returns an error if the query fails.
	DiscoverPools(ctx context.Context, chain domain.ChainID, protocol string, minTVLUSD domain.Decimal, limit int) ([]PoolDiscovery, error)

	// GetPoolMetadata returns current metadata for a specific pool.
	//
	// Parameters:
	//   - ctx: execution context for cancellation
	//   - chain: the blockchain network
	//   - poolID: the on-chain pool address
	//
	// Returns pool metadata including TVL, volume, and fee APR.
	// Returns an error if the pool is not found or the query fails.
	GetPoolMetadata(ctx context.Context, chain domain.ChainID, poolID string) (*PoolDiscovery, error)

	// HealthCheck verifies the data source is operational.
	// Returns nil if healthy, error otherwise.
	HealthCheck(ctx context.Context) error
}

// HistoricalDatasource defines the interface for accessing historical
// price and swap data for backtesting purposes.
//
// HistoricalDatasource implementations are used by the backtest engine
// (cmd/lpbot-backtest) to replay historical market conditions. Data
// sources include DexScreener, GeckoTerminal, and protocol subgraphs.
//
// Historical data is used to validate PnL calculations and IL formulas
// (spec §8.1 Phase 0 objective).
//
// Thread safety: implementations must be safe for concurrent use.
type HistoricalDatasource interface {
	// GetPriceHistory returns historical price data for a pool.
	//
	// Parameters:
	//   - ctx: execution context for cancellation
	//   - chain: the blockchain network
	//   - poolID: the on-chain pool address
	//   - from: start time (inclusive)
	//   - to: end time (inclusive)
	//   - resolution: data resolution (e.g., 1h, 5m, 1d)
	//
	// Returns a list of price data points sorted by timestamp ascending.
	// Returns an error if the query fails.
	GetPriceHistory(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, resolution time.Duration) ([]HistoricalPrice, error)

	// GetSwaps returns historical swap events for a pool.
	//
	// Parameters:
	//   - ctx: execution context for cancellation
	//   - chain: the blockchain network
	//   - poolID: the on-chain pool address
	//   - from: start time (inclusive)
	//   - to: end time (inclusive)
	//   - limit: maximum number of results (pass zero for default)
	//
	// Returns a list of swap events sorted by timestamp ascending.
	// Returns an error if the query fails.
	GetSwaps(ctx context.Context, chain domain.ChainID, poolID string, from, to time.Time, limit int) ([]Swap, error)

	// GetPoolStateAt returns the pool state at a specific block.
	//
	// Parameters:
	//   - ctx: execution context for cancellation
	//   - chain: the blockchain network
	//   - poolID: the on-chain pool address
	//   - blockNumber: the block number
	//
	// Returns the pool state including price, liquidity, and tick.
	// Returns an error if the pool state cannot be retrieved.
	GetPoolStateAt(ctx context.Context, chain domain.ChainID, poolID string, blockNumber uint64) (*PoolDiscovery, error)

	// HealthCheck verifies the data source is operational.
	// Returns nil if healthy, error otherwise.
	HealthCheck(ctx context.Context) error
}