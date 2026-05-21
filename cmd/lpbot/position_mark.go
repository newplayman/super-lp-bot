package main

import (
	"context"
	"database/sql"
	"fmt"
	"sort"
	"time"

	"github.com/lpbot/lpbot/internal/core/pnl"
	dexdomain "github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/metrics"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

type shadowPositionMarkRecord struct {
	MarkTime       int64
	PositionID     string
	PoolID         string
	Chain          string
	Status         string
	Tier           string
	AmountUSD      string
	Source         string
	HoldMinutes    int64
	ValuationUSD   string
	FeeUSD         string
	ILUSD          string
	NetPnLUSD      string
	CurrentTVLUSD  string
	CurrentVol24h  string
	PriceChangePct string
	CreatedAt      int64
}

type activeShadowPosition struct {
	ID        string
	PoolID    string
	Chain     dexdomain.ChainID
	Status    dexdomain.PositionStatus
	Tier      dexdomain.Tier
	AmountUSD dexdomain.Decimal
	TickLower int64
	TickUpper int64
	OpenedAt  int64
	ClosedAt  int64
}

type shadowExitDecisionRecord struct {
	DecisionTime   int64
	PositionID     string
	PoolID         string
	Chain          string
	Status         string
	Tier           string
	AmountUSD      string
	HoldMinutes    int64
	CurrentTVLUSD  string
	NetPnLUSD      string
	ILUSD          string
	PriceChangePct string
	WouldExit      bool
	Reason         string
	Action         string
	CreatedAt      int64
}

type shadowExitActionRecord struct {
	DecisionTime int64
	PositionID   string
	PoolID       string
	Chain        string
	Reason       string
	Action       string
	TxHash       string
	TxStatus     string
	CreatedAt    int64
}

func (app *App) ensureShadowPositionMarksTable(ctx context.Context) error {
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return nil
	}

	_, err := provider.DB().ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS shadow_position_marks (
			id BIGSERIAL PRIMARY KEY,
			mark_time BIGINT NOT NULL,
			position_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			chain TEXT NOT NULL,
			status TEXT NOT NULL,
			tier TEXT NOT NULL DEFAULT '',
			amount_usd TEXT NOT NULL DEFAULT '0',
			source TEXT NOT NULL DEFAULT '',
			hold_minutes BIGINT NOT NULL DEFAULT 0,
			valuation_usd TEXT NOT NULL DEFAULT '0',
			fee_usd TEXT NOT NULL DEFAULT '0',
			il_usd TEXT NOT NULL DEFAULT '0',
			net_pnl_usd TEXT NOT NULL DEFAULT '0',
			current_tvl_usd TEXT NOT NULL DEFAULT '0',
			current_vol24h_usd TEXT NOT NULL DEFAULT '0',
			price_change_pct TEXT NOT NULL DEFAULT '0',
			created_at BIGINT NOT NULL
		);

		CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_position_time
			ON shadow_position_marks(position_id, mark_time DESC);
		CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_mark_time
			ON shadow_position_marks(mark_time DESC);

		ALTER TABLE shadow_position_marks
			ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT '';
		ALTER TABLE shadow_position_marks
			ADD COLUMN IF NOT EXISTS amount_usd TEXT NOT NULL DEFAULT '0';
	`)
	if err != nil {
		return fmt.Errorf("ensure shadow_position_marks table: %w", err)
	}
	return nil
}

func (app *App) ensureShadowExitDecisionsTable(ctx context.Context) error {
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return nil
	}

	_, err := provider.DB().ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS shadow_exit_decisions (
			id BIGSERIAL PRIMARY KEY,
			decision_time BIGINT NOT NULL,
			position_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			chain TEXT NOT NULL,
			status TEXT NOT NULL,
			tier TEXT NOT NULL,
			amount_usd TEXT NOT NULL DEFAULT '0',
			hold_minutes BIGINT NOT NULL DEFAULT 0,
			current_tvl_usd TEXT NOT NULL DEFAULT '0',
			net_pnl_usd TEXT NOT NULL DEFAULT '0',
			il_usd TEXT NOT NULL DEFAULT '0',
			price_change_pct TEXT NOT NULL DEFAULT '0',
			would_exit BOOLEAN NOT NULL DEFAULT FALSE,
			reason TEXT NOT NULL DEFAULT '',
			action TEXT NOT NULL DEFAULT 'hold',
			created_at BIGINT NOT NULL
		);

		CREATE INDEX IF NOT EXISTS idx_shadow_exit_decisions_position_time
			ON shadow_exit_decisions(position_id, decision_time DESC);
		CREATE INDEX IF NOT EXISTS idx_shadow_exit_decisions_decision_time
			ON shadow_exit_decisions(decision_time DESC);
	`)
	if err != nil {
		return fmt.Errorf("ensure shadow_exit_decisions table: %w", err)
	}
	return nil
}

func (app *App) ensureShadowExitActionsTable(ctx context.Context) error {
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return nil
	}

	_, err := provider.DB().ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS shadow_exit_actions (
			id BIGSERIAL PRIMARY KEY,
			decision_time BIGINT NOT NULL,
			position_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			chain TEXT NOT NULL,
			reason TEXT NOT NULL DEFAULT '',
			action TEXT NOT NULL DEFAULT '',
			tx_hash TEXT NOT NULL DEFAULT '',
			tx_status TEXT NOT NULL DEFAULT '',
			created_at BIGINT NOT NULL
		);

		CREATE INDEX IF NOT EXISTS idx_shadow_exit_actions_position_time
			ON shadow_exit_actions(position_id, decision_time DESC);
		CREATE INDEX IF NOT EXISTS idx_shadow_exit_actions_decision_time
			ON shadow_exit_actions(decision_time DESC);
	`)
	if err != nil {
		return fmt.Errorf("ensure shadow_exit_actions table: %w", err)
	}
	return nil
}

func (app *App) markShadowPositions(ctx context.Context) {
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return
	}
	if app.datasource == nil {
		return
	}

	positions, err := app.listActiveShadowPositions(ctx, provider.DB())
	if err != nil {
		app.logger.Warn("shadow position mark query failed", zap.Error(err))
		return
	}
	if len(positions) == 0 {
		metrics.RecordShadowPositionMarks(0, 0, 0)
		return
	}

	now := time.Now()
	records := make([]shadowPositionMarkRecord, 0, len(positions))
	exitDecisions := make([]shadowExitDecisionRecord, 0, len(positions))
	totalValuation := dexdomain.ZeroDecimal()
	totalNetPnL := dexdomain.ZeroDecimal()
	exitSignals := 0

	for _, pos := range positions {
		record, err := app.buildPositionMarkRecord(ctx, pos, now)
		if err != nil {
			app.logger.Warn("shadow position mark failed",
				zap.String("position_id", pos.ID),
				zap.Error(err))
			continue
		}
		records = append(records, record)
		totalValuation = totalValuation.Add(dexdomain.MustDecimal(record.ValuationUSD))
		totalNetPnL = totalNetPnL.Add(dexdomain.MustDecimal(record.NetPnLUSD))
		exitDecision := buildShadowExitDecision(pos, record, now)
		if exitDecision.WouldExit {
			exitSignals++
		}
		exitDecisions = append(exitDecisions, exitDecision)
	}

	if err := app.persistShadowPositionMarks(ctx, provider.DB(), records); err != nil {
		app.logger.Warn("shadow position mark persist failed", zap.Error(err))
		return
	}
	if err := app.persistShadowExitDecisions(ctx, provider.DB(), exitDecisions); err != nil {
		app.logger.Warn("shadow exit decision persist failed", zap.Error(err))
		return
	}
	if err := app.recordShadowExitActions(ctx, provider.DB(), exitDecisions); err != nil {
		app.logger.Warn("shadow exit action persist failed", zap.Error(err))
		return
	}
	if err := app.reconcileBuiltShadowExits(ctx, provider.DB()); err != nil {
		app.logger.Warn("shadow exit reconciliation failed", zap.Error(err))
		return
	}
	if err := app.backfillClosedShadowPositionMarks(ctx, provider.DB()); err != nil {
		app.logger.Warn("closed shadow mark backfill failed", zap.Error(err))
		return
	}

	valuationFloat, _ := totalValuation.Float64()
	netPnLFloat, _ := totalNetPnL.Float64()
	metrics.RecordShadowPositionMarks(len(records), valuationFloat, netPnLFloat)
	metrics.RecordShadowExitSignals(exitSignals)
	metrics.RecordPnL(totalNetPnL)
}

func (app *App) listActiveShadowPositions(ctx context.Context, db *sql.DB) ([]activeShadowPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, pool_id, chain, status, COALESCE(tier, ''), amount_usd, tick_lower, tick_upper, opened_at
		FROM positions
		WHERE status IN ('intended', 'opening', 'open')
		ORDER BY opened_at DESC
	`)
	if err != nil {
		return nil, fmt.Errorf("query active positions: %w", err)
	}
	defer rows.Close()

	var positions []activeShadowPosition
	for rows.Next() {
		var row activeShadowPosition
		var chainInt int
		var tier string
		var amountUSD string
		if err := rows.Scan(&row.ID, &row.PoolID, &chainInt, &row.Status, &tier, &amountUSD, &row.TickLower, &row.TickUpper, &row.OpenedAt); err != nil {
			return nil, fmt.Errorf("scan active position: %w", err)
		}
		row.Chain = chainIntToDomain(chainInt)
		if parsedTier, err := dexdomain.ParseTier(tier); err == nil {
			row.Tier = parsedTier
		}
		row.AmountUSD = dexdomain.MustDecimal(amountUSD)
		positions = append(positions, row)
	}
	return positions, rows.Err()
}

func (app *App) buildPositionMarkRecord(ctx context.Context, pos activeShadowPosition, now time.Time) (shadowPositionMarkRecord, error) {
	return app.buildPositionMarkRecordAt(ctx, pos, string(pos.Status), now)
}

func (app *App) buildPositionMarkRecordAt(ctx context.Context, pos activeShadowPosition, status string, asOf time.Time) (shadowPositionMarkRecord, error) {
	meta, source, err := app.datasource.GetPoolMetadataWithSource(ctx, pos.Chain, pos.PoolID)
	if err != nil {
		return shadowPositionMarkRecord{}, err
	}
	if meta == nil {
		return shadowPositionMarkRecord{}, fmt.Errorf("no pool metadata for %s", pos.PoolID)
	}

	holdMinutes := int64(0)
	if pos.OpenedAt > 0 {
		holdMinutes = int64(asOf.Sub(time.Unix(pos.OpenedAt, 0)).Minutes())
		if holdMinutes < 0 {
			holdMinutes = 0
		}
	}

	holdDays := dexdomain.NewDecimalFromFloat(float64(max64(holdMinutes, 1)) / 1440.0)
	tvl := meta.TVLUSD
	if tvl.IsZero() {
		tvl = pos.AmountUSD
	}
	sharePct := pos.AmountUSD.Div(tvl)
	maxShare := dexdomain.MustDecimal("0.20")
	if sharePct.GreaterThan(maxShare) {
		sharePct = maxShare
	}

	effectiveFeeBPS := meta.FeeBPS
	if effectiveFeeBPS == 0 {
		effectiveFeeBPS = 30
	}
	estimatedFeeUSD := pnl.AccrueFeesFromVolume(meta.Vol24h, effectiveFeeBPS).Mul(sharePct).Mul(holdDays)
	priceChangePct, estimatedILUSD := app.estimateShadowIL(ctx, pos, meta, holdMinutes, asOf)
	valuationUSD := pos.AmountUSD.Add(estimatedFeeUSD).Add(estimatedILUSD)
	netPnLUSD := estimatedFeeUSD.Add(estimatedILUSD)

	return shadowPositionMarkRecord{
		MarkTime:       asOf.Unix(),
		PositionID:     pos.ID,
		PoolID:         pos.PoolID,
		Chain:          string(pos.Chain),
		Status:         status,
		Tier:           string(pos.Tier),
		AmountUSD:      pos.AmountUSD.String(),
		Source:         source,
		HoldMinutes:    holdMinutes,
		ValuationUSD:   valuationUSD.String(),
		FeeUSD:         estimatedFeeUSD.String(),
		ILUSD:          estimatedILUSD.String(),
		NetPnLUSD:      netPnLUSD.String(),
		CurrentTVLUSD:  meta.TVLUSD.String(),
		CurrentVol24h:  meta.Vol24h.String(),
		PriceChangePct: priceChangePct.String(),
		CreatedAt:      time.Now().UnixMilli(),
	}, nil
}

func (app *App) estimateShadowIL(ctx context.Context, pos activeShadowPosition, meta *ports.PoolDiscovery, holdMinutes int64, now time.Time) (dexdomain.Decimal, dexdomain.Decimal) {
	historical, ok := any(app.datasource).(ports.HistoricalDatasource)
	if ok {
		from := now.Add(-24 * time.Hour)
		if pos.OpenedAt > 0 {
			from = time.Unix(pos.OpenedAt, 0)
		}
		history, err := historical.GetPriceHistory(ctx, pos.Chain, pos.PoolID, from, now, shadowPriceResolution(now.Sub(from)))
		if err == nil && len(history) > 0 {
			sort.Slice(history, func(i, j int) bool {
				return history[i].Timestamp.Before(history[j].Timestamp)
			})

			entryPrice := openingPrice(history[0])
			currentPrice := closingPrice(history[len(history)-1])
			if !entryPrice.IsZero() && !currentPrice.IsZero() {
				historyChangePct, historyILUSD := realizeShadowIL(pos, entryPrice, currentPrice)
				if !historyChangePct.IsZero() || meta == nil || meta.PriceUSD.IsZero() || meta.PriceChange24hPct.IsZero() {
					return historyChangePct, historyILUSD
				}
			}
		}
	}

	if meta == nil || meta.PriceUSD.IsZero() || meta.PriceChange24hPct.IsZero() {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}

	scale := dexdomain.NewDecimalFromFloat(1)
	if holdMinutes > 0 && holdMinutes < 1440 {
		scale = dexdomain.NewDecimalFromFloat(float64(holdMinutes) / 1440.0)
		if scale.LessThan(dexdomain.MustDecimal("0.05")) {
			scale = dexdomain.MustDecimal("0.05")
		}
	}
	priceChangePct := meta.PriceChange24hPct.Mul(scale)
	denom := dexdomain.MustDecimal("1").Add(priceChangePct)
	if denom.LessThanOrEqual(dexdomain.ZeroDecimal()) {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}
	currentPrice := meta.PriceUSD
	entryPrice := currentPrice.Div(denom)
	if entryPrice.IsZero() || currentPrice.IsZero() {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}
	return realizeShadowIL(pos, entryPrice, currentPrice)
}

func realizeShadowIL(pos activeShadowPosition, entryPrice, currentPrice dexdomain.Decimal) (dexdomain.Decimal, dexdomain.Decimal) {
	priceChangePct := currentPrice.Div(entryPrice).Sub(dexdomain.MustDecimal("1"))
	position := dexdomain.Position{
		ID:        pos.ID,
		PoolID:    pos.PoolID,
		Chain:     pos.Chain,
		Status:    pos.Status,
		AmountUSD: pos.AmountUSD,
		TickLower: pos.TickLower,
		TickUpper: pos.TickUpper,
		OpenedAt:  pos.OpenedAt,
	}
	ilFraction, err := pnl.RealizeIL(position, entryPrice, currentPrice)
	if err != nil {
		return priceChangePct, dexdomain.ZeroDecimal()
	}
	return priceChangePct, pos.AmountUSD.Mul(ilFraction)
}

func (app *App) persistShadowPositionMarks(ctx context.Context, db *sql.DB, records []shadowPositionMarkRecord) error {
	if len(records) == 0 {
		return nil
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin position mark tx: %w", err)
	}
	defer tx.Rollback()

	for _, record := range records {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO shadow_position_marks (
				mark_time, position_id, pool_id, chain, status, tier, amount_usd, source,
				hold_minutes, valuation_usd, fee_usd, il_usd, net_pnl_usd,
				current_tvl_usd, current_vol24h_usd, price_change_pct, created_at
			) VALUES (
				$1, $2, $3, $4, $5, $6, $7, $8,
				$9, $10, $11, $12, $13,
				$14, $15, $16, $17
			)
		`,
			record.MarkTime,
			record.PositionID,
			record.PoolID,
			record.Chain,
			record.Status,
			record.Tier,
			record.AmountUSD,
			record.Source,
			record.HoldMinutes,
			record.ValuationUSD,
			record.FeeUSD,
			record.ILUSD,
			record.NetPnLUSD,
			record.CurrentTVLUSD,
			record.CurrentVol24h,
			record.PriceChangePct,
			record.CreatedAt,
		)
		if err != nil {
			return fmt.Errorf("insert position mark for %s: %w", record.PositionID, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit position mark tx: %w", err)
	}
	return nil
}

func (app *App) backfillClosedShadowPositionMarks(ctx context.Context, db *sql.DB) error {
	positions, err := app.listClosedShadowPositionsForBackfill(ctx, db)
	if err != nil {
		return err
	}
	if len(positions) == 0 {
		return nil
	}

	records := make([]shadowPositionMarkRecord, 0, len(positions))
	for _, pos := range positions {
		if pos.ClosedAt <= 0 {
			continue
		}
		record, err := app.buildPositionMarkRecordAt(ctx, pos, string(dexdomain.StatusClosed), time.Unix(pos.ClosedAt, 0))
		if err != nil {
			app.logger.Warn("closed shadow mark backfill skipped",
				zap.String("position_id", pos.ID),
				zap.Error(err))
			continue
		}
		records = append(records, record)
	}
	if len(records) == 0 {
		return nil
	}
	return app.persistShadowPositionMarks(ctx, db, records)
}

func (app *App) listClosedShadowPositionsForBackfill(ctx context.Context, db *sql.DB) ([]activeShadowPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT p.id, p.pool_id, p.chain, p.status, COALESCE(p.tier, ''), p.amount_usd, p.tick_lower, p.tick_upper, p.opened_at, COALESCE(p.closed_at, 0)
		FROM positions p
		LEFT JOIN (
			SELECT DISTINCT ON (position_id)
				position_id, status, mark_time
			FROM shadow_position_marks
			ORDER BY position_id, mark_time DESC
		) m ON m.position_id = p.id
		WHERE p.status = 'closed'
		  AND p.closed_at > 0
		  AND (
			m.position_id IS NULL
			OR m.status <> 'closed'
			OR m.mark_time < p.closed_at
		  )
		ORDER BY p.closed_at DESC
		LIMIT 20
	`)
	if err != nil {
		return nil, fmt.Errorf("query closed positions for backfill: %w", err)
	}
	defer rows.Close()

	positions := make([]activeShadowPosition, 0)
	for rows.Next() {
		var row activeShadowPosition
		var chainInt int
		var tier string
		var amountUSD string
		if err := rows.Scan(&row.ID, &row.PoolID, &chainInt, &row.Status, &tier, &amountUSD, &row.TickLower, &row.TickUpper, &row.OpenedAt, &row.ClosedAt); err != nil {
			return nil, fmt.Errorf("scan closed position for backfill: %w", err)
		}
		row.Chain = chainIntToDomain(chainInt)
		if parsedTier, err := dexdomain.ParseTier(tier); err == nil {
			row.Tier = parsedTier
		}
		row.AmountUSD = dexdomain.MustDecimal(amountUSD)
		positions = append(positions, row)
	}
	return positions, rows.Err()
}

func buildShadowExitDecision(pos activeShadowPosition, mark shadowPositionMarkRecord, now time.Time) shadowExitDecisionRecord {
	amountUSD := pos.AmountUSD
	currentTVLUSD := dexdomain.MustDecimal(mark.CurrentTVLUSD)
	netPnLUSD := dexdomain.MustDecimal(mark.NetPnLUSD)
	ilUSD := dexdomain.MustDecimal(mark.ILUSD)
	priceChangePct := dexdomain.MustDecimal(mark.PriceChangePct)
	thresholds := dexdomain.TierThresholdsFor(pos.Tier)

	wouldExit := false
	reason := "hold: no current exit condition met"
	action := "hold"

	ilPct := dexdomain.ZeroDecimal()
	if !amountUSD.IsZero() {
		ilPct = ilUSD.Abs().Div(amountUSD)
	}

	minHoldMinutes := thresholds.MinHoldHours.Mul(dexdomain.NewDecimalFromInt(60)).IntPart()
	tvlFloor := maxDecimal(dexdomain.MustDecimal("10000"), amountUSD.Mul(dexdomain.MustDecimal("5")))

	switch {
	case !amountUSD.IsZero() && ilPct.GreaterThan(thresholds.ILStopPct):
		wouldExit = true
		reason = fmt.Sprintf("IL breach: %.2f%% > %.2f%%", ilPct.Mul(dexdomain.MustDecimal("100")), thresholds.ILStopPct.Mul(dexdomain.MustDecimal("100")))
		action = "shadow_close"
	case !currentTVLUSD.IsZero() && currentTVLUSD.LessThan(tvlFloor):
		wouldExit = true
		reason = fmt.Sprintf("TVL degraded: %s < floor %s", currentTVLUSD.String(), tvlFloor.String())
		action = "shadow_close"
	case mark.HoldMinutes >= minHoldMinutes && netPnLUSD.LessThanOrEqual(dexdomain.ZeroDecimal()):
		wouldExit = true
		reason = fmt.Sprintf("min hold met (%dm) and net pnl non-positive (%s)", minHoldMinutes, netPnLUSD.String())
		action = "shadow_close"
	case priceChangePct.Abs().GreaterThan(thresholds.ILStopPct.Mul(dexdomain.MustDecimal("3"))):
		wouldExit = true
		reason = fmt.Sprintf("price moved %.2f%% which exceeds watch band %.2f%%", priceChangePct.Abs().Mul(dexdomain.MustDecimal("100")), thresholds.ILStopPct.Mul(dexdomain.MustDecimal("300")))
		action = "shadow_review"
	}

	return shadowExitDecisionRecord{
		DecisionTime:   now.Unix(),
		PositionID:     pos.ID,
		PoolID:         pos.PoolID,
		Chain:          string(pos.Chain),
		Status:         string(pos.Status),
		Tier:           string(pos.Tier),
		AmountUSD:      amountUSD.String(),
		HoldMinutes:    mark.HoldMinutes,
		CurrentTVLUSD:  mark.CurrentTVLUSD,
		NetPnLUSD:      mark.NetPnLUSD,
		ILUSD:          mark.ILUSD,
		PriceChangePct: mark.PriceChangePct,
		WouldExit:      wouldExit,
		Reason:         reason,
		Action:         action,
		CreatedAt:      now.UnixMilli(),
	}
}

func (app *App) persistShadowExitDecisions(ctx context.Context, db *sql.DB, records []shadowExitDecisionRecord) error {
	if len(records) == 0 {
		return nil
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin exit decision tx: %w", err)
	}
	defer tx.Rollback()

	for _, record := range records {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO shadow_exit_decisions (
				decision_time, position_id, pool_id, chain, status, tier,
				amount_usd, hold_minutes, current_tvl_usd, net_pnl_usd,
				il_usd, price_change_pct, would_exit, reason, action, created_at
			) VALUES (
				$1, $2, $3, $4, $5, $6,
				$7, $8, $9, $10,
				$11, $12, $13, $14, $15, $16
			)
		`,
			record.DecisionTime,
			record.PositionID,
			record.PoolID,
			record.Chain,
			record.Status,
			record.Tier,
			record.AmountUSD,
			record.HoldMinutes,
			record.CurrentTVLUSD,
			record.NetPnLUSD,
			record.ILUSD,
			record.PriceChangePct,
			record.WouldExit,
			record.Reason,
			record.Action,
			record.CreatedAt,
		)
		if err != nil {
			return fmt.Errorf("insert exit decision for %s: %w", record.PositionID, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit exit decision tx: %w", err)
	}
	return nil
}

func (app *App) recordShadowExitActions(ctx context.Context, db *sql.DB, records []shadowExitDecisionRecord) error {
	if len(records) == 0 {
		return nil
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin exit action tx: %w", err)
	}
	defer tx.Rollback()

	for _, record := range records {
		if !record.WouldExit || record.Action != "shadow_close" {
			continue
		}
		existingTxHash, exists, err := recentEquivalentExitAction(ctx, tx, record)
		if err != nil {
			return fmt.Errorf("check exit action dedupe for %s: %w", record.PositionID, err)
		}
		if exists {
			if err := app.finalizeShadowExitAction(ctx, tx, record, existingTxHash); err != nil {
				return err
			}
			continue
		}

		txHash := shadowID("exit-tx", record.PositionID, record.DecisionTime)

		_, err = tx.ExecContext(ctx, `
			INSERT INTO shadow_exit_actions (
				decision_time, position_id, pool_id, chain, reason, action, tx_hash, tx_status, created_at
			) VALUES (
				$1, $2, $3, $4, $5, $6, $7, $8, $9
			)
		`,
			record.DecisionTime,
			record.PositionID,
			record.PoolID,
			record.Chain,
			record.Reason,
			record.Action,
			txHash,
			string(dexdomain.TxConfirmed),
			time.Now().UnixMilli(),
		)
		if err != nil {
			return fmt.Errorf("insert exit action for %s: %w", record.PositionID, err)
		}
		if err := app.finalizeShadowExitAction(ctx, tx, record, txHash); err != nil {
			return err
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit exit action tx: %w", err)
	}
	return nil
}

func recentEquivalentExitAction(ctx context.Context, tx *sql.Tx, record shadowExitDecisionRecord) (string, bool, error) {
	cutoff := record.DecisionTime - 3600
	var txHash string
	err := tx.QueryRowContext(ctx, `
		SELECT tx_hash
		FROM shadow_exit_actions
		WHERE position_id = $1
		  AND action = $2
		  AND reason = $3
		  AND decision_time >= $4
		ORDER BY decision_time DESC, id DESC
		LIMIT 1
	`, record.PositionID, record.Action, record.Reason, cutoff).Scan(&txHash)
	if err == sql.ErrNoRows {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return txHash, true, nil
}

func (app *App) finalizeShadowExitAction(ctx context.Context, tx *sql.Tx, record shadowExitDecisionRecord, txHash string) error {
	txStatus := dexdomain.TxConfirmed
	exitTx := dexdomain.SignedTx{
		UnsignedTx: dexdomain.UnsignedTx{
			ID:       txHash,
			Chain:    dexdomain.ChainID(record.Chain),
			From:     zeroEVMAddress(),
			To:       parseAddressOrZero(record.PoolID),
			Value:    dexdomain.ZeroDecimal(),
			Deadline: record.DecisionTime + 300,
			MinOut:   dexdomain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: txStatus,
	}
	if err := app.store.TxRepo().UpsertTx(ctx, exitTx); err != nil {
		return fmt.Errorf("upsert shadow exit tx for %s: %w", record.PositionID, err)
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE shadow_exit_actions
		SET tx_status = $1
		WHERE position_id = $2
		  AND tx_hash = $3
	`, string(txStatus), record.PositionID, txHash); err != nil {
		return fmt.Errorf("update exit action status for %s: %w", record.PositionID, err)
	}
	if err := app.store.PositionRepo().UpdateStatus(ctx, record.PositionID, dexdomain.StatusClosed); err != nil {
		return fmt.Errorf("close shadow position %s: %w", record.PositionID, err)
	}
	return nil
}

func openingPrice(point ports.HistoricalPrice) dexdomain.Decimal {
	for _, candidate := range []dexdomain.Decimal{point.Price0, point.Price1} {
		if !candidate.IsZero() {
			return candidate
		}
	}
	return dexdomain.ZeroDecimal()
}

func closingPrice(point ports.HistoricalPrice) dexdomain.Decimal {
	for _, candidate := range []dexdomain.Decimal{point.Price1, point.Price0} {
		if !candidate.IsZero() {
			return candidate
		}
	}
	return dexdomain.ZeroDecimal()
}

func shadowPriceResolution(window time.Duration) time.Duration {
	switch {
	case window <= 0:
		return time.Hour
	case window <= 12*time.Hour:
		return time.Minute
	default:
		return time.Hour
	}
}

func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func maxDecimal(a, b dexdomain.Decimal) dexdomain.Decimal {
	if a.GreaterThan(b) {
		return a
	}
	return b
}

func chainIntToDomain(value int) dexdomain.ChainID {
	switch value {
	case 2:
		return dexdomain.ChainSolana
	default:
		return dexdomain.ChainBase
	}
}
