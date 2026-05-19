// Package main provides the lpbot-backtest CLI for Phase 0 validation.
package main

import (
	"context"
	"fmt"
	"math/big"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Simulator handles position simulation over historical data.
type Simulator struct {
	rangeMode string
	rangeK    float64
}

// NewSimulator creates a new position simulator.
func NewSimulator(rangeMode string, rangeK float64) *Simulator {
	return &Simulator{
		rangeMode: rangeMode,
		rangeK:    rangeK,
	}
}

// SimulationResult contains the results of a position simulation.
type SimulationResult struct {
	Position       *domain.Position
	SimulatedFees  domain.Decimal
	TotalIL        domain.Decimal
	NetPnL         domain.Decimal
	EntryBlockRef  domain.BlockRef
	ExitBlockRef   domain.BlockRef
	Snapshots      []PositionSnapshot
}

// PositionSnapshot represents a point-in-time state of the position.
type PositionSnapshot struct {
	Timestamp       time.Time
	BlockNumber     uint64
	Tick            int64
	Price           domain.Decimal
	Liquidity       domain.Decimal
	Token0Amt       domain.Decimal
	Token1Amt       domain.Decimal
	UncollectedFees domain.Decimal
	CumulativeFees  domain.Decimal
	IL              domain.Decimal
}

// Simple position state for simulation
type simPositionState struct {
	tickLower, tickUpper int64
	liquidity            *big.Int
	token0, token1       domain.Decimal
}

// CreatePosition creates a new position based on the range mode.
func (s *Simulator) CreatePosition(pool domain.Pool, openTime time.Time) *domain.Position {
	tier, _ := domain.ParseTier("A") // default to tier A

	// Calculate tick range based on mode
	tickLower, tickUpper := s.calculateTickRange(pool, 0) // mid price = 0

	pos := &domain.Position{
		ID:        fmt.Sprintf("sim_%d", openTime.UnixNano()),
		PoolID:    pool.ID,
		Chain:     pool.Chain,
		Status:    domain.StatusOpen,
		Tier:      tier,
		TickLower: tickLower,
		TickUpper: tickUpper,
		OpenedAt:  openTime.Unix(),
		AmountUSD: domain.NewDecimalFromInt(10000000000), // $10k in micro units
	}

	return pos
}

// calculateTickRange calculates tick boundaries based on range mode.
func (s *Simulator) calculateTickRange(pool domain.Pool, midTick int64) (tickLower, tickUpper int64) {
	switch s.rangeMode {
	case "symmetric":
		spread := int64(s.rangeK * 100)
		tickLower = midTick - spread
		tickUpper = midTick + spread
	case "increasing":
		spread := int64(s.rangeK * 50)
		tickLower = midTick - spread
		tickUpper = midTick + spread*2
	case "decreasing":
		spread := int64(s.rangeK * 50)
		tickLower = midTick - spread*2
		tickUpper = midTick + spread
	default:
		spread := int64(150)
		tickLower = midTick - spread
		tickUpper = midTick + spread
	}

	return tickLower, tickUpper
}

// Simulate runs the position simulation over historical data.
func (s *Simulator) Simulate(
	ctx context.Context,
	pos *domain.Position,
	swaps []ports.Swap,
	poolStates []domain.PoolState,
	_ ports.LedgerRepo,
) (*SimulationResult, error) {
	result := &SimulationResult{
		Position:  pos,
		Snapshots: make([]PositionSnapshot, 0, len(poolStates)),
	}

	// Track position state
	v3State := simPositionState{
		tickLower: pos.TickLower,
		tickUpper: pos.TickUpper,
		liquidity: big.NewInt(1000000),
		token0:    domain.ZeroDecimal(),
		token1:    domain.ZeroDecimal(),
	}

	var cumulativeFees domain.Decimal
	var cumulativeIL domain.Decimal

	for i, state := range poolStates {
		snapshot := PositionSnapshot{
			Timestamp:   time.Unix(state.BlockRef.TimeUnix, 0),
			BlockNumber: state.BlockRef.Number,
			Tick:        state.Tick,
			Liquidity:   domain.NewDecimalFromInt(int64(state.BlockRef.Number)),
		}

		// Calculate fees accumulated since last state
		if i > 0 {
			prevState := poolStates[i-1]
			feesAccrued := s.calculateFeesAccrued(pos, swaps, prevState.BlockRef.TimeUnix, state.BlockRef.TimeUnix)
			cumulativeFees = cumulativeFees.Add(feesAccrued)
		}

		// Calculate IL based on current price vs entry price
		ilPct := s.calculateIL(v3State, state)

		// Get token values
		token0Val := v3State.token0.Mul(domain.NewDecimalFromInt(int64(state.BlockRef.Number)))
		token1Val := v3State.token1
		positionValue := token0Val.Add(token1Val)

		ilUSD := positionValue.Mul(ilPct)
		cumulativeIL = cumulativeIL.Add(ilUSD)

		// Update snapshot
		snapshot.UncollectedFees = v3State.token0.Add(v3State.token1)
		snapshot.CumulativeFees = cumulativeFees
		snapshot.IL = cumulativeIL
		snapshot.Price = domain.NewDecimalFromInt(int64(state.BlockRef.Number))

		result.Snapshots = append(result.Snapshots, snapshot)
	}

	// Final state
	if len(poolStates) > 0 {
		result.EntryBlockRef = poolStates[0].BlockRef
		result.ExitBlockRef = poolStates[len(poolStates)-1].BlockRef
	}

	result.SimulatedFees = cumulativeFees
	result.TotalIL = cumulativeIL
	result.NetPnL = cumulativeFees.Add(cumulativeIL)

	return result, nil
}

// calculateFeesAccrued calculates fees accumulated between two timestamps.
func (s *Simulator) calculateFeesAccrued(pos *domain.Position, swaps []ports.Swap, fromUnix, toUnix int64) domain.Decimal {
	var totalFees domain.Decimal

	for _, swap := range swaps {
		swapTime := swap.Timestamp.Unix()
		if swapTime < fromUnix || swapTime > toUnix {
			continue
		}

		// Check if swap is in the position's tick range
		swapTick := int64(swap.Tick)

		if swapTick >= pos.TickLower && swapTick < pos.TickUpper {
			// Swap is in range - calculate LP fees (0.3% fee)
			feeAmount := swap.Amount0.Add(swap.Amount1).Mul(domain.NewDecimalFromInt(3)).Div(domain.NewDecimalFromInt(1000))
			totalFees = totalFees.Add(feeAmount)
		}
	}

	return totalFees
}

// calculateIL calculates the impermanent loss percentage.
func (s *Simulator) calculateIL(v3State simPositionState, state domain.PoolState) domain.Decimal {
	tickCurrent := state.Tick

	var ilPct domain.Decimal

	if tickCurrent >= v3State.tickLower && tickCurrent < v3State.tickUpper {
		// In range: 2% IL
		ilPct = domain.NewDecimalFromInt(-2).Div(domain.NewDecimalFromInt(100))
	} else {
		// Out of range: 5% IL
		ilPct = domain.NewDecimalFromInt(-5).Div(domain.NewDecimalFromInt(100))
	}

	return ilPct
}