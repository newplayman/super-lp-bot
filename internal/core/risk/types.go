package risk

import (
	"context"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// RiskReason represents the reason a trade was blocked.
type RiskReason string

// Exported RiskReason values for metric labels.
const (
	ReasonOK           RiskReason = "ok"
	ReasonNilGate      RiskReason = "nil_gate"
	ReasonDailyDDKill  RiskReason = "daily_dd_kill"
	ReasonWeeklyDDFreeze RiskReason = "weekly_dd_freeze"
	ReasonPnLNaN       RiskReason = "pnl_nan"
	ReasonOverSingleLimit RiskReason = "over_single_limit"
	ReasonRepoError    RiskReason = "repo_error"
	ReasonInternalError RiskReason = "internal_error"
	ReasonManualKill   RiskReason = "manual_kill"
)

// RiskConfig holds risk thresholds for the RiskGate.
type RiskConfig struct {
	VaRWarnPct          decimal.Decimal
	VaRKillPct          decimal.Decimal
	DailyDDKillPct      decimal.Decimal
	WeeklyDDFreezePct   decimal.Decimal
	TotalExposurePct    decimal.Decimal
	MaxSingleTradeUSD   decimal.Decimal
}

// DefaultRiskConfig returns sensible defaults.
func DefaultRiskConfig() RiskConfig {
	return RiskConfig{
		VaRWarnPct:          decimal.NewFromFloat(0.08),
		VaRKillPct:          decimal.NewFromFloat(0.12),
		DailyDDKillPct:      decimal.NewFromFloat(0.05),
		WeeklyDDFreezePct:   decimal.NewFromFloat(0.10),
		TotalExposurePct:    decimal.NewFromFloat(0.30),
		MaxSingleTradeUSD:   decimal.NewFromInt(50),
	}
}

// RiskReport represents a risk assessment result
type RiskReport struct {
	Score       int
	Description string
}

// Assessor defines the interface for performing risk assessment on pools.
type Assessor interface {
	Assess(ctx context.Context, pool ports.PoolDiscovery) (*RiskReport, error)
}

// riskAssessor is the implementation of Assessor.
type riskAssessor struct {
	config RiskConfig
	repo   ports.RiskRepo
}

// New creates a new Risk Assessor.
func New() Assessor {
	return &riskAssessor{
		config: DefaultRiskConfig(),
		repo:   nil,
	}
}

// NewWithConfig creates a Risk Assessor with custom config.
func NewWithConfig(config RiskConfig) Assessor {
	return &riskAssessor{config: config}
}

// NewWithRepo creates a Risk Assessor with repository.
func NewWithRepo(repo ports.RiskRepo) Assessor {
	return &riskAssessor{
		config: DefaultRiskConfig(),
		repo:   repo,
	}
}

// Assess performs a risk assessment on the given pool.
func (a *riskAssessor) Assess(ctx context.Context, pool ports.PoolDiscovery) (*RiskReport, error) {
	minTVL := decimal.NewFromInt(10000)
	if pool.TVLUSD.LessThan(minTVL) {
		return &RiskReport{Score: 20, Description: "Low TVL"}, nil
	}

	minVol := decimal.NewFromInt(1000)
	if pool.Vol24h.LessThan(minVol) {
		return &RiskReport{Score: 40, Description: "Low volume"}, nil
	}

	return &RiskReport{Score: 80, Description: "Pool passes risk checks"}, nil
}

// RiskGate manages kill switch state transitions.
type RiskGate struct {
	config RiskConfig
	repo   ports.RiskRepo
	state  ports.KillState
	mu     sync.Mutex

	// Drawdown tracking (exposed for Allow() checks)
	peakUSD          decimal.Decimal
	currentUSD       decimal.Decimal
	peakWeeklyUSD    decimal.Decimal
	currentWeeklyUSD decimal.Decimal
	lastPnL          *decimal.Decimal // pointer to detect uninitialized/NaN state

	// Block reason for Allow() to return
	blockReason RiskReason
}

func uniqueSources(sources []ports.RiskSource) []ports.RiskSource {
	seen := make(map[ports.RiskSource]struct{}, len(sources))
	result := make([]ports.RiskSource, 0, len(sources))
	for _, source := range sources {
		if source == "" {
			continue
		}
		if _, ok := seen[source]; ok {
			continue
		}
		seen[source] = struct{}{}
		result = append(result, source)
	}
	return result
}

func levelForSources(sources []ports.RiskSource) ports.KillLevel {
	level := ports.KillLevelOK
	for _, source := range sources {
		switch source {
		case ports.RiskSourceDailyDD, ports.RiskSourceManual:
			return ports.KillLevelKill
		case ports.RiskSourceWeeklyDD:
			if level != ports.KillLevelKill {
				level = ports.KillLevelFreeze
			}
		case ports.RiskSourceVaR, ports.RiskSourceExecutionStuck, ports.RiskSourceRecon, ports.RiskSourceDatasource:
			if level == ports.KillLevelOK {
				level = ports.KillLevelWarn
			}
		}
	}
	return level
}

func killLevelSeverity(level ports.KillLevel) int {
	switch level {
	case ports.KillLevelKill:
		return 3
	case ports.KillLevelFreeze:
		return 2
	case ports.KillLevelWarn:
		return 1
	default:
		return 0
	}
}

func (g *RiskGate) persistState(ctx context.Context) error {
	if g.repo != nil {
		return g.repo.UpsertKillState(ctx, g.state)
	}
	return nil
}

func (g *RiskGate) setSourceState(ctx context.Context, source ports.RiskSource, level ports.KillLevel, reason string) error {
	sources := uniqueSources(append(g.state.Sources, source))
	if inferred := levelForSources(sources); killLevelSeverity(inferred) > killLevelSeverity(level) {
		level = inferred
	}
	g.state = ports.KillState{
		Level:   level,
		Sources: sources,
		Since:   time.Now(),
		Reason:  reason,
	}
	return g.persistState(ctx)
}

func (g *RiskGate) clearSourceState(ctx context.Context, source ports.RiskSource, reason string) error {
	filtered := make([]ports.RiskSource, 0, len(g.state.Sources))
	for _, active := range g.state.Sources {
		if active != source {
			filtered = append(filtered, active)
		}
	}
	filtered = uniqueSources(filtered)
	g.state = ports.KillState{
		Level:   levelForSources(filtered),
		Sources: filtered,
		Since:   time.Now(),
		Reason:  reason,
	}
	return g.persistState(ctx)
}

// NewRiskGate creates a new RiskGate.
func NewRiskGate(repo ports.RiskRepo) *RiskGate {
	return &RiskGate{
		config: DefaultRiskConfig(),
		repo:   repo,
		state:  ports.KillState{Level: ports.KillLevelOK},
	}
}

// NewRiskGateWithConfig creates a RiskGate with custom config.
func NewRiskGateWithConfig(repo ports.RiskRepo, config RiskConfig) *RiskGate {
	return &RiskGate{
		config: config,
		repo:   repo,
		state:  ports.KillState{Level: ports.KillLevelOK},
	}
}

// GetState returns the current kill state.
func (g *RiskGate) GetState(ctx context.Context) (ports.KillState, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.repo != nil {
		return g.repo.GetKillState(ctx)
	}
	return g.state, nil
}

// CheckVaR checks if portfolio VaR exceeds thresholds.
func (g *RiskGate) CheckVaR(ctx context.Context, totalValue, realizedLoss decimal.Decimal) (ports.KillLevel, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if totalValue.IsZero() {
		return ports.KillLevelOK, nil
	}

	lossPct := realizedLoss.Div(totalValue).Abs()

	if lossPct.GreaterThanOrEqual(g.config.VaRKillPct) {
		if err := g.setSourceState(ctx, ports.RiskSourceVaR, ports.KillLevelKill, "VaR kill exceeded"); err != nil {
			return ports.KillLevelKill, err
		}
		return ports.KillLevelKill, nil
	}

	if lossPct.GreaterThanOrEqual(g.config.VaRWarnPct) {
		if g.state.Level != ports.KillLevelWarn || len(g.state.Sources) == 0 {
			if err := g.setSourceState(ctx, ports.RiskSourceVaR, ports.KillLevelWarn, "VaR warn exceeded"); err != nil {
				return ports.KillLevelWarn, err
			}
		}
		return ports.KillLevelWarn, nil
	}

	for _, source := range g.state.Sources {
		if source == ports.RiskSourceVaR {
			if err := g.clearSourceState(ctx, ports.RiskSourceVaR, "VaR normalized"); err != nil {
				return ports.KillLevelOK, err
			}
			break
		}
	}

	return ports.KillLevelOK, nil
}

// CheckDrawdown checks daily/weekly drawdown against thresholds.
func (g *RiskGate) CheckDrawdown(ctx context.Context, peakValue, currentValue decimal.Decimal, isWeekly bool) (ports.KillLevel, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if peakValue.IsZero() {
		return ports.KillLevelOK, nil
	}

	drawdown := peakValue.Sub(currentValue).Div(peakValue)

	var threshold decimal.Decimal
	var source ports.RiskSource
	if isWeekly {
		threshold = g.config.WeeklyDDFreezePct
		source = ports.RiskSourceWeeklyDD
	} else {
		threshold = g.config.DailyDDKillPct
		source = ports.RiskSourceDailyDD
	}

	if drawdown.GreaterThanOrEqual(threshold) {
		level := ports.KillLevelFreeze
		if !isWeekly {
			level = ports.KillLevelKill
		}
		if err := g.setSourceState(ctx, source, level, "Drawdown exceeded"); err != nil {
			return level, err
		}
		return level, nil
	}

	for _, active := range g.state.Sources {
		if active == source {
			if err := g.clearSourceState(ctx, source, "Drawdown normalized"); err != nil {
				return ports.KillLevelOK, err
			}
			break
		}
	}

	return ports.KillLevelOK, nil
}

// CheckExposure checks if total exposure exceeds limits.
func (g *RiskGate) CheckExposure(ctx context.Context, totalExposure, totalBudget decimal.Decimal) (ports.KillLevel, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if totalBudget.IsZero() {
		return ports.KillLevelOK, nil
	}

	exposurePct := totalExposure.Div(totalBudget)

	if exposurePct.GreaterThanOrEqual(g.config.TotalExposurePct) {
		if err := g.setSourceState(ctx, ports.RiskSourceRecon, ports.KillLevelWarn, "Exposure exceeded"); err != nil {
			return ports.KillLevelWarn, err
		}
		return ports.KillLevelWarn, nil
	}

	for _, source := range g.state.Sources {
		if source == ports.RiskSourceRecon {
			if err := g.clearSourceState(ctx, ports.RiskSourceRecon, "Exposure normalized"); err != nil {
				return ports.KillLevelOK, err
			}
			break
		}
	}

	return ports.KillLevelOK, nil
}

// RaiseKill manually raises the kill switch.
func (g *RiskGate) RaiseKill(ctx context.Context, reason string) error {
	g.mu.Lock()
	defer g.mu.Unlock()

	return g.setSourceState(ctx, ports.RiskSourceManual, ports.KillLevelKill, reason)
}

// LowerWarn lowers the kill switch from warn to ok.
func (g *RiskGate) LowerWarn(ctx context.Context) error {
	g.mu.Lock()
	defer g.mu.Unlock()

	if g.state.Level == ports.KillLevelKill {
		return nil
	}
	g.state = ports.KillState{Level: ports.KillLevelOK, Since: time.Now(), Reason: "Risk normalized"}
	return g.persistState(ctx)
}

// IsBlocked returns true if the kill state blocks new positions.
func (g *RiskGate) IsBlocked(ctx context.Context) (bool, error) {
	state, err := g.GetState(ctx)
	if err != nil {
		return false, err
	}
	return state.Level != ports.KillLevelOK, nil
}

// RecordRiskEvent records a risk event to the audit trail.
func (g *RiskGate) RecordRiskEvent(ctx context.Context, event ports.RiskEvent) error {
	if g.repo != nil {
		return g.repo.AppendRiskEvent(ctx, event)
	}
	return nil
}
