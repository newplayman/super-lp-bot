package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
)

type shadowDecisionTraceRecord struct {
	TickTime        int64
	TraceID         string
	PoolID          string
	PoolKey         string
	Chain           string
	Protocol        string
	ScoreTotal      float64
	ScoreJSON       string
	Selected        bool
	SelectedRank    int
	SelectionReason string
	IntentOpen      bool
	IntentReason    string
	ChainStage      string
	ChainReason     string
	PipelineStage   string
	PipelineOK      bool
	PipelineReason  string
	FinalAction     string
	PositionID      string
	TxHash          string
	CreatedAt       int64
}

type shadowPipelineDecision struct {
	Stage       string
	OK          bool
	Reason      string
	ChainStage  string
	ChainReason string
	Action      string
	PositionID  string
	TxHash      string
}

func (app *App) ensureShadowDecisionTraceTable(ctx context.Context) error {
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return nil
	}

	_, err := provider.DB().ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS shadow_decision_trace (
			id BIGSERIAL PRIMARY KEY,
			tick_time BIGINT NOT NULL,
			trace_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			pool_key TEXT NOT NULL,
			chain TEXT NOT NULL,
			protocol TEXT NOT NULL,
			score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
			score_json TEXT NOT NULL,
			selected BOOLEAN NOT NULL DEFAULT FALSE,
			selected_rank INTEGER,
			selection_reason TEXT NOT NULL DEFAULT '',
			intent_open BOOLEAN NOT NULL DEFAULT FALSE,
			intent_reason TEXT NOT NULL DEFAULT '',
			chain_stage TEXT NOT NULL DEFAULT '',
			chain_reason TEXT NOT NULL DEFAULT '',
			pipeline_stage TEXT NOT NULL DEFAULT '',
			pipeline_ok BOOLEAN NOT NULL DEFAULT FALSE,
			pipeline_reason TEXT NOT NULL DEFAULT '',
			final_action TEXT NOT NULL DEFAULT 'skip',
			position_id TEXT,
			tx_hash TEXT,
			created_at BIGINT NOT NULL
		);

		CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_created_at
			ON shadow_decision_trace(created_at DESC);
		CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_tick_time
			ON shadow_decision_trace(tick_time DESC);
		CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_pool_id
			ON shadow_decision_trace(pool_id);
		ALTER TABLE shadow_decision_trace
			ADD COLUMN IF NOT EXISTS chain_stage TEXT NOT NULL DEFAULT '';
		ALTER TABLE shadow_decision_trace
			ADD COLUMN IF NOT EXISTS chain_reason TEXT NOT NULL DEFAULT '';
	`)
	if err != nil {
		return fmt.Errorf("ensure shadow_decision_trace table: %w", err)
	}
	return nil
}

func (app *App) persistShadowDecisionTraces(ctx context.Context, records []shadowDecisionTraceRecord) error {
	if len(records) == 0 {
		return nil
	}
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		return nil
	}

	tx, err := provider.DB().BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin decision trace tx: %w", err)
	}
	defer tx.Rollback()

	for _, record := range records {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO shadow_decision_trace (
				tick_time, trace_id, pool_id, pool_key, chain, protocol,
				score_total, score_json, selected, selected_rank, selection_reason,
				intent_open, intent_reason, chain_stage, chain_reason,
				pipeline_stage, pipeline_ok, pipeline_reason,
				final_action, position_id, tx_hash, created_at
			) VALUES (
				$1, $2, $3, $4, $5, $6,
				$7, $8, $9, $10, $11,
				$12, $13, $14, $15,
				$16, $17, $18,
				$19, $20, $21, $22
			)
		`,
			record.TickTime,
			record.TraceID,
			record.PoolID,
			record.PoolKey,
			record.Chain,
			record.Protocol,
			record.ScoreTotal,
			record.ScoreJSON,
			record.Selected,
			nullableInt(record.SelectedRank),
			record.SelectionReason,
			record.IntentOpen,
			record.IntentReason,
			record.ChainStage,
			record.ChainReason,
			record.PipelineStage,
			record.PipelineOK,
			record.PipelineReason,
			record.FinalAction,
			nullableString(record.PositionID),
			nullableString(record.TxHash),
			record.CreatedAt,
		)
		if err != nil {
			return fmt.Errorf("insert decision trace for %s: %w", record.PoolKey, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit decision trace tx: %w", err)
	}
	return nil
}

func (app *App) buildDecisionTraceRecord(pool domain.Pool, score domain.Score, tickTime int64) shadowDecisionTraceRecord {
	total := score.Total
	if total == 0 {
		total = score.ComputeTotal()
	}
	payload, err := json.Marshal(score)
	scoreJSON := "{}"
	if err == nil {
		scoreJSON = string(payload)
	}

	return shadowDecisionTraceRecord{
		TickTime:        tickTime,
		TraceID:         shadowID("trace", pool.Key(), tickTime),
		PoolID:          pool.ID,
		PoolKey:         pool.Key(),
		Chain:           string(pool.Chain),
		Protocol:        pool.Protocol,
		ScoreTotal:      total,
		ScoreJSON:       scoreJSON,
		SelectionReason: "not evaluated yet",
		FinalAction:     "skip",
		CreatedAt:       time.Now().UnixMilli(),
	}
}

func (app *App) evaluateShadowPipeline(ctx context.Context, pool domain.Pool) shadowPipelineDecision {
	if app.mainLoop == nil {
		return shadowPipelineDecision{
			Stage:  "pipeline_unavailable",
			Reason: "main loop not initialized",
			Action: "skip",
		}
	}

	blocked, err := app.mainLoop.RiskGate.IsBlocked(ctx)
	if err != nil {
		return shadowPipelineDecision{
			Stage:  "risk_gate_error",
			Reason: err.Error(),
			Action: "skip",
		}
	}
	if blocked {
		app.mainLoop.GetMetrics().IncRiskBlock()
		return shadowPipelineDecision{
			Stage:  "risk_blocked",
			Reason: "global risk gate is blocking new positions",
			Action: "skip",
		}
	}

	thresholds := domain.TierThresholdsFor(pool.Tier_)
	amount := thresholds.MaxPerPoolUSD
	if !app.mainLoop.AllocationManager.CheckAllocation(pool.Tier_, amount) {
		app.mainLoop.GetMetrics().IncAllocBlock()
		return shadowPipelineDecision{
			Stage:  "allocation_blocked",
			Reason: fmt.Sprintf("tier %s allocation limit rejected amount %s", pool.Tier_, amount.String()),
			Action: "skip",
		}
	}

	chainValidation := app.validatePoolOnChain(ctx, pool)
	if !chainValidation.OK {
		return shadowPipelineDecision{
			Stage:       chainValidation.Stage,
			Reason:      chainValidation.Reason,
			ChainStage:  chainValidation.Stage,
			ChainReason: chainValidation.Reason,
			Action:      "skip",
		}
	}

	if app.liveGate != nil {
		if err := app.liveGate.checkOpen(pool, amount); err != nil {
			return shadowPipelineDecision{
				Stage:       "live_gate_blocked",
				Reason:      err.Error(),
				ChainStage:  chainValidation.Stage,
				ChainReason: chainValidation.Reason,
				Action:      "skip",
			}
		}
	}

	sim, err := app.mainLoop.Simulator.Simulate(ctx, domain.UnsignedTx{}, domain.BlockRef{})
	if err != nil {
		app.mainLoop.GetMetrics().IncSimulateFail()
		return shadowPipelineDecision{
			Stage:       "simulation_error",
			Reason:      err.Error(),
			ChainStage:  chainValidation.Stage,
			ChainReason: chainValidation.Reason,
			Action:      "skip",
		}
	}
	if sim == nil || !sim.Success {
		app.mainLoop.GetMetrics().IncSimulateFail()
		reason := "simulation returned unsuccessful result"
		if sim != nil && sim.Error != "" {
			reason = sim.Error
		}
		return shadowPipelineDecision{
			Stage:       "simulation_failed",
			Reason:      reason,
			ChainStage:  chainValidation.Stage,
			ChainReason: chainValidation.Reason,
			Action:      "skip",
		}
	}

	if !app.mainLoop.ApproveTracker.HasAllowance(pool) {
		if err := app.mainLoop.ApproveTracker.EnsureApproval(ctx, pool); err != nil {
			app.mainLoop.GetMetrics().IncApproveFail()
			return shadowPipelineDecision{
				Stage:       "approval_failed",
				Reason:      err.Error(),
				ChainStage:  chainValidation.Stage,
				ChainReason: chainValidation.Reason,
				Action:      "skip",
			}
		}
	}

	result, err := app.mainLoop.OrderManager.Open(ctx, pool, amount)
	if err != nil {
		app.mainLoop.GetMetrics().IncTxFailed()
		app.mainLoop.OrderManager.OnTxFailure(ctx, pool.ID)
		return shadowPipelineDecision{
			Stage:       "order_error",
			Reason:      err.Error(),
			ChainStage:  chainValidation.Stage,
			ChainReason: chainValidation.Reason,
			Action:      "skip",
		}
	}
	if !result.Success {
		app.mainLoop.GetMetrics().IncTxFailed()
		app.mainLoop.OrderManager.OnTxFailure(ctx, pool.ID)
		reason := result.Error
		if reason == "" {
			reason = "order manager returned unsuccessful result"
		}
		return shadowPipelineDecision{
			Stage:       "order_rejected",
			Reason:      reason,
			ChainStage:  chainValidation.Stage,
			ChainReason: chainValidation.Reason,
			Action:      "skip",
			PositionID:  result.PositionID,
			TxHash:      result.TxHash,
		}
	}

	stage := "order_opened"
	action := "open_shadow_position"
	reason := "shadow order recorded"
	if result.TxHash == "" && result.PositionID != "" {
		stage = "position_reused"
		action = "reuse_shadow_position"
		reason = fmt.Sprintf("existing position %s already active in shadow state", result.PositionID)
	} else if result.PositionID != "" && result.TxHash != "" {
		reason = fmt.Sprintf("position %s recorded with shadow tx %s", result.PositionID, result.TxHash)
	}

	return shadowPipelineDecision{
		Stage:       stage,
		OK:          true,
		Reason:      reason,
		ChainStage:  chainValidation.Stage,
		ChainReason: chainValidation.Reason,
		Action:      action,
		PositionID:  result.PositionID,
		TxHash:      result.TxHash,
	}
}

func nullableString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullableInt(value int) any {
	if value <= 0 {
		return nil
	}
	return value
}
