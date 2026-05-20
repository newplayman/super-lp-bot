package risk

import (
	"context"
	"math"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// Candidate is the interface for trade candidates being evaluated by the gate.
type Candidate interface {
	GetNotionalUSD() domain.Decimal
}

// dailyDrawdown returns the current daily drawdown as a negative decimal (e.g., -0.05 for 5%).
func (g *RiskGate) dailyDrawdown() decimal.Decimal {
	if g.peakUSD.IsZero() {
		return decimal.Zero
	}
	return g.currentUSD.Sub(g.peakUSD).Div(g.peakUSD)
}

// weeklyDrawdown returns the current weekly drawdown as a negative decimal.
func (g *RiskGate) weeklyDrawdown() decimal.Decimal {
	if g.peakWeeklyUSD.IsZero() {
		return decimal.Zero
	}
	return g.currentWeeklyUSD.Sub(g.peakWeeklyUSD).Div(g.peakWeeklyUSD)
}

// Allow returns whether the candidate trade is allowed to proceed.
// Fail-closed: any internal error returns false, not panic.
func (g *RiskGate) Allow(c Candidate) (bool, RiskReason) {
	if g == nil {
		return false, ReasonNilGate
	}

	// Check repo state if available (fail-closed on error)
	if g.repo != nil {
		state, err := g.repo.GetKillState(context.Background())
		if err != nil {
			return false, ReasonRepoError
		}
		if state.Level != ports.KillLevelOK {
			return false, g.blockReason
		}
	} else if g.state.Level != ports.KillLevelOK {
		// Fallback to local state if no repo
		return false, g.blockReason
	}

	// 1. Daily drawdown check (>= threshold triggers kill)
	dailyDD := g.dailyDrawdown()
	if dailyDD.LessThan(decimal.Zero) && dailyDD.Abs().GreaterThanOrEqual(g.config.DailyDDKillPct) {
		return false, ReasonDailyDDKill
	}

	// 2. Weekly drawdown check (>= threshold triggers freeze)
	weeklyDD := g.weeklyDrawdown()
	if weeklyDD.LessThan(decimal.Zero) && weeklyDD.Abs().GreaterThanOrEqual(g.config.WeeklyDDFreezePct) {
		return false, ReasonWeeklyDDFreeze
	}

	// 3. PnL nil/NaN check - fail-closed on missing or invalid PnL
	if g.lastPnL == nil {
		return false, ReasonPnLNaN
	}
	if math.IsNaN(g.lastPnL.InexactFloat64()) {
		return false, ReasonPnLNaN
	}

	// 4. Single trade limit check
	notional := c.GetNotionalUSD()
	if notional.GreaterThan(g.config.MaxSingleTradeUSD) {
		return false, ReasonOverSingleLimit
	}

	return true, ReasonOK
}
