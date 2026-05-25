package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math/big"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"go.uber.org/zap"
)

const (
	shadowOutcomeWorkerInterval      = 10 * time.Minute
	shadowOutcomeReportDefaultPath   = "REPORT_SHADOW_OUTCOMES_CN.md"
	shadowReadinessReportDefaultPath = "READINESS_REPORT_CN.md"
	shadowOutcomeMintGasUnits        = uint64(300000)
	shadowOutcomeExitGasUnits        = uint64(260000)
	shadowOutcomeDefaultP10LossUSD   = "-1.000000"
)

type shadowOutcomeHorizon struct {
	Name     string
	Duration time.Duration
}

var shadowOutcomeHorizons = []shadowOutcomeHorizon{
	{Name: "1h", Duration: time.Hour},
	{Name: "6h", Duration: 6 * time.Hour},
	{Name: "24h", Duration: 24 * time.Hour},
}

type shadowOutcomeLabelRecord struct {
	ID                        string
	DecisionTraceID           string
	PoolID                    string
	Chain                     string
	DecisionTime              int64
	ScoreTotal                float64
	Selected                  bool
	IntentOpen                bool
	Horizon                   string
	EntryValueUSD             domain.Decimal
	SimulatedPositionValueUSD domain.Decimal
	SimulatedFeeUSD           domain.Decimal
	SimulatedGasUSD           domain.Decimal
	SimulatedILUSD            domain.Decimal
	SimulatedNetPnLUSD        domain.Decimal
	MaxDrawdownUSD            domain.Decimal
	Label                     string
	CreatedAt                 int64
}

type shadowDecisionForOutcome struct {
	TickTime    int64
	TraceID     string
	PoolID      string
	Chain       string
	ScoreTotal  float64
	ScoreJSON   string
	Selected    bool
	IntentOpen  bool
	FinalAction string
	PositionID  string
}

type shadowMarkForOutcome struct {
	MarkTime      int64
	AmountUSD     domain.Decimal
	ValuationUSD  domain.Decimal
	FeeUSD        domain.Decimal
	ILUSD         domain.Decimal
	NetPnLUSD     domain.Decimal
	CurrentTVLUSD domain.Decimal
	CurrentVol24h domain.Decimal
}

type shadowOutcomeReportRow struct {
	Horizon         string
	Label           string
	Selected        bool
	ScoreTotal      float64
	SimulatedNetPnL domain.Decimal
	MaxDrawdownUSD  domain.Decimal
	FeeTierBPS      int
	TVLUSD          domain.Decimal
	Vol24hUSD       domain.Decimal
	VolatilityScore float64
}

type shadowOutcomeReportStats struct {
	Count                   int
	SelectedSampleCount     int
	RealizedSampleCount     int
	Wins                    int
	Losses                  int
	Invalid                 int
	Skips                   int
	InvalidRate             float64
	WinRate                 float64
	GasAdjustedPositiveRate float64
	AvgNetPnL               domain.Decimal
	MedianNetPnL            domain.Decimal
	P10NetPnL               domain.Decimal
	P90NetPnL               domain.Decimal
	MaxDrawdown             domain.Decimal
	P10ThresholdUSD         domain.Decimal
	HighScoreAvgNetPnL      domain.Decimal
	LowScoreAvgNetPnL       domain.Decimal
	HighScoreVsLow          string
}

func (app *App) ensureShadowOutcomeLabelsTable(ctx context.Context) error {
	tables, err := newRuntimeSQLTables(app.store)
	if err != nil || tables == nil || tables.db == nil {
		return nil
	}

	query := fmt.Sprintf(`
		CREATE TABLE IF NOT EXISTS %s (
			id TEXT PRIMARY KEY,
			decision_trace_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			chain TEXT NOT NULL DEFAULT '',
			decision_time BIGINT NOT NULL,
			score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
			selected BOOLEAN NOT NULL DEFAULT FALSE,
			intent_open BOOLEAN NOT NULL DEFAULT FALSE,
			horizon TEXT NOT NULL,
			entry_value_usd TEXT NOT NULL DEFAULT '0',
			simulated_position_value_usd TEXT NOT NULL DEFAULT '0',
			simulated_fee_usd TEXT NOT NULL DEFAULT '0',
			simulated_gas_usd TEXT NOT NULL DEFAULT '0',
			simulated_il_usd TEXT NOT NULL DEFAULT '0',
			simulated_net_pnl_usd TEXT NOT NULL DEFAULT '0',
			max_drawdown_usd TEXT NOT NULL DEFAULT '0',
			label TEXT NOT NULL DEFAULT 'invalid',
			created_at BIGINT NOT NULL
		)
	`, tables.shadowOutcomeTable)
	if _, err := tables.db.ExecContext(ctx, query); err != nil {
		return fmt.Errorf("ensure shadow outcome table: %w", err)
	}

	indexStatements := []string{
		fmt.Sprintf(`CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_outcomes_trace_horizon ON %s(decision_trace_id, horizon)`, tables.shadowOutcomeTable),
		fmt.Sprintf(`CREATE INDEX IF NOT EXISTS idx_shadow_outcomes_horizon_created ON %s(horizon, created_at DESC)`, tables.shadowOutcomeTable),
		fmt.Sprintf(`CREATE INDEX IF NOT EXISTS idx_shadow_outcomes_pool_horizon ON %s(pool_id, horizon, created_at DESC)`, tables.shadowOutcomeTable),
	}
	for _, stmt := range indexStatements {
		if _, err := tables.db.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("ensure shadow outcome index: %w", err)
		}
	}
	return nil
}

func (app *App) shouldRunShadowOutcomeLoop() bool {
	tables, err := newRuntimeSQLTables(app.store)
	return err == nil && tables != nil && tables.db != nil
}

func (app *App) runShadowOutcomeLoop(ctx context.Context) {
	app.backfillShadowOutcomes(ctx, time.Now().UTC())
	ticker := time.NewTicker(shadowOutcomeWorkerInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case tick := <-ticker.C:
			if err := app.backfillShadowOutcomes(ctx, tick.UTC()); err != nil && ctx.Err() == nil {
				app.logger.Warn("shadow outcome backfill failed", zap.Error(err))
			}
		}
	}
}

func classifyShadowOutcomeLabel(selected bool, intentOpen bool, action string, valid bool, netPnLUSD domain.Decimal) string {
	action = strings.TrimSpace(action)
	if !selected || !intentOpen || action == "" || action == "skip" {
		return "skip"
	}
	if !valid {
		return "invalid"
	}
	if netPnLUSD.IsPositive() {
		return "win"
	}
	return "loss"
}

func (app *App) backfillShadowOutcomes(ctx context.Context, now time.Time) error {
	tables, err := newRuntimeSQLTables(app.store)
	if err != nil || tables == nil || tables.db == nil {
		return nil
	}
	for _, horizon := range shadowOutcomeHorizons {
		matured, err := app.loadMaturedShadowDecisions(ctx, tables, horizon, now)
		if err != nil {
			return err
		}
		for _, decision := range matured {
			record, err := app.buildShadowOutcomeRecord(ctx, tables, decision, horizon, now)
			if err != nil {
				app.logger.Warn("shadow outcome build failed",
					zap.String("trace_id", decision.TraceID),
					zap.String("horizon", horizon.Name),
					zap.Error(err))
				continue
			}
			if err := app.insertShadowOutcomeRecord(ctx, tables, record); err != nil {
				return err
			}
		}
	}
	return nil
}

func (app *App) loadMaturedShadowDecisions(ctx context.Context, tables *runtimeSQLTables, horizon shadowOutcomeHorizon, now time.Time) ([]shadowDecisionForOutcome, error) {
	cutoff := now.Add(-horizon.Duration).Unix()
	query := fmt.Sprintf(`
		SELECT d.tick_time, d.trace_id, d.pool_id, d.chain, d.score_total, d.score_json,
		       d.selected, d.intent_open, d.final_action, COALESCE(d.position_id, '')
		FROM shadow_decision_trace d
		WHERE d.tick_time <= %s
		  AND NOT EXISTS (
			SELECT 1
			FROM %s o
			WHERE o.decision_trace_id = d.trace_id
			  AND o.horizon = %s
		  )
		ORDER BY d.tick_time ASC, d.id ASC
	`, tables.placeholder(1), tables.shadowOutcomeTable, tables.placeholder(2))
	rows, err := tables.db.QueryContext(ctx, query, cutoff, horizon.Name)
	if err != nil {
		return nil, fmt.Errorf("query matured shadow decisions: %w", err)
	}
	defer rows.Close()

	results := make([]shadowDecisionForOutcome, 0)
	for rows.Next() {
		var row shadowDecisionForOutcome
		if err := rows.Scan(
			&row.TickTime,
			&row.TraceID,
			&row.PoolID,
			&row.Chain,
			&row.ScoreTotal,
			&row.ScoreJSON,
			&row.Selected,
			&row.IntentOpen,
			&row.FinalAction,
			&row.PositionID,
		); err != nil {
			return nil, fmt.Errorf("scan matured shadow decision: %w", err)
		}
		results = append(results, row)
	}
	return results, rows.Err()
}

func (app *App) buildShadowOutcomeRecord(ctx context.Context, tables *runtimeSQLTables, decision shadowDecisionForOutcome, horizon shadowOutcomeHorizon, now time.Time) (shadowOutcomeLabelRecord, error) {
	record := shadowOutcomeLabelRecord{
		ID:              shadowID("shadow-outcome", decision.TraceID+":"+horizon.Name, decision.TickTime),
		DecisionTraceID: decision.TraceID,
		PoolID:          decision.PoolID,
		Chain:           decision.Chain,
		DecisionTime:    decision.TickTime,
		ScoreTotal:      decision.ScoreTotal,
		Selected:        decision.Selected,
		IntentOpen:      decision.IntentOpen,
		Horizon:         horizon.Name,
		CreatedAt:       now.UnixMilli(),
	}

	if !decision.Selected || !decision.IntentOpen || (decision.FinalAction != "open_shadow_position" && decision.FinalAction != "reuse_shadow_position") {
		record.Label = classifyShadowOutcomeLabel(decision.Selected, decision.IntentOpen, decision.FinalAction, true, domain.ZeroDecimal())
		return record, nil
	}
	if strings.TrimSpace(decision.PositionID) == "" {
		record.Label = classifyShadowOutcomeLabel(decision.Selected, decision.IntentOpen, decision.FinalAction, false, domain.ZeroDecimal())
		return record, nil
	}

	targetTime := decision.TickTime + int64(horizon.Duration.Seconds())
	entryAmount, err := app.loadShadowEntryValue(ctx, tables, decision.PositionID)
	if err != nil {
		return shadowOutcomeLabelRecord{}, err
	}
	outcomeMark, ok, err := app.loadShadowOutcomeMark(ctx, tables, decision.PositionID, targetTime)
	if err != nil {
		return shadowOutcomeLabelRecord{}, err
	}
	if !ok {
		record.EntryValueUSD = entryAmount
		record.Label = classifyShadowOutcomeLabel(decision.Selected, decision.IntentOpen, decision.FinalAction, false, domain.ZeroDecimal())
		return record, nil
	}

	gasUSD := app.estimateShadowOutcomeGasUSD(ctx, decision.Chain, decision.PoolID)
	netPnLUSD := outcomeMark.NetPnLUSD.Sub(gasUSD)
	maxDrawdownUSD, err := app.loadShadowOutcomeMaxDrawdown(ctx, tables, decision.PositionID, decision.TickTime, outcomeMark.MarkTime)
	if err != nil {
		return shadowOutcomeLabelRecord{}, err
	}

	record.EntryValueUSD = entryAmount
	record.SimulatedPositionValueUSD = outcomeMark.ValuationUSD
	record.SimulatedFeeUSD = outcomeMark.FeeUSD
	record.SimulatedGasUSD = gasUSD
	record.SimulatedILUSD = outcomeMark.ILUSD
	record.SimulatedNetPnLUSD = netPnLUSD
	record.MaxDrawdownUSD = maxDrawdownUSD
	record.Label = classifyShadowOutcomeLabel(decision.Selected, decision.IntentOpen, decision.FinalAction, true, netPnLUSD)
	return record, nil
}

func (app *App) loadShadowEntryValue(ctx context.Context, tables *runtimeSQLTables, positionID string) (domain.Decimal, error) {
	query := `
		SELECT COALESCE(amount_usd, '0')
		FROM shadow_position_marks
		WHERE position_id = ` + tables.placeholder(1) + `
		ORDER BY mark_time ASC, id ASC
		LIMIT 1
	`
	var amount string
	if err := tables.db.QueryRowContext(ctx, query, positionID).Scan(&amount); err != nil {
		if err == sql.ErrNoRows {
			return domain.ZeroDecimal(), nil
		}
		return domain.ZeroDecimal(), fmt.Errorf("query shadow entry value for %s: %w", positionID, err)
	}
	return decimalFromStringSafe(amount), nil
}

func (app *App) loadShadowOutcomeMark(ctx context.Context, tables *runtimeSQLTables, positionID string, minMarkTime int64) (shadowMarkForOutcome, bool, error) {
	query := `
		SELECT mark_time, amount_usd, valuation_usd, fee_usd, il_usd, net_pnl_usd,
		       COALESCE(current_tvl_usd, '0'), COALESCE(current_vol24h_usd, '0')
		FROM shadow_position_marks
		WHERE position_id = ` + tables.placeholder(1) + `
		  AND mark_time >= ` + tables.placeholder(2) + `
		ORDER BY mark_time ASC, id ASC
		LIMIT 1
	`
	var row shadowMarkForOutcome
	err := tables.db.QueryRowContext(ctx, query, positionID, minMarkTime).Scan(
		&row.MarkTime,
		stringScanner(&row.AmountUSD),
		stringScanner(&row.ValuationUSD),
		stringScanner(&row.FeeUSD),
		stringScanner(&row.ILUSD),
		stringScanner(&row.NetPnLUSD),
		stringScanner(&row.CurrentTVLUSD),
		stringScanner(&row.CurrentVol24h),
	)
	if err == sql.ErrNoRows {
		return shadowMarkForOutcome{}, false, nil
	}
	if err != nil {
		return shadowMarkForOutcome{}, false, fmt.Errorf("query shadow outcome mark for %s: %w", positionID, err)
	}
	return row, true, nil
}

func (app *App) loadShadowOutcomeMaxDrawdown(ctx context.Context, tables *runtimeSQLTables, positionID string, startTime int64, endTime int64) (domain.Decimal, error) {
	query := `
		SELECT COALESCE(MIN(CAST(net_pnl_usd AS NUMERIC)), 0)
		FROM shadow_position_marks
		WHERE position_id = ` + tables.placeholder(1) + `
		  AND mark_time >= ` + tables.placeholder(2) + `
		  AND mark_time <= ` + tables.placeholder(3) + `
	`
	var minPnL string
	if err := tables.db.QueryRowContext(ctx, query, positionID, startTime, endTime).Scan(&minPnL); err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("query shadow drawdown for %s: %w", positionID, err)
	}
	return decimalFromStringSafe(minPnL), nil
}

func (app *App) estimateShadowOutcomeGasUSD(ctx context.Context, chain string, poolID string) domain.Decimal {
	if !strings.EqualFold(strings.TrimSpace(chain), string(domain.ChainBase)) {
		return domain.ZeroDecimal()
	}
	provider := app.rpcProviderForChain(domain.ChainBase)
	if provider == nil {
		return domain.ZeroDecimal()
	}
	gasPriceWei, err := provider.SuggestGasPrice(ctx)
	if err != nil || gasPriceWei == nil || gasPriceWei.Sign() <= 0 {
		return domain.ZeroDecimal()
	}
	ethPriceUSD, err := estimateShadowOutcomeBaseWETHPriceUSD(ctx, provider, poolID)
	if err != nil || ethPriceUSD.IsZero() {
		return domain.ZeroDecimal()
	}
	totalWei := new(big.Int).Mul(new(big.Int).SetUint64(shadowOutcomeMintGasUnits+shadowOutcomeExitGasUnits), gasPriceWei)
	return decimalFromWei(totalWei, 18).Mul(ethPriceUSD)
}

func estimateShadowOutcomeBaseWETHPriceUSD(ctx context.Context, provider *rpc.RoundRobinProvider, poolID string) (domain.Decimal, error) {
	poolAddr := parseAddressOrZero(poolID)
	if provider == nil || poolAddr.IsZero() {
		return domain.ZeroDecimal(), nil
	}
	tick, err := dashboardReadV3PoolTick(ctx, provider, poolAddr)
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	token0, err := callAddressMethod(ctx, provider, poolAddr, "token0()")
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	token1, err := callAddressMethod(ctx, provider, poolAddr, "token1()")
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	return estimateBaseWETHPriceUSD(ctx, domain.Pool{
		ID:     poolID,
		Chain:  domain.ChainBase,
		Token0: token0,
		Token1: token1,
		Tick:   tick,
	}, provider)
}

func (app *App) insertShadowOutcomeRecord(ctx context.Context, tables *runtimeSQLTables, record shadowOutcomeLabelRecord) error {
	query := fmt.Sprintf(`
		INSERT INTO %s (
			id, decision_trace_id, pool_id, chain, decision_time, score_total, selected, intent_open,
			horizon, entry_value_usd, simulated_position_value_usd, simulated_fee_usd, simulated_gas_usd,
			simulated_il_usd, simulated_net_pnl_usd, max_drawdown_usd, label, created_at
		) VALUES (
			%s, %s, %s, %s, %s, %s, %s, %s,
			%s, %s, %s, %s, %s, %s, %s, %s, %s, %s
		)
	`, tables.shadowOutcomeTable,
		tables.placeholder(1), tables.placeholder(2), tables.placeholder(3), tables.placeholder(4), tables.placeholder(5), tables.placeholder(6), tables.placeholder(7), tables.placeholder(8),
		tables.placeholder(9), tables.placeholder(10), tables.placeholder(11), tables.placeholder(12), tables.placeholder(13), tables.placeholder(14), tables.placeholder(15), tables.placeholder(16), tables.placeholder(17), tables.placeholder(18))
	if tables.dialect == "sqlite" {
		query += ` ON CONFLICT(decision_trace_id, horizon) DO NOTHING`
	} else {
		query += ` ON CONFLICT (decision_trace_id, horizon) DO NOTHING`
	}
	_, err := tables.db.ExecContext(ctx, query,
		record.ID,
		record.DecisionTraceID,
		record.PoolID,
		record.Chain,
		record.DecisionTime,
		record.ScoreTotal,
		record.Selected,
		record.IntentOpen,
		record.Horizon,
		record.EntryValueUSD.String(),
		record.SimulatedPositionValueUSD.String(),
		record.SimulatedFeeUSD.String(),
		record.SimulatedGasUSD.String(),
		record.SimulatedILUSD.String(),
		record.SimulatedNetPnLUSD.String(),
		record.MaxDrawdownUSD.String(),
		record.Label,
		record.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert shadow outcome %s/%s: %w", record.DecisionTraceID, record.Horizon, err)
	}
	return nil
}

func (app *App) generateShadowOutcomeReport(ctx context.Context, outputPath string) error {
	tables, err := newRuntimeSQLTables(app.store)
	if err != nil || tables == nil || tables.db == nil {
		return fmt.Errorf("shadow outcome report requires store DB access")
	}
	rows, err := app.loadShadowOutcomeReportRows(ctx, tables)
	if err != nil {
		return err
	}
	report := renderShadowOutcomeReport(rows, time.Now().UTC())
	path := strings.TrimSpace(outputPath)
	if path == "" {
		path = shadowOutcomeReportDefaultPath
	}
	if err := os.WriteFile(path, []byte(report), 0644); err != nil {
		return fmt.Errorf("write shadow outcome report: %w", err)
	}
	return nil
}

func (app *App) loadShadowOutcomeReportRows(ctx context.Context, tables *runtimeSQLTables) ([]shadowOutcomeReportRow, error) {
	query := fmt.Sprintf(`
		SELECT
			o.horizon,
			o.label,
			o.selected,
			o.score_total,
			o.simulated_net_pnl_usd,
			o.max_drawdown_usd,
			COALESCE(p.fee_bps, 0),
			COALESCE(p.tvl_usd, '0'),
			COALESCE(p.vol_24h, '0'),
			COALESCE(d.score_json, '{}')
		FROM %s o
		LEFT JOIN (
			SELECT pool_id, MAX(fee_bps) AS fee_bps, MAX(COALESCE(tvl_usd, '0')) AS tvl_usd, MAX(COALESCE(vol_24h, '0')) AS vol_24h
			FROM pools
			GROUP BY pool_id
		) p ON p.pool_id = o.pool_id
		LEFT JOIN shadow_decision_trace d ON d.trace_id = o.decision_trace_id
		ORDER BY o.horizon, o.created_at DESC
	`, tables.shadowOutcomeTable)
	sqlRows, err := tables.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query shadow outcome report rows: %w", err)
	}
	defer sqlRows.Close()

	results := make([]shadowOutcomeReportRow, 0)
	for sqlRows.Next() {
		var row shadowOutcomeReportRow
		var scoreJSON string
		if err := sqlRows.Scan(
			&row.Horizon,
			&row.Label,
			&row.Selected,
			&row.ScoreTotal,
			stringScanner(&row.SimulatedNetPnL),
			stringScanner(&row.MaxDrawdownUSD),
			&row.FeeTierBPS,
			stringScanner(&row.TVLUSD),
			stringScanner(&row.Vol24hUSD),
			&scoreJSON,
		); err != nil {
			return nil, fmt.Errorf("scan shadow outcome report row: %w", err)
		}
		var score domain.Score
		if err := json.Unmarshal([]byte(scoreJSON), &score); err == nil {
			row.VolatilityScore = score.VolatilityScore
		}
		results = append(results, row)
	}
	return results, sqlRows.Err()
}

func renderShadowOutcomeReport(rows []shadowOutcomeReportRow, generatedAt time.Time) string {
	var b strings.Builder
	p10Threshold := shadowOutcomeP10ThresholdUSD()
	b.WriteString("# Shadow Outcome 回填报告\n\n")
	b.WriteString(fmt.Sprintf("- 生成时间: %s\n", generatedAt.Format(time.RFC3339)))
	b.WriteString("- 口径: `simulated_net_pnl_usd` 当前是 shadow mark 净值减去估算 gas；`lvr` 仍未纳入。\n")
	b.WriteString("- 标签: `win/loss/skip/invalid`\n\n")
	if len(rows) == 0 {
		b.WriteString("当前还没有可用样本。先运行 shadow worker/backfill，再重新生成本报告。\n")
		return b.String()
	}

	for _, horizon := range shadowOutcomeHorizons {
		subset := filterShadowOutcomeRows(rows, func(row shadowOutcomeReportRow) bool { return row.Horizon == horizon.Name })
		stats := computeShadowOutcomeStats(subset)
		b.WriteString(fmt.Sprintf("## %s\n\n", horizon.Name))
		b.WriteString(fmt.Sprintf("- 样本数: %d\n", stats.Count))
		b.WriteString(fmt.Sprintf("- selected_sample_count: %d\n", stats.SelectedSampleCount))
		b.WriteString(fmt.Sprintf("- realized_sample_count: %d\n", stats.RealizedSampleCount))
		b.WriteString(fmt.Sprintf("- 标签分布: win=%d loss=%d skip=%d invalid=%d\n", stats.Wins, stats.Losses, stats.Skips, stats.Invalid))
		b.WriteString(fmt.Sprintf("- invalid_rate: %.2f%%\n", stats.InvalidRate*100))
		b.WriteString(fmt.Sprintf("- 胜率: %.2f%%\n", stats.WinRate*100))
		b.WriteString(fmt.Sprintf("- gas_adjusted_positive_rate: %.2f%%\n", stats.GasAdjustedPositiveRate*100))
		b.WriteString(fmt.Sprintf("- 平均净收益: %s USD\n", stats.AvgNetPnL.StringFixed(6)))
		b.WriteString(fmt.Sprintf("- 中位数净收益: %s USD\n", stats.MedianNetPnL.StringFixed(6)))
		b.WriteString(fmt.Sprintf("- P10 / P90: %s / %s USD\n", stats.P10NetPnL.StringFixed(6), stats.P90NetPnL.StringFixed(6)))
		b.WriteString(fmt.Sprintf("- p10 阈值: %s USD\n", p10Threshold.StringFixed(6)))
		b.WriteString(fmt.Sprintf("- 最大回撤样本值: %s USD\n", stats.MaxDrawdown.StringFixed(6)))
		b.WriteString(fmt.Sprintf("- high_score_vs_low_score: %s (high=%s, low=%s)\n",
			stats.HighScoreVsLow,
			stats.HighScoreAvgNetPnL.StringFixed(6),
			stats.LowScoreAvgNetPnL.StringFixed(6),
		))
		b.WriteString(fmt.Sprintf("- 结论: %s\n\n", classifyShadowOutcomeVerdict(stats)))

		appendShadowOutcomeBucketTable(&b, "按 Score Bucket", subset, scoreBucketLabel)
		appendShadowOutcomeBucketTable(&b, "按 TVL Bucket", subset, tvlBucketLabel)
		appendShadowOutcomeBucketTable(&b, "按 Fee Tier", subset, feeTierBucketLabel)
		appendShadowOutcomeBucketTable(&b, "按 Volatility Bucket", subset, volatilityBucketLabel)
	}
	return b.String()
}

func appendShadowOutcomeBucketTable(b *strings.Builder, title string, rows []shadowOutcomeReportRow, bucketFn func(shadowOutcomeReportRow) string) {
	if len(rows) == 0 {
		return
	}
	buckets := map[string][]shadowOutcomeReportRow{}
	for _, row := range rows {
		label := bucketFn(row)
		buckets[label] = append(buckets[label], row)
	}
	labels := make([]string, 0, len(buckets))
	for label := range buckets {
		labels = append(labels, label)
	}
	sort.Strings(labels)

	b.WriteString(fmt.Sprintf("### %s\n\n", title))
	b.WriteString("| Bucket | Samples | Win Rate | Avg Net | Median | Verdict |\n")
	b.WriteString("| --- | ---: | ---: | ---: | ---: | --- |\n")
	for _, label := range labels {
		stats := computeShadowOutcomeStats(buckets[label])
		b.WriteString(fmt.Sprintf("| %s | %d | %.2f%% | %s | %s | %s |\n",
			label,
			stats.Count,
			stats.WinRate*100,
			stats.AvgNetPnL.StringFixed(6),
			stats.MedianNetPnL.StringFixed(6),
			classifyShadowOutcomeVerdict(stats),
		))
	}
	b.WriteString("\n")
}

func filterShadowOutcomeRows(rows []shadowOutcomeReportRow, keep func(shadowOutcomeReportRow) bool) []shadowOutcomeReportRow {
	filtered := make([]shadowOutcomeReportRow, 0, len(rows))
	for _, row := range rows {
		if keep(row) {
			filtered = append(filtered, row)
		}
	}
	return filtered
}

func computeShadowOutcomeStats(rows []shadowOutcomeReportRow) shadowOutcomeReportStats {
	stats := shadowOutcomeReportStats{
		Count:           len(rows),
		MaxDrawdown:     domain.ZeroDecimal(),
		P10ThresholdUSD: shadowOutcomeP10ThresholdUSD(),
		HighScoreVsLow:  "insufficient",
	}
	if len(rows) == 0 {
		return stats
	}
	realized := make([]domain.Decimal, 0, len(rows))
	highScore := make([]domain.Decimal, 0)
	lowScore := make([]domain.Decimal, 0)
	for _, row := range rows {
		if row.Selected && row.Label != "skip" {
			stats.SelectedSampleCount++
		}
		switch row.Label {
		case "win":
			stats.Wins++
		case "loss":
			stats.Losses++
		case "skip":
			stats.Skips++
		case "invalid":
			stats.Invalid++
		}
		if row.Label == "win" || row.Label == "loss" {
			realized = append(realized, row.SimulatedNetPnL)
			stats.AvgNetPnL = stats.AvgNetPnL.Add(row.SimulatedNetPnL)
			if row.MaxDrawdownUSD.LessThan(stats.MaxDrawdown) {
				stats.MaxDrawdown = row.MaxDrawdownUSD
			}
			if row.ScoreTotal >= 80 {
				highScore = append(highScore, row.SimulatedNetPnL)
			}
			if row.ScoreTotal < 70 {
				lowScore = append(lowScore, row.SimulatedNetPnL)
			}
		}
	}
	actionable := stats.Wins + stats.Losses + stats.Invalid
	if actionable > 0 {
		stats.InvalidRate = float64(stats.Invalid) / float64(actionable)
	}
	if stats.Wins+stats.Losses > 0 {
		stats.RealizedSampleCount = stats.Wins + stats.Losses
		stats.WinRate = float64(stats.Wins) / float64(stats.Wins+stats.Losses)
		stats.GasAdjustedPositiveRate = stats.WinRate
		stats.AvgNetPnL = stats.AvgNetPnL.Div(domain.NewDecimalFromInt(int64(stats.Wins + stats.Losses)))
	}
	if len(realized) == 0 {
		stats.HighScoreAvgNetPnL = averageDecimal(highScore)
		stats.LowScoreAvgNetPnL = averageDecimal(lowScore)
		stats.HighScoreVsLow = compareShadowOutcomeBuckets(stats.HighScoreAvgNetPnL, len(highScore), stats.LowScoreAvgNetPnL, len(lowScore))
		return stats
	}
	sort.Slice(realized, func(i, j int) bool { return realized[i].LessThan(realized[j]) })
	stats.MedianNetPnL = quantileDecimal(realized, 0.5)
	stats.P10NetPnL = quantileDecimal(realized, 0.1)
	stats.P90NetPnL = quantileDecimal(realized, 0.9)
	stats.HighScoreAvgNetPnL = averageDecimal(highScore)
	stats.LowScoreAvgNetPnL = averageDecimal(lowScore)
	stats.HighScoreVsLow = compareShadowOutcomeBuckets(stats.HighScoreAvgNetPnL, len(highScore), stats.LowScoreAvgNetPnL, len(lowScore))
	return stats
}

func quantileDecimal(values []domain.Decimal, q float64) domain.Decimal {
	if len(values) == 0 {
		return domain.ZeroDecimal()
	}
	if q <= 0 {
		return values[0]
	}
	if q >= 1 {
		return values[len(values)-1]
	}
	index := int(float64(len(values)-1) * q)
	if index < 0 {
		index = 0
	}
	if index >= len(values) {
		index = len(values) - 1
	}
	return values[index]
}

func classifyShadowOutcomeVerdict(stats shadowOutcomeReportStats) string {
	realizedCount := stats.RealizedSampleCount
	if realizedCount == 0 {
		return "FAIL"
	}
	if realizedCount < 20 {
		if stats.AvgNetPnL.IsPositive() || stats.MedianNetPnL.IsPositive() {
			return "WARN"
		}
		return "FAIL"
	}
	switch {
	case stats.InvalidRate > 0.30:
		return "FAIL"
	case stats.AvgNetPnL.LessThanOrEqual(domain.ZeroDecimal()):
		return "FAIL"
	case stats.MedianNetPnL.LessThanOrEqual(domain.ZeroDecimal()):
		return "FAIL"
	case stats.P10NetPnL.LessThan(stats.P10ThresholdUSD):
		return "FAIL"
	case stats.HighScoreVsLow == "worse":
		return "FAIL"
	case stats.HighScoreVsLow == "better":
		return "PASS"
	case stats.HighScoreVsLow == "flat" || stats.HighScoreVsLow == "insufficient":
		return "WARN"
	default:
		return "FAIL"
	}
}

func shadowOutcomeP10ThresholdUSD() domain.Decimal {
	value := strings.TrimSpace(os.Getenv("LPBOT_SHADOW_MAX_P10_LOSS_USD"))
	if value == "" {
		value = shadowOutcomeDefaultP10LossUSD
	}
	return decimalFromStringSafe(value)
}

func averageDecimal(values []domain.Decimal) domain.Decimal {
	if len(values) == 0 {
		return domain.ZeroDecimal()
	}
	total := domain.ZeroDecimal()
	for _, value := range values {
		total = total.Add(value)
	}
	return total.Div(domain.NewDecimalFromInt(int64(len(values))))
}

func compareShadowOutcomeBuckets(high domain.Decimal, highCount int, low domain.Decimal, lowCount int) string {
	if highCount == 0 || lowCount == 0 {
		return "insufficient"
	}
	switch {
	case high.GreaterThan(low):
		return "better"
	case high.LessThan(low):
		return "worse"
	default:
		return "flat"
	}
}

func scoreBucketLabel(row shadowOutcomeReportRow) string {
	switch {
	case row.ScoreTotal >= 90:
		return "90+"
	case row.ScoreTotal >= 80:
		return "80-89"
	case row.ScoreTotal >= 70:
		return "70-79"
	case row.ScoreTotal >= 60:
		return "60-69"
	default:
		return "<60"
	}
}

func tvlBucketLabel(row shadowOutcomeReportRow) string {
	switch {
	case row.TVLUSD.GreaterThanOrEqual(domain.MustDecimal("1000000")):
		return ">=1m"
	case row.TVLUSD.GreaterThanOrEqual(domain.MustDecimal("250000")):
		return "250k-1m"
	case row.TVLUSD.GreaterThanOrEqual(domain.MustDecimal("50000")):
		return "50k-250k"
	default:
		return "<50k"
	}
}

func feeTierBucketLabel(row shadowOutcomeReportRow) string {
	switch row.FeeTierBPS {
	case 1, 5:
		return "<=5 bps"
	case 30:
		return "30 bps"
	case 100:
		return "100 bps"
	default:
		return fmt.Sprintf("%d bps", row.FeeTierBPS)
	}
}

func volatilityBucketLabel(row shadowOutcomeReportRow) string {
	switch {
	case row.VolatilityScore >= 80:
		return "80+"
	case row.VolatilityScore >= 60:
		return "60-79"
	case row.VolatilityScore >= 40:
		return "40-59"
	default:
		return "<40"
	}
}
