// Package reporting provides automatic report generation for daily/weekly/monthly reports.
// See spec §8.5.
package reporting

import (
	"context"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/core/pnl"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface compliance check.
var _ Reporter = (*reportGeneratorNop)(nil)

// reportGeneratorNop is a no-op implementation for compile-time interface checks.
type reportGeneratorNop struct{}

func (n *reportGeneratorNop) GenerateDaily(ctx context.Context, date time.Time) (*Report, error) {
	return nil, nil
}

func (n *reportGeneratorNop) GenerateWeekly(ctx context.Context, date time.Time) (*Report, error) {
	return nil, nil
}

func (n *reportGeneratorNop) GenerateMonthly(ctx context.Context, date time.Time) (*Report, error) {
	return nil, nil
}

// storeNop is a no-op Store for testing.
type storeNop struct{}

func (s *storeNop) TxRepo() ports.TxRepo                           { return nil }
func (s *storeNop) PositionRepo() ports.PositionRepo               { return nil }
func (s *storeNop) PoolRepo() ports.PoolRepo                       { return nil }
func (s *storeNop) LedgerRepo() ports.LedgerRepo                   { return nil }
func (s *storeNop) RiskRepo() ports.RiskRepo                       { return nil }
func (s *storeNop) ExecutionIntentRepo() ports.ExecutionIntentRepo { return nil }
func (s *storeNop) ConfigSnap() ports.ConfigSnap                   { return nil }

// TestReportGenerator_DailyReport verifies daily report generation.
func TestReportGenerator_DailyReport(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()

	report, err := generator.GenerateDaily(ctx, time.Now())
	require.NoError(t, err)
	require.NotNil(t, report)
	require.Contains(t, report.Content, "# Daily Report")
	require.Contains(t, report.Content, time.Now().Format("2006-01-02"))
}

// TestReportGenerator_WeeklyReport verifies weekly report generation.
func TestReportGenerator_WeeklyReport(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()

	report, err := generator.GenerateWeekly(ctx, time.Now())
	require.NoError(t, err)
	require.NotNil(t, report)
	require.Contains(t, report.Content, "# Weekly Report")
}

// TestReportGenerator_MonthlyReport verifies monthly report generation.
func TestReportGenerator_MonthlyReport(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()

	report, err := generator.GenerateMonthly(ctx, time.Now())
	require.NoError(t, err)
	require.NotNil(t, report)
	require.Contains(t, report.Content, "# Monthly Report")
}

// TestReportGenerator_PnLSection verifies PnL section is included in daily report.
func TestReportGenerator_PnLSection(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()

	report, err := generator.GenerateDaily(ctx, time.Now())
	require.NoError(t, err)
	require.Contains(t, report.Content, "## PnL Summary")
	require.Contains(t, report.Content, "Fee Income:")
	require.Contains(t, report.Content, "IL:")
}

// TestReportGenerator_Period verifies the report period is set correctly.
func TestReportGenerator_Period(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()
	now := time.Now()

	// Daily report
	daily, err := generator.GenerateDaily(ctx, now)
	require.NoError(t, err)
	require.Equal(t, PeriodDaily, daily.Period)

	// Weekly report
	weekly, err := generator.GenerateWeekly(ctx, now)
	require.NoError(t, err)
	require.Equal(t, PeriodWeekly, weekly.Period)

	// Monthly report
	monthly, err := generator.GenerateMonthly(ctx, now)
	require.NoError(t, err)
	require.Equal(t, PeriodMonthly, monthly.Period)
}

// TestReportGenerator_ReportDate verifies the report date matches input.
func TestReportGenerator_ReportDate(t *testing.T) {
	generator := NewReportGenerator(DefaultReportConfig(), &storeNop{}, &pnlNop{})
	ctx := context.Background()
	testDate := time.Date(2024, 1, 15, 0, 0, 0, 0, time.UTC)

	report, err := generator.GenerateDaily(ctx, testDate)
	require.NoError(t, err)
	require.Equal(t, testDate, report.Date)
}

// TestReportGenerator_DefaultConfig verifies default config creates valid generator.
func TestReportGenerator_DefaultConfig(t *testing.T) {
	cfg := DefaultReportConfig()
	require.True(t, cfg.IncludePnL)
	require.True(t, cfg.IncludePositions)
	require.True(t, cfg.IncludeRisk)
}

// pnlNop is a no-op PnLTracker for testing.
type pnlNop struct{}

func (n *pnlNop) MarkPrice(ctx context.Context) (int, error) { return 0, nil }
func (n *pnlNop) GetPositionPnL(ctx context.Context, positionID string) (*pnl.PnLResult, error) {
	return &pnl.PnLResult{}, nil
}
func (n *pnlNop) GetPositionSnapshot(ctx context.Context, positionID string) (*pnl.PositionSnapshot, error) {
	return &pnl.PositionSnapshot{}, nil
}
func (n *pnlNop) RecordRealizedPnL(ctx context.Context, positionID string, txHash string) (*pnl.PnLResult, error) {
	return &pnl.PnLResult{}, nil
}
func (n *pnlNop) TrackPosition(ctx context.Context, pos *domain.Position) error { return nil }
func (n *pnlNop) UntrackPosition(ctx context.Context, positionID string) error  { return nil }
