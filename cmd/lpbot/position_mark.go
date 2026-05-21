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
	AmountUSD dexdomain.Decimal
	TickLower int64
	TickUpper int64
	OpenedAt  int64
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
	`)
	if err != nil {
		return fmt.Errorf("ensure shadow_position_marks table: %w", err)
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
	totalValuation := dexdomain.ZeroDecimal()
	totalNetPnL := dexdomain.ZeroDecimal()

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
	}

	if err := app.persistShadowPositionMarks(ctx, provider.DB(), records); err != nil {
		app.logger.Warn("shadow position mark persist failed", zap.Error(err))
		return
	}

	valuationFloat, _ := totalValuation.Float64()
	netPnLFloat, _ := totalNetPnL.Float64()
	metrics.RecordShadowPositionMarks(len(records), valuationFloat, netPnLFloat)
	metrics.RecordPnL(totalNetPnL)
}

func (app *App) listActiveShadowPositions(ctx context.Context, db *sql.DB) ([]activeShadowPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, pool_id, chain, status, amount_usd, tick_lower, tick_upper, opened_at
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
		var amountUSD string
		if err := rows.Scan(&row.ID, &row.PoolID, &chainInt, &row.Status, &amountUSD, &row.TickLower, &row.TickUpper, &row.OpenedAt); err != nil {
			return nil, fmt.Errorf("scan active position: %w", err)
		}
		row.Chain = chainIntToDomain(chainInt)
		row.AmountUSD = dexdomain.MustDecimal(amountUSD)
		positions = append(positions, row)
	}
	return positions, rows.Err()
}

func (app *App) buildPositionMarkRecord(ctx context.Context, pos activeShadowPosition, now time.Time) (shadowPositionMarkRecord, error) {
	meta, source, err := app.datasource.GetPoolMetadataWithSource(ctx, pos.Chain, pos.PoolID)
	if err != nil {
		return shadowPositionMarkRecord{}, err
	}
	if meta == nil {
		return shadowPositionMarkRecord{}, fmt.Errorf("no pool metadata for %s", pos.PoolID)
	}

	holdMinutes := int64(0)
	if pos.OpenedAt > 0 {
		holdMinutes = int64(now.Sub(time.Unix(pos.OpenedAt, 0)).Minutes())
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

	estimatedFeeUSD := pnl.AccrueFeesFromVolume(meta.Vol24h, meta.FeeBPS).Mul(sharePct).Mul(holdDays)
	priceChangePct, estimatedILUSD := app.estimateShadowIL(ctx, pos, now)
	valuationUSD := pos.AmountUSD.Add(estimatedFeeUSD).Add(estimatedILUSD)
	netPnLUSD := estimatedFeeUSD.Add(estimatedILUSD)

	return shadowPositionMarkRecord{
		MarkTime:       now.Unix(),
		PositionID:     pos.ID,
		PoolID:         pos.PoolID,
		Chain:          string(pos.Chain),
		Status:         string(pos.Status),
		Source:         source,
		HoldMinutes:    holdMinutes,
		ValuationUSD:   valuationUSD.String(),
		FeeUSD:         estimatedFeeUSD.String(),
		ILUSD:          estimatedILUSD.String(),
		NetPnLUSD:      netPnLUSD.String(),
		CurrentTVLUSD:  meta.TVLUSD.String(),
		CurrentVol24h:  meta.Vol24h.String(),
		PriceChangePct: priceChangePct.String(),
		CreatedAt:      now.UnixMilli(),
	}, nil
}

func (app *App) estimateShadowIL(ctx context.Context, pos activeShadowPosition, now time.Time) (dexdomain.Decimal, dexdomain.Decimal) {
	historical, ok := any(app.datasource).(ports.HistoricalDatasource)
	if !ok {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}

	from := now.Add(-24 * time.Hour)
	if pos.OpenedAt > 0 {
		from = time.Unix(pos.OpenedAt, 0)
	}
	history, err := historical.GetPriceHistory(ctx, pos.Chain, pos.PoolID, from, now, time.Hour)
	if err != nil || len(history) == 0 {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}

	sort.Slice(history, func(i, j int) bool {
		return history[i].Timestamp.Before(history[j].Timestamp)
	})

	entryPrice := firstNonZeroPrice(history[0])
	currentPrice := firstNonZeroPrice(history[len(history)-1])
	if entryPrice.IsZero() || currentPrice.IsZero() {
		return dexdomain.ZeroDecimal(), dexdomain.ZeroDecimal()
	}

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
				mark_time, position_id, pool_id, chain, status, source,
				hold_minutes, valuation_usd, fee_usd, il_usd, net_pnl_usd,
				current_tvl_usd, current_vol24h_usd, price_change_pct, created_at
			) VALUES (
				$1, $2, $3, $4, $5, $6,
				$7, $8, $9, $10, $11,
				$12, $13, $14, $15
			)
		`,
			record.MarkTime,
			record.PositionID,
			record.PoolID,
			record.Chain,
			record.Status,
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

func firstNonZeroPrice(point ports.HistoricalPrice) dexdomain.Decimal {
	for _, candidate := range []dexdomain.Decimal{point.Price1, point.Price0} {
		if !candidate.IsZero() {
			return candidate
		}
	}
	return dexdomain.ZeroDecimal()
}

func max64(a, b int64) int64 {
	if a > b {
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
