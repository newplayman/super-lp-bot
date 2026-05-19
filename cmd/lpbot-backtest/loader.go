// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"context"
	"database/sql"
	"fmt"
	"math/big"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// CachedLoader implements DataLoader with SQLite caching for historical data.
// It loads data from DexScreener adapter (swaps) and GeckoTerminal adapter (pool states).
type CachedLoader struct {
	db *sql.DB
}

// NewCachedLoader creates a new CachedLoader with the given SQLite database.
func NewCachedLoader(db *sql.DB) *CachedLoader {
	return &CachedLoader{db: db}
}

// LoadSwaps loads historical swaps from cache or external source.
// In Phase 0, this uses fixture data if cache is empty.
func (l *CachedLoader) LoadSwaps(ctx context.Context, pool domain.Pool, from, to time.Time) ([]ports.Swap, error) {
	// Check cache first
	if l.db != nil {
		swaps, err := l.loadSwapsFromCache(pool.ID, from, to)
		if err == nil && len(swaps) > 0 {
			return swaps, nil
		}
	}

	// In Phase 0, generate fixture data if no cache
	swaps := generateFixtureSwaps(pool, from, to)

	// Cache the data
	if l.db != nil {
		if err := l.cacheSwaps(swaps); err != nil {
			fmt.Printf("Warning: failed to cache swaps: %v\n", err)
		}
	}

	return swaps, nil
}

// LoadPoolStates loads historical pool states from cache or external source.
// In Phase 0, this uses fixture data if cache is empty.
func (l *CachedLoader) LoadPoolStates(ctx context.Context, pool domain.Pool, from, to time.Time, step time.Duration) ([]domain.PoolState, error) {
	// Check cache first
	if l.db != nil {
		states, err := l.loadPoolStatesFromCache(pool.ID, from, to)
		if err == nil && len(states) > 0 {
			return states, nil
		}
	}

	// Generate fixture pool states at the given step interval
	states := generateFixturePoolStates(pool, from, to, step)

	// Cache the data
	if l.db != nil {
		if err := l.cachePoolStates(states); err != nil {
			fmt.Printf("Warning: failed to cache pool states: %v\n", err)
		}
	}

	return states, nil
}

// LoadCollectedFees loads the total fees collected from the subgraph.
// In Phase 0, this returns zero (no ground truth available).
func (l *CachedLoader) LoadCollectedFees(ctx context.Context, pool domain.Pool, from, to time.Time) (domain.Decimal, error) {
	// Check cache first
	if l.db != nil {
		fees, err := l.loadFeesFromCache(pool.ID, from, to)
		if err == nil {
			return fees, nil
		}
	}

	// In Phase 0, return zero - no ground truth available yet
	return domain.NewDecimalFromInt(0), nil
}

// Cache operations

func (l *CachedLoader) loadSwapsFromCache(poolID string, from, to time.Time) ([]ports.Swap, error) {
	query := `
		SELECT id, pool_id, chain, timestamp, block_number, amount0, amount1, trader, tick, sqrt_price_x96
		FROM cache_swaps
		WHERE pool_id = ? AND timestamp >= ? AND timestamp <= ?
		ORDER BY timestamp ASC
	`

	fromUnix := from.Unix()
	toUnix := to.Unix()

	rows, err := l.db.Query(query, poolID, fromUnix, toUnix)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var swaps []ports.Swap
	for rows.Next() {
		var s ports.Swap
		var timestamp int64
		var amount0Str, amount1Str, sqrtPriceStr, traderStr string

		err := rows.Scan(&s.ID, &s.PoolID, &s.Chain, &timestamp, &s.BlockNumber,
			&amount0Str, &amount1Str, &traderStr, &s.Tick, &sqrtPriceStr)
		if err != nil {
			return nil, err
		}

		s.Timestamp = time.Unix(timestamp, 0)
		s.Amount0 = domain.MustDecimal(amount0Str)
		s.Amount1 = domain.MustDecimal(amount1Str)
		s.SqrtPriceX96 = domain.MustDecimal(sqrtPriceStr)
		s.Trader, _ = domain.ParseAddress(traderStr)

		swaps = append(swaps, s)
	}

	return swaps, rows.Err()
}

func (l *CachedLoader) cacheSwaps(swaps []ports.Swap) error {
	tx, err := l.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`
		INSERT OR REPLACE INTO cache_swaps
		(id, pool_id, chain, timestamp, block_number, amount0, amount1, trader, tick, sqrt_price_x96)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, s := range swaps {
		trader := ""
		if len(s.Trader.Bytes()) > 0 {
			trader = s.Trader.String()
		}

		_, err := stmt.Exec(
			s.ID,
			s.PoolID,
			s.Chain,
			s.Timestamp.Unix(),
			s.BlockNumber,
			s.Amount0.String(),
			s.Amount1.String(),
			trader,
			s.Tick,
			s.SqrtPriceX96.String(),
		)
		if err != nil {
			return err
		}
	}

	return tx.Commit()
}

func (l *CachedLoader) loadPoolStatesFromCache(poolID string, from, to time.Time) ([]domain.PoolState, error) {
	query := `
		SELECT pool_id, block_number, block_hash, block_time, tick, liquidity, reserve0, reserve1, sqrt_price_x96, fee_growth_0, fee_growth_1
		FROM cache_pool_states
		WHERE pool_id = ? AND block_time >= ? AND block_time <= ?
		ORDER BY block_time ASC
	`

	fromUnix := from.Unix()
	toUnix := to.Unix()

	rows, err := l.db.Query(query, poolID, fromUnix, toUnix)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var states []domain.PoolState
	for rows.Next() {
		var s domain.PoolState
		var timestamp int64
		var tick int64
		var liquidity, reserve0, reserve1, sqrtPrice, feeGrowth0, feeGrowth1 string

		err := rows.Scan(&s.BlockRef.Hash, &s.BlockRef.Number, &s.BlockRef.Hash, &timestamp,
			&tick, &liquidity, &reserve0, &reserve1, &sqrtPrice, &feeGrowth0, &feeGrowth1)
		if err != nil {
			return nil, err
		}

		s.BlockRef.TimeUnix = timestamp
		s.Tick = tick

		if liquidity != "" {
			d := domain.MustDecimal(liquidity)
			s.Liquidity = decimalToBigInt(d)
		}

		if sqrtPrice != "" {
			d := domain.MustDecimal(sqrtPrice)
			s.SqrtPriceX96 = decimalToBigInt(d)
		}

		if reserve0 != "" {
			s.Reserve0 = domain.MustDecimal(reserve0)
		}

		if reserve1 != "" {
			s.Reserve1 = domain.MustDecimal(reserve1)
		}

		states = append(states, s)
	}

	return states, rows.Err()
}

func (l *CachedLoader) cachePoolStates(states []domain.PoolState) error {
	tx, err := l.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`
		INSERT OR REPLACE INTO cache_pool_states
		(pool_id, block_number, block_hash, block_time, tick, liquidity, reserve0, reserve1, sqrt_price_x96, fee_growth_0, fee_growth_1)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for i, s := range states {
		poolID := s.BlockRef.Hash
		if poolID == "" {
			poolID = fmt.Sprintf("state_%d", i)
		}

		var liquidity, sqrtPrice, feeGrowth0, feeGrowth1 string
		if s.Liquidity != nil {
			liquidity = bigIntToString(s.Liquidity)
		}
		if s.SqrtPriceX96 != nil {
			sqrtPrice = bigIntToString(s.SqrtPriceX96)
		}
		if s.FeeGrowthGlobal0X128 != nil {
			feeGrowth0 = bigIntToString(s.FeeGrowthGlobal0X128)
		}
		if s.FeeGrowthGlobal1X128 != nil {
			feeGrowth1 = bigIntToString(s.FeeGrowthGlobal1X128)
		}

		_, err := stmt.Exec(
			poolID,
			s.BlockRef.Number,
			s.BlockRef.Hash,
			s.BlockRef.TimeUnix,
			s.Tick,
			liquidity,
			s.Reserve0.String(),
			s.Reserve1.String(),
			sqrtPrice,
			feeGrowth0,
			feeGrowth1,
		)
		if err != nil {
			return err
		}
	}

	return tx.Commit()
}

func (l *CachedLoader) loadFeesFromCache(poolID string, from, to time.Time) (domain.Decimal, error) {
	query := `
		SELECT SUM(CAST(fee AS REAL)) as total_fees
		FROM cache_swaps
		WHERE pool_id = ? AND timestamp >= ? AND timestamp <= ?
	`

	var totalFees float64
	err := l.db.QueryRow(query, poolID, from.Unix(), to.Unix()).Scan(&totalFees)
	if err != nil {
		return domain.NewDecimalFromInt(0), err
	}

	// Convert float to decimal (assuming 6 decimal precision for fees)
	// Multiply by 1e6 to convert to integer representation
	return domain.NewDecimalFromInt(int64(totalFees * 1e6)), nil
}

// generateFixtureSwaps generates synthetic swap data for Phase 0 testing.
func generateFixtureSwaps(pool domain.Pool, from, to time.Time) []ports.Swap {
	var swaps []ports.Swap

	interval := 5 * time.Minute
	current := from
	blockNum := uint64(100000000)

	for current.Before(to) {
		numSwaps := 1 + int(current.Unix()%3)

		for i := 0; i < numSwaps; i++ {
			swap := ports.Swap{
				ID:          fmt.Sprintf("swap_%d_%d", blockNum, i),
				PoolID:      pool.ID,
				Chain:       pool.Chain,
				Timestamp:   current,
				BlockNumber: blockNum,
				Amount0:     domain.NewDecimalFromInt(1),
				Amount1:     domain.NewDecimalFromInt(3000000000),
				Tick:        int(current.Unix() % 10000),
				SqrtPriceX96: domain.NewDecimalFromInt(1 << 32),
				Trader:      domain.MustParseAddress("0x0000000000000000000000000000000000000000"),
			}

			swaps = append(swaps, swap)
		}

		current = current.Add(interval)
		blockNum++
	}

	return swaps
}

// generateFixturePoolStates generates synthetic pool state data.
func generateFixturePoolStates(pool domain.Pool, from, to time.Time, step time.Duration) []domain.PoolState {
	var states []domain.PoolState

	current := from
	blockNum := uint64(100000000)

	for current.Before(to) {
		state := domain.PoolState{
			BlockRef: domain.BlockRef{
				Chain:    pool.Chain,
				Number:   blockNum,
				Hash:     fmt.Sprintf("0x%x", blockNum),
				TimeUnix: current.Unix(),
			},
			Tick:        int64(current.Unix() % 10000),
			Liquidity:   big.NewInt(1000000),
			SqrtPriceX96: big.NewInt(1 << 32),
		}

		states = append(states, state)

		current = current.Add(step)
		blockNum++
	}

	return states
}

// Helper functions

func decimalToBigInt(d domain.Decimal) *big.Int {
	val := d.IntPart()
	return big.NewInt(val)
}

func bigIntToString(i *big.Int) string {
	if i == nil {
		return ""
	}
	return i.String()
}