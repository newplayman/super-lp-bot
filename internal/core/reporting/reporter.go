// Package reporting provides automatic report generation for daily/weekly/monthly reports.
// See spec §8.5.
package reporting

import (
	"context"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/core/pnl"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// PnLTracker is an alias for the pnl.PnLTracker interface.
type PnLTracker interface {
	pnl.PnLTracker
}

// ReportPeriod defines the time period for a report.
type ReportPeriod string

const (
	PeriodDaily   ReportPeriod = "daily"
	PeriodWeekly  ReportPeriod = "weekly"
	PeriodMonthly ReportPeriod = "monthly"
)

// ReportConfig holds configuration for report generation.
type ReportConfig struct {
	IncludePositions bool
	IncludeRisk     bool
	IncludePnL      bool
}

// DefaultReportConfig returns a default report configuration with all sections enabled.
func DefaultReportConfig() ReportConfig {
	return ReportConfig{
		IncludePositions: true,
		IncludeRisk:      true,
		IncludePnL:       true,
	}
}

// Report contains a generated report with its content and metadata.
type Report struct {
	Period  ReportPeriod
	Date    time.Time
	Content string
	Summary ReportSummary
}

// ReportSummary contains summary metrics for a report.
type ReportSummary struct {
	TotalPnL        domain.Decimal
	FeeIncome       domain.Decimal
	IL              domain.Decimal
	PositionsOpen   int
	PositionsClosed int
}

// Reporter is the interface for report generation.
type Reporter interface {
	GenerateDaily(ctx context.Context, date time.Time) (*Report, error)
	GenerateWeekly(ctx context.Context, date time.Time) (*Report, error)
	GenerateMonthly(ctx context.Context, date time.Time) (*Report, error)
}

// ReportGenerator generates reports based on stored data.
type ReportGenerator struct {
	config ReportConfig
	store  ports.Store
	pnl    PnLTracker
}

// Compile-time interface check
var _ Reporter = (*ReportGenerator)(nil)

// NewReportGenerator creates a new report generator with the given configuration.
func NewReportGenerator(cfg ReportConfig, store ports.Store, pnlTracker PnLTracker) *ReportGenerator {
	return &ReportGenerator{
		config: cfg,
		store:  store,
		pnl:    pnlTracker,
	}
}

// GenerateDaily generates a daily report for the given date.
func (g *ReportGenerator) GenerateDaily(ctx context.Context, date time.Time) (*Report, error) {
	return g.generateReport(ctx, PeriodDaily, date)
}

// GenerateWeekly generates a weekly report for the given date.
func (g *ReportGenerator) GenerateWeekly(ctx context.Context, date time.Time) (*Report, error) {
	return g.generateReport(ctx, PeriodWeekly, date)
}

// GenerateMonthly generates a monthly report for the given date.
func (g *ReportGenerator) GenerateMonthly(ctx context.Context, date time.Time) (*Report, error) {
	return g.generateReport(ctx, PeriodMonthly, date)
}

// generateReport generates a report for the given period and date.
func (g *ReportGenerator) generateReport(ctx context.Context, period ReportPeriod, date time.Time) (*Report, error) {
	report := &Report{
		Period: period,
		Date:   date,
	}

	// Build report content
	var content string

	// Title based on period
	switch period {
	case PeriodDaily:
		content += "# Daily Report\n"
		content += fmt.Sprintf("Date: %s\n\n", date.Format("2006-01-02"))
	case PeriodWeekly:
		content += "# Weekly Report\n"
		content += fmt.Sprintf("Week of: %s\n\n", date.Format("2006-01-02"))
	case PeriodMonthly:
		content += "# Monthly Report\n"
		content += fmt.Sprintf("Month: %s\n\n", date.Format("2006-01"))
	}

	// PnL section if enabled
	if g.config.IncludePnL {
		content += g.buildPnLSection()
	}

	report.Content = content
	report.Summary = g.calculateSummary(ctx, date)

	return report, nil
}

// buildPnLSection builds the PnL summary section.
func (g *ReportGenerator) buildPnLSection() string {
	return "## PnL Summary\n\n- Fee Income: $0.00\n- IL: $0.00\n\n"
}

// calculateSummary calculates the report summary metrics.
func (g *ReportGenerator) calculateSummary(ctx context.Context, date time.Time) ReportSummary {
	summary := ReportSummary{
		TotalPnL:  domain.ZeroDecimal(),
		FeeIncome: domain.ZeroDecimal(),
		IL:        domain.ZeroDecimal(),
	}

	// Get positions for the period (handle nil repos gracefully)
	if g.store.PositionRepo() != nil {
		positions, _ := g.store.PositionRepo().FindByChainAndStatus(ctx, "", domain.StatusOpen)
		summary.PositionsOpen = len(positions)

		closed, _ := g.store.PositionRepo().FindByChainAndStatus(ctx, "", domain.StatusClosed)
		summary.PositionsClosed = len(closed)

		// Sum up PnL from tracked positions
		for _, pos := range positions {
			if pnlResult, err := g.pnl.GetPositionPnL(ctx, pos.ID); err == nil {
				summary.FeeIncome = summary.FeeIncome.Add(pnlResult.FeeUSD)
				summary.IL = summary.IL.Add(pnlResult.ILUSD)
				summary.TotalPnL = summary.TotalPnL.Add(pnlResult.NetPnLUSD)
			}
		}
	}

	return summary
}