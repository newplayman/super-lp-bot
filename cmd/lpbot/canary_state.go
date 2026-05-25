package main

import (
	"context"
	"database/sql"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

type canaryEvent struct {
	Chain           string
	Command         string
	Stage           string
	Status          string
	PositionID      string
	PoolID          string
	Wallet          string
	TokenID         string
	TxHash          string
	AmountUSD       string
	RequiredUSDCRaw string
	RequiredWETHRaw string
	InputMint       string
	OutputMint      string
	InputAmountRaw  string
	OutputAmountRaw string
	SOLBalanceRaw   string
	USDCBalanceRaw  string
	GasEstimate     uint64
	Message         string
	ErrorMsg        string
	CreatedAt       int64
}

type canaryEventWriter struct {
	store interface {
		DB() *sql.DB
		Close() error
	}
	db *sql.DB
}

type canaryStrategyApproval struct {
	TickTime       int64
	AgeSeconds     int64
	ScoreTotal     float64
	FinalAction    string
	PipelineStage  string
	PipelineReason string
}

type canaryOpenEconomics struct {
	RequestedAmountUSD   domain.Decimal
	ETHPriceUSD          domain.Decimal
	GasPriceGwei         domain.Decimal
	EstimatedGasUSD      domain.Decimal
	RecentAvgGrossUSD    domain.Decimal
	RecentAvgGrossPerUSD domain.Decimal
	ShadowAvgGrossUSD    domain.Decimal
	ShadowAvgGrossPerUSD domain.Decimal
	EffectiveGrossUSD    domain.Decimal
	EffectiveGrossPerUSD domain.Decimal
	ProjectedGrossUSD    domain.Decimal
	RecentWinRate        domain.Decimal
	ShadowWinRate        domain.Decimal
	CoverageRatio        domain.Decimal
	RecentRounds         int64
	ShadowRounds         int64
	ProjectionSource     string
}

const (
	canaryShadowApprovalMaxAge     = 3 * time.Hour
	canaryShadowApprovalStaleGrace = 12 * time.Hour
	canaryRecentRoundWindow        = 6
	canaryGrossToGasCoverageMin    = 1.5
	canaryShadowBlendWeight        = 0.35
	canaryShadowBlendHaircut       = 0.60
	canaryShadowOnlyHaircut        = 0.50
	canaryShadowMinSizeRatio       = 0.50
	canaryShadowMaxSizeRatio       = 3.00
)

func newCanaryEventWriter(ctx context.Context, cfg *config.Config) (*canaryEventWriter, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config is nil")
	}
	dsn := strings.TrimSpace(cfg.Store.PostgresDSN)
	if dsn == "" {
		return nil, fmt.Errorf("store.postgres_dsn is empty; cannot persist canary state")
	}
	store, err := postgres.NewFromDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("open postgres for canary state: %w", err)
	}
	writer := &canaryEventWriter{store: store, db: store.DB()}
	if err := writer.ensure(ctx); err != nil {
		_ = writer.Close()
		return nil, err
	}
	return writer, nil
}

func (w *canaryEventWriter) Close() error {
	if w == nil || w.store == nil {
		return nil
	}
	return w.store.Close()
}

func (w *canaryEventWriter) ensure(ctx context.Context) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	var exists bool
	if err := w.db.QueryRowContext(ctx, `SELECT to_regclass('public.canary_events') IS NOT NULL`).Scan(&exists); err != nil {
		return fmt.Errorf("check canary_events table: %w", err)
	}
	if !exists {
		return fmt.Errorf("canary_events table missing; apply migrations/postgres/000002_canary_state.sql")
	}
	var columnCount int
	if err := w.db.QueryRowContext(ctx, `
		SELECT count(*)
		FROM information_schema.columns
		WHERE table_schema = 'public'
		  AND table_name = 'canary_events'
		  AND column_name IN (
			'chain', 'input_mint', 'output_mint',
			'input_amount_raw', 'output_amount_raw',
			'sol_balance_raw', 'usdc_balance_raw'
		  )
	`).Scan(&columnCount); err != nil {
		return fmt.Errorf("check canary_events columns: %w", err)
	}
	if columnCount != 7 {
		return fmt.Errorf("canary_events schema is outdated; apply migrations/postgres/000002_canary_state.sql")
	}
	return nil
}

func (w *canaryEventWriter) Record(ctx context.Context, event canaryEvent) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	now := time.Now().Unix()
	if event.CreatedAt <= 0 {
		event.CreatedAt = now
	}
	if event.Status == "" {
		event.Status = "ok"
	}
	if strings.TrimSpace(event.Chain) == "" {
		event.Chain = string(domain.ChainBase)
	}
	idInput := fmt.Sprintf("%s:%s:%s:%s:%d", event.Command, event.Stage, event.PositionID, event.TxHash, time.Now().UnixNano())
	id := shadowID("canary-event", idInput, time.Now().UnixNano())
	_, err := w.db.ExecContext(ctx, `
		INSERT INTO canary_events (
			id, chain, command, stage, status, position_id, pool_id, wallet, token_id, tx_hash,
			amount_usd, required_usdc_raw, required_weth_raw, input_mint, output_mint,
			input_amount_raw, output_amount_raw, sol_balance_raw, usdc_balance_raw,
			gas_estimate, message, error_msg, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
	`,
		id,
		event.Chain,
		event.Command,
		event.Stage,
		event.Status,
		event.PositionID,
		event.PoolID,
		event.Wallet,
		event.TokenID,
		event.TxHash,
		event.AmountUSD,
		event.RequiredUSDCRaw,
		event.RequiredWETHRaw,
		event.InputMint,
		event.OutputMint,
		event.InputAmountRaw,
		event.OutputAmountRaw,
		event.SOLBalanceRaw,
		event.USDCBalanceRaw,
		event.GasEstimate,
		event.Message,
		event.ErrorMsg,
		event.CreatedAt,
		now,
	)
	if err != nil {
		return fmt.Errorf("insert canary event: %w", err)
	}
	return nil
}

func (w *canaryEventWriter) RecordSignedTx(ctx context.Context, signed domain.SignedTx, status domain.TxStatus) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	signed.Status = status
	return postgres.NewTxRepo(w.db).UpsertTx(ctx, signed)
}

func (w *canaryEventWriter) ReserveOpeningPosition(ctx context.Context, pos *domain.Position) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	if pos == nil {
		return fmt.Errorf("position is nil")
	}
	if pos.ID == "" {
		return fmt.Errorf("position id is empty")
	}
	if pos.Status == "" {
		pos.Status = domain.StatusIntended
	}
	return postgres.NewPositionRepo(w.db).Save(ctx, pos)
}

func (w *canaryEventWriter) UpdatePositionStatus(ctx context.Context, positionID string, status domain.PositionStatus) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	return postgres.NewPositionRepo(w.db).UpdateStatus(ctx, positionID, status)
}

func (w *canaryEventWriter) AttachOpenTxHash(ctx context.Context, positionID string, txHash string) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	return attachOpenTxHashToPosition(ctx, postgres.NewPositionRepo(w.db), positionID, txHash)
}

func (w *canaryEventWriter) SaveOpeningPosition(ctx context.Context, positionID string, pool domain.Pool, amountUSD domain.Decimal, openedAt int64) error {
	if w == nil || w.db == nil {
		return fmt.Errorf("canary state writer is not initialized")
	}
	if positionID == "" {
		return fmt.Errorf("position id is empty")
	}
	pos := &domain.Position{
		ID:        positionID,
		PoolID:    pool.ID,
		Chain:     pool.Chain,
		Status:    domain.StatusOpening,
		Tier:      pool.Tier_,
		AmountUSD: amountUSD,
		TickLower: int64(pool.Tick),
		TickUpper: int64(pool.Tick),
		OpenedAt:  openedAt,
	}
	return postgres.NewPositionRepo(w.db).Save(ctx, pos)
}

func (w *canaryEventWriter) RequireRecentShadowApproval(ctx context.Context, poolID string, maxAge time.Duration) (canaryStrategyApproval, error) {
	if w == nil || w.db == nil {
		return canaryStrategyApproval{}, fmt.Errorf("canary state writer is not initialized")
	}
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return canaryStrategyApproval{}, fmt.Errorf("pool id is empty")
	}
	if maxAge <= 0 {
		maxAge = canaryShadowApprovalMaxAge
	}

	var row struct {
		TickTime       int64
		ScoreTotal     float64
		Selected       bool
		IntentOpen     bool
		ChainStage     string
		PipelineStage  string
		PipelineOK     bool
		PipelineReason string
		FinalAction    string
	}
	err := w.db.QueryRowContext(ctx, `
		SELECT tick_time, score_total, selected, intent_open, chain_stage,
		       pipeline_stage, pipeline_ok, pipeline_reason, final_action
		FROM shadow_decision_trace
		WHERE lower(pool_id) = lower($1)
		ORDER BY tick_time DESC
		LIMIT 1
	`, poolID).Scan(
		&row.TickTime,
		&row.ScoreTotal,
		&row.Selected,
		&row.IntentOpen,
		&row.ChainStage,
		&row.PipelineStage,
		&row.PipelineOK,
		&row.PipelineReason,
		&row.FinalAction,
	)
	if err == sql.ErrNoRows {
		return canaryStrategyApproval{}, fmt.Errorf("canary quality gate blocked: no recent shadow decision for pool %s", poolID)
	}
	if err != nil {
		return canaryStrategyApproval{}, fmt.Errorf("read shadow decision for canary quality gate: %w", err)
	}

	ageSeconds := time.Now().Unix() - row.TickTime
	if ageSeconds < 0 {
		ageSeconds = 0
	}
	approval := canaryStrategyApproval{
		TickTime:       row.TickTime,
		AgeSeconds:     ageSeconds,
		ScoreTotal:     row.ScoreTotal,
		FinalAction:    row.FinalAction,
		PipelineStage:  row.PipelineStage,
		PipelineReason: row.PipelineReason,
	}
	age := time.Duration(ageSeconds) * time.Second
	if age > maxAge {
		staleGraceOK := age <= canaryShadowApprovalStaleGrace &&
			row.Selected &&
			row.IntentOpen &&
			row.ScoreTotal >= shadowOpenScoreThreshold &&
			(row.PipelineOK || row.FinalAction == "reuse_shadow_position")
		if !staleGraceOK {
			return approval, fmt.Errorf("canary quality gate blocked: latest shadow decision is stale age=%ds max=%s", ageSeconds, maxAge)
		}
		if approval.PipelineReason != "" {
			approval.PipelineReason += "; "
		}
		approval.PipelineReason += fmt.Sprintf("stale shadow approval accepted within grace window (%s)", canaryShadowApprovalStaleGrace)
	}
	if row.ScoreTotal < shadowOpenScoreThreshold {
		return approval, fmt.Errorf("canary quality gate blocked: score %.2f below threshold %.2f", row.ScoreTotal, shadowOpenScoreThreshold)
	}
	if !row.Selected || !row.IntentOpen || !row.PipelineOK {
		return approval, fmt.Errorf("canary quality gate blocked: selected=%t intent_open=%t pipeline_ok=%t stage=%s reason=%s", row.Selected, row.IntentOpen, row.PipelineOK, row.PipelineStage, row.PipelineReason)
	}
	if row.ChainStage != "chain_state_ok" && row.ChainStage != "chain_v3_validated" {
		return approval, fmt.Errorf("canary quality gate blocked: chain_stage=%s", row.ChainStage)
	}
	if row.FinalAction != "open_shadow_position" && row.FinalAction != "reuse_shadow_position" {
		return approval, fmt.Errorf("canary quality gate blocked: final_action=%s", row.FinalAction)
	}
	return approval, nil
}

func (w *canaryEventWriter) EvaluateCanaryOpenEconomics(ctx context.Context, pool domain.Pool, amountUSD domain.Decimal, mintGas uint64, provider *rpc.RoundRobinProvider) (canaryOpenEconomics, error) {
	if w == nil || w.db == nil {
		return canaryOpenEconomics{}, fmt.Errorf("canary state writer is not initialized")
	}
	if provider == nil {
		return canaryOpenEconomics{}, fmt.Errorf("rpc provider is not configured")
	}
	if mintGas == 0 {
		return canaryOpenEconomics{}, fmt.Errorf("mint gas estimate is zero")
	}

	ethPriceUSD, err := estimateBaseWETHPriceUSD(ctx, pool, provider)
	if err != nil {
		return canaryOpenEconomics{}, fmt.Errorf("estimate canary ETH/USD for quality gate: %w", err)
	}
	gasPriceWei, err := provider.SuggestGasPrice(ctx)
	if err != nil {
		return canaryOpenEconomics{}, fmt.Errorf("suggest gas price for canary quality gate: %w", err)
	}
	gasPriceGwei := decimalFromWei(gasPriceWei, 9)
	estimatedGasETH := decimalFromWei(new(big.Int).Mul(new(big.Int).SetUint64(mintGas), gasPriceWei), 18)
	estimatedGasUSD := estimatedGasETH.Mul(ethPriceUSD)
	if estimatedGasUSD.LessThanOrEqual(domain.ZeroDecimal()) {
		return canaryOpenEconomics{}, fmt.Errorf("canary quality gate blocked: estimated gas usd is zero")
	}

	var recentRounds int64
	var recentAvgGrossUSD, recentAvgGrossPerUSD, recentWinRate float64
	err = w.db.QueryRowContext(ctx, `
		WITH recent AS (
			SELECT
				(e.total_usd::numeric - p.amount_usd::numeric) AS gross_net_usd,
				NULLIF(p.amount_usd::numeric, 0) AS amount_usd
			FROM positions p
			JOIN canary_exit_preflights e ON e.token_id = p.token_id
			WHERE lower(p.pool_id) = lower($1)
			  AND p.status = 'closed'
			  AND COALESCE(e.status, '') = 'closed'
			ORDER BY COALESCE(p.closed_at, 0) DESC
			LIMIT $2
		)
		SELECT
			count(*),
			COALESCE(avg(gross_net_usd::double precision), 0),
			COALESCE(avg(CASE WHEN amount_usd IS NULL THEN 0 ELSE (gross_net_usd / amount_usd)::double precision END), 0),
			COALESCE(avg(CASE WHEN gross_net_usd > 0 THEN 1.0 ELSE 0.0 END), 0)
		FROM recent
	`, pool.ID, canaryRecentRoundWindow).Scan(&recentRounds, &recentAvgGrossUSD, &recentAvgGrossPerUSD, &recentWinRate)
	if err != nil {
		return canaryOpenEconomics{}, fmt.Errorf("read recent canary outcomes for quality gate: %w", err)
	}

	var shadowRounds int64
	var shadowAvgGrossUSD, shadowAvgGrossPerUSD, shadowWinRate float64
	shadowMinAmountUSD := amountUSD.Mul(domain.NewDecimalFromFloat(canaryShadowMinSizeRatio))
	shadowMaxAmountUSD := amountUSD.Mul(domain.NewDecimalFromFloat(canaryShadowMaxSizeRatio))
	err = w.db.QueryRowContext(ctx, `
		WITH latest AS (
			SELECT DISTINCT ON (position_id)
				position_id,
				mark_time,
				(COALESCE(amount_usd, '0'))::numeric AS amount_usd,
				((COALESCE(fee_usd, '0'))::numeric + (COALESCE(il_usd, '0'))::numeric) AS gross_net_usd
			FROM shadow_position_marks
			WHERE lower(pool_id) = lower($1)
			  AND status = 'closed'
			  AND position_id NOT LIKE 'shadow-canary-live-pos-%'
			  AND COALESCE(amount_usd, '0') <> '0'
			  AND (COALESCE(amount_usd, '0'))::numeric >= $3::numeric
			  AND (COALESCE(amount_usd, '0'))::numeric <= $4::numeric
			ORDER BY position_id, mark_time DESC, created_at DESC
		),
		recent AS (
			SELECT
				gross_net_usd,
				NULLIF(amount_usd, 0) AS amount_usd
			FROM latest
			ORDER BY mark_time DESC
			LIMIT $2
		)
		SELECT
			count(*),
			COALESCE(avg(gross_net_usd::double precision), 0),
			COALESCE(avg(CASE WHEN amount_usd IS NULL THEN 0 ELSE (gross_net_usd / amount_usd)::double precision END), 0),
			COALESCE(avg(CASE WHEN gross_net_usd > 0 THEN 1.0 ELSE 0.0 END), 0)
		FROM recent
	`, pool.ID, canaryRecentRoundWindow, shadowMinAmountUSD.String(), shadowMaxAmountUSD.String()).Scan(&shadowRounds, &shadowAvgGrossUSD, &shadowAvgGrossPerUSD, &shadowWinRate)
	if err != nil {
		return canaryOpenEconomics{}, fmt.Errorf("read recent shadow outcomes for quality gate: %w", err)
	}
	if recentRounds == 0 && shadowRounds == 0 {
		return canaryOpenEconomics{}, fmt.Errorf("canary quality gate blocked: no closed canary or shadow history for pool %s", pool.ID)
	}

	avgGross := domain.NewDecimalFromFloat(recentAvgGrossUSD)
	avgGrossPerUSD := domain.NewDecimalFromFloat(recentAvgGrossPerUSD)
	shadowGross := domain.NewDecimalFromFloat(shadowAvgGrossUSD)
	shadowGrossPerUSD := domain.NewDecimalFromFloat(shadowAvgGrossPerUSD)
	shadowGrossHaircut := domain.NewDecimalFromFloat(canaryShadowBlendHaircut)
	shadowOnlyHaircut := domain.NewDecimalFromFloat(canaryShadowOnlyHaircut)
	effectiveGross := avgGross
	effectiveGrossPerUSD := avgGrossPerUSD
	projectionSource := "canary_realized_only"
	switch {
	case recentRounds > 0 && shadowRounds > 0:
		canaryWeight := domain.NewDecimalFromFloat(float64(recentRounds))
		shadowWeight := domain.NewDecimalFromFloat(float64(shadowRounds)).Mul(domain.NewDecimalFromFloat(canaryShadowBlendWeight))
		totalWeight := canaryWeight.Add(shadowWeight)
		effectiveGross = avgGross.Mul(canaryWeight).
			Add(shadowGross.Mul(shadowGrossHaircut).Mul(shadowWeight)).
			Div(totalWeight)
		effectiveGrossPerUSD = avgGrossPerUSD.Mul(canaryWeight).
			Add(shadowGrossPerUSD.Mul(shadowGrossHaircut).Mul(shadowWeight)).
			Div(totalWeight)
		projectionSource = "canary_plus_shadow_haircut"
	case recentRounds == 0 && shadowRounds > 0:
		effectiveGross = shadowGross.Mul(shadowOnlyHaircut)
		effectiveGrossPerUSD = shadowGrossPerUSD.Mul(shadowOnlyHaircut)
		projectionSource = "shadow_only_haircut"
	}
	projectedGross := effectiveGrossPerUSD.Mul(amountUSD)
	winRate := domain.NewDecimalFromFloat(recentWinRate)
	shadowWin := domain.NewDecimalFromFloat(shadowWinRate)
	coverageRatio := projectedGross.Div(estimatedGasUSD)
	minCoverage := domain.NewDecimalFromFloat(canaryGrossToGasCoverageMin)
	if coverageRatio.LessThan(minCoverage) {
		return canaryOpenEconomics{
				RequestedAmountUSD:   amountUSD,
				ETHPriceUSD:          ethPriceUSD,
				GasPriceGwei:         gasPriceGwei,
				EstimatedGasUSD:      estimatedGasUSD,
				RecentAvgGrossUSD:    avgGross,
				RecentAvgGrossPerUSD: avgGrossPerUSD,
				ShadowAvgGrossUSD:    shadowGross,
				ShadowAvgGrossPerUSD: shadowGrossPerUSD,
				EffectiveGrossUSD:    effectiveGross,
				EffectiveGrossPerUSD: effectiveGrossPerUSD,
				ProjectedGrossUSD:    projectedGross,
				RecentWinRate:        winRate,
				ShadowWinRate:        shadowWin,
				CoverageRatio:        coverageRatio,
				RecentRounds:         recentRounds,
				ShadowRounds:         shadowRounds,
				ProjectionSource:     projectionSource,
			}, fmt.Errorf(
				"canary quality gate blocked: projected_gross_usd=%s < gas_usd=%s * coverage_min=%.2f (coverage=%s, source=%s, size_usd=%s, recent_avg_gross_usd=%s, recent_avg_gross_per_usd=%s, recent_rounds=%d, recent_win_rate=%s, shadow_avg_gross_usd=%s, shadow_avg_gross_per_usd=%s, shadow_rounds=%d, shadow_win_rate=%s, effective_gross_usd=%s, effective_gross_per_usd=%s, eth_price_usd=%s, gas_price_gwei=%s)",
				projectedGross.StringFixed(6),
				estimatedGasUSD.StringFixed(6),
				canaryGrossToGasCoverageMin,
				coverageRatio.StringFixed(4),
				projectionSource,
				amountUSD.StringFixed(2),
				avgGross.StringFixed(6),
				avgGrossPerUSD.StringFixed(6),
				recentRounds,
				winRate.StringFixed(4),
				shadowGross.StringFixed(6),
				shadowGrossPerUSD.StringFixed(6),
				shadowRounds,
				shadowWin.StringFixed(4),
				effectiveGross.StringFixed(6),
				effectiveGrossPerUSD.StringFixed(6),
				ethPriceUSD.StringFixed(4),
				gasPriceGwei.StringFixed(4),
			)
	}
	return canaryOpenEconomics{
		RequestedAmountUSD:   amountUSD,
		ETHPriceUSD:          ethPriceUSD,
		GasPriceGwei:         gasPriceGwei,
		EstimatedGasUSD:      estimatedGasUSD,
		RecentAvgGrossUSD:    avgGross,
		RecentAvgGrossPerUSD: avgGrossPerUSD,
		ShadowAvgGrossUSD:    shadowGross,
		ShadowAvgGrossPerUSD: shadowGrossPerUSD,
		EffectiveGrossUSD:    effectiveGross,
		EffectiveGrossPerUSD: effectiveGrossPerUSD,
		ProjectedGrossUSD:    projectedGross,
		RecentWinRate:        winRate,
		ShadowWinRate:        shadowWin,
		CoverageRatio:        coverageRatio,
		RecentRounds:         recentRounds,
		ShadowRounds:         shadowRounds,
		ProjectionSource:     projectionSource,
	}, nil
}

func estimateBaseWETHPriceUSD(ctx context.Context, pool domain.Pool, provider *rpc.RoundRobinProvider) (domain.Decimal, error) {
	queryCtx, cancel := context.WithTimeout(ctx, 6*time.Second)
	defer cancel()
	decimals0, err := tokenDecimals(queryCtx, provider, pool.Token0)
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	decimals1, err := tokenDecimals(queryCtx, provider, pool.Token1)
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	price0, price1, err := inferBaseTokenPricesUSD(pool, decimals0, decimals1)
	if err != nil {
		return domain.ZeroDecimal(), err
	}
	switch {
	case strings.EqualFold(pool.Token0.String(), baseWETHAddress):
		return price0, nil
	case strings.EqualFold(pool.Token1.String(), baseWETHAddress):
		return price1, nil
	default:
		return domain.ZeroDecimal(), fmt.Errorf("pool %s does not include base WETH", pool.ID)
	}
}

func decimalFromWei(value *big.Int, decimals int32) domain.Decimal {
	if value == nil || value.Sign() <= 0 {
		return domain.ZeroDecimal()
	}
	return domain.MustDecimal(value.String()).Div(domain.MustDecimal("1" + strings.Repeat("0", int(decimals))))
}
